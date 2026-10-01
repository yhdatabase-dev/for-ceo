"""취업규칙 검토 오케스트레이터 — 원본 `cgr/run.py:review_file` v2 이관.

===============================================================================
파이프라인 (원본과 동일 10단계)
===============================================================================
1) parse_document(file_path)                             # 파서 어댑터
2) WrCatalogRepo.load_all() + load_articles_meta()       # 슬롯 + 조 메타
3) applicability.is_slot_applicable(context)             # 사업장 정보 기반 SKIP
4) slots_by_article(catalog)                             # 조별 그룹핑
5) article_prefilter.filter_articles_by_embedding        # 조 단위 사전 필터
6) EmbedMatcher(text).prepare_slots(...)                 # 임베딩 슬롯 배치 준비
7) 조별 병렬 추출 (ThreadPoolExecutor):
     · embed_match 슬롯 → EmbedMatcher
     · 그 외          → extract_slots (LLM function call)
8) rules.evaluate(slot, extraction) → FindingVO          # 판정
9) explainer.explain_findings                            # 위반/누락 사유 풀이
10) optional_display_emb.build_optional_displays_emb     # 선택조 참고
11) verdict.finalize_report                              # summary + overall
12) ReportVO → ReviewFullOut 매핑                         # DTO 변환

===============================================================================
원본 대비 변경점
===============================================================================
- `catalog_path` 인자 제거 — v2 는 카탈로그를 DB(WrCatalogRepo) 에서 로드
- `MasterDB` 결합 제거 — 조 메타(title/body/scope) 는 미리 dict 로 로드해 주입
- `explain_findings` 시그니처 변경 대응 (conn + extractions_by_id 추가)
- 병렬 태스크에 `contextvars.copy_context().run(...)` 유지 — 로거 request_id 전파
- 예외 처리: 파이프라인 각 단계에 fallback → 최소 리포트라도 반환
- 리포트 저장 (save_report) 은 여기서 하지 않음 (원본 run.py 도 안 함, main 이 함)
  → v2 는 라우터가 직접 호출 시 저장 불필요. 필요 시 별도 훅 추가.
"""
from __future__ import annotations

import contextvars
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from app.core.exceptions import CgrError
from app.core.logging import bind_context, get_logger
from app.integrations.parsers.dispatcher import parse_document
from app.repositories.review.catalog_repo import ArticleMeta, WrCatalogRepo
from app.repositories.shared import HistoryRepo
from app.schemas.review.responses import (
    ArticleResultOut,
    FindingOut,
    ReviewFullOut,
)
from app.schemas.review.values import (
    ExtractionVO,
    FindingVO,
    ReportVO,
    SlotDefVO,
)
from app.schemas.shared import WorkplaceContextIn
from app.services.review.applicability import is_slot_applicable
from app.services.review.article_prefilter import (
    filter_articles_by_embedding,
    make_skipped_extractions,
)
from app.services.review.embed_matcher import EmbedMatcher
from app.services.review.explainer import explain_findings
from app.services.review.extractor import extract_slots
from app.services.review.optional_display_emb import build_optional_displays_emb
from app.services.review.rules import evaluate
from app.services.review.verdict import classify, finalize_report

log = get_logger(__name__)


class WrReviewService:
    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db
        self.catalog = WrCatalogRepo(db)

    # ─────────────────────────────────────────────────────────
    # 진입점
    # ─────────────────────────────────────────────────────────
    def review_file(
        self,
        file_path: Path,
        *,
        context: WorkplaceContextIn,
        summary_only: bool = False,
        case_id: str = "",
    ) -> ReviewFullOut:
        """취업규칙 파일 검토."""
        t_all = time.time()

        # 조기 case_id 생성 → 로그 상관에 즉시 반영 (원본 review 라우트 L230/L337 대응)
        effective_case_id = case_id or _case_id(file_path)
        bind_context(case_uid=effective_case_id)

        # 1) 파싱
        text = parse_document(file_path)

        # 2) 카탈로그 로드
        slots_all = self.catalog.load_all()
        articles_meta = self.catalog.load_articles_meta()
        article_meta_by_no: dict[int, ArticleMeta] = {a["article"]: a for a in articles_meta}
        log.info(
            "review.catalog loaded — slots=%d articles_meta=%d",
            len(slots_all),
            len(articles_meta),
        )

        # 3) 사업장 정보 기반 슬롯 필터링
        active_slots: list[SlotDefVO] = []
        skipped_slots: dict[str, str] = {}
        for s in slots_all:
            ok, reason = is_slot_applicable(s, context)
            if ok:
                active_slots.append(s)
            else:
                skipped_slots[s.slot_id] = reason or "미적용"
        if skipped_slots:
            log.info("review.applicability — %d 슬롯 SKIP", len(skipped_slots))

        # 4) 조별 그룹핑
        by_art: dict[int, list[SlotDefVO]] = {}
        for s in active_slots:
            by_art.setdefault(s.article, []).append(s)

        # 5) 사전 필터 (best-effort — 실패 시 전체 활성)
        article_texts = {n: (article_meta_by_no.get(n, {}).get("body") or "") for n in by_art}
        try:
            active_by_art, skipped_arts = filter_articles_by_embedding(
                text, by_art, article_texts
            )
            log.info(
                "review.prefilter — active=%d skip=%d",
                len(active_by_art),
                len(skipped_arts),
            )
        except Exception as e:  # noqa: BLE001
            log.warning("review.prefilter 실패 — 전체 조 LLM 진행: %s", e)
            active_by_art = by_art
            skipped_arts = {}

        # 6) EmbedMatcher 준비 (best-effort)
        embed_matcher: EmbedMatcher | None = None
        try:
            embed_matcher = EmbedMatcher(text)
            all_active_slots = [s for slots in active_by_art.values() for s in slots]
            embed_matcher.prepare_slots(all_active_slots)
        except Exception as e:  # noqa: BLE001
            log.warning("review.embed_matcher.prepare 실패 — embed_match 슬롯은 개별 처리: %s", e)

        # 10) 선택조 참고 — 병렬 시작 (백그라운드)
        covered = set(by_art.keys())
        od_executor = ThreadPoolExecutor(max_workers=1)
        od_future = od_executor.submit(
            contextvars.copy_context().run,
            build_optional_displays_emb,
            text,
            articles_meta,
            excluded_articles=covered,
        )

        # 7) 조별 병렬 추출
        results = self._extract_all_articles(
            text, active_by_art, skipped_arts, by_art, embed_matcher
        )

        # 8) rules.evaluate → FindingVO + extractions_by_id 유지 (explainer 용)
        all_findings: list[FindingVO] = []
        extractions_by_id: dict[str, ExtractionVO] = {}
        for article, slots, extractions, err in results:
            if err is not None or not extractions:
                extractions = [
                    ExtractionVO(
                        slot_id=s.slot_id,
                        found=False,
                        extracted_value=None,
                        quote="",
                        confidence=None,
                    )
                    for s in slots
                ]
            for s, e in zip(slots, extractions):
                extractions_by_id[s.slot_id] = e
                f = evaluate(s, e)
                # fix_example 주입 (원본 정책)
                if f.status in ("VIOLATION", "MISSING", "AMBIGUOUS") and s.fix_example:
                    f.fix_example = s.fix_example
                all_findings.append(f)

        # 9) 위반/누락 사유 LLM 풀이 (best-effort)
        slots_by_id = {s.slot_id: s for s in slots_all}
        try:
            t0 = time.time()
            explain_findings(self.db, all_findings, slots_by_id, extractions_by_id)
            log.info("review.explainer — %.1fs", time.time() - t0)
        except Exception as e:  # noqa: BLE001
            log.warning("review.explainer 실패 — 기술적 사유 그대로 노출: %s", e)

        # 10) 선택조 결과 회수
        try:
            optional_displays = od_future.result(timeout=30.0)
        except Exception as e:  # noqa: BLE001
            log.warning("review.optional_display 실패 — 빈 리스트로 진행: %s", e)
            optional_displays = []
        finally:
            od_executor.shutdown(wait=False)

        # 11) ReportVO 조립 + finalize
        article_titles = {n: (m.get("title") or "") for n, m in article_meta_by_no.items()}
        report = ReportVO(
            case_id=effective_case_id,
            filename=file_path.name,
            findings=all_findings,
            optional_displays=optional_displays,
            article_titles=article_titles,
            source_file=str(file_path),
            generated_at=datetime.now(timezone.utc).isoformat(),
            elapsed_sec=round(time.time() - t_all, 3),
        )
        finalize_report(report)

        # 12) 이력 저장 (best-effort — 감사·통계용)
        self._append_history(report)

        # 13) DTO 매핑
        return _to_review_full_out(report, article_titles, summary_only=summary_only)

    # ─────────────────────────────────────────────────────────
    # 이력 저장 (원본 store.history.append_history 대체)
    # ─────────────────────────────────────────────────────────
    def _append_history(self, report: ReportVO) -> None:
        """검토 이력을 cgr_txn.review_history 에 append.

        실패해도 검토 응답은 영향받지 않음 (best-effort).
        """
        try:
            by_status: dict[str, int] = {}
            by_severity: dict[str, int] = {}
            for f in report.findings:
                by_status[f.status] = by_status.get(f.status, 0) + 1
                by_severity[f.severity] = by_severity.get(f.severity, 0) + 1

            # top_violations — 위반/누락 상위 5건 (사유 짧게)
            top: list[dict] = []
            for f in report.findings:
                if f.status in ("VIOLATION", "MISSING") and len(top) < 5:
                    top.append(
                        {
                            "slot_id": f.slot_id,
                            "article": f.article,
                            "status": f.status,
                            "severity": f.severity,
                            "reason": (f.user_reason or f.reason)[:200],
                        }
                    )

            HistoryRepo(self.db).append(
                case_id=None,
                case_uid=report.case_id,
                filename=report.filename,
                overall_label=report.overall_label,
                llm_model=report.llm_model or None,
                n_findings=len(report.findings),
                by_status=by_status,
                by_severity=by_severity,
                by_bucket=report.summary,
                top_violations=top,
                report_path=None,   # save_report 로 저장 시 여기 설정 (현재는 비사용)
            )
        except Exception as e:  # noqa: BLE001
            log.warning("review.history.append 실패 (무시): %s", e)

    # ─────────────────────────────────────────────────────────
    # 조별 병렬 추출
    # ─────────────────────────────────────────────────────────
    def _extract_all_articles(
        self,
        text: str,
        active_by_art: dict[int, list[SlotDefVO]],
        skipped_arts: dict[int, str],
        by_art_original: dict[int, list[SlotDefVO]],
        embed_matcher: EmbedMatcher | None,
    ) -> list[tuple[int, list[SlotDefVO], list[ExtractionVO], Exception | None]]:
        """조별 병렬 추출 (원본 run.py:_extract_article 대응)."""
        db = self.db

        def _one(article: int, slots: list[SlotDefVO]):
            t0 = time.time()
            try:
                embed_slots = [s for s in slots if s.comparator == "embed_match"]
                llm_slots = [s for s in slots if s.comparator != "embed_match"]
                extractions: list[ExtractionVO] = []
                if embed_slots and embed_matcher is not None:
                    extractions.extend(embed_matcher.match_many(embed_slots))
                if llm_slots:
                    extractions.extend(extract_slots(db, text, llm_slots))
                # 슬롯 원래 순서대로 재정렬
                ext_by_id = {e.slot_id: e for e in extractions}
                ordered = [ext_by_id[s.slot_id] for s in slots if s.slot_id in ext_by_id]
                log.info(
                    "review.article[%d] 추출 %d슬롯 [embed:%d llm:%d] %.1fs",
                    article,
                    len(slots),
                    len(embed_slots),
                    len(llm_slots),
                    time.time() - t0,
                )
                return article, slots, ordered, None
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "review.article[%d] 추출 실패 (%.1fs): %s",
                    article,
                    time.time() - t0,
                    e,
                )
                return article, slots, [], e

        results: list[tuple[int, list[SlotDefVO], list[ExtractionVO], Exception | None]] = []
        if active_by_art:
            with ThreadPoolExecutor(max_workers=min(30, len(active_by_art))) as ex:
                futures = [
                    ex.submit(contextvars.copy_context().run, _one, a, s)
                    for a, s in sorted(active_by_art.items())
                ]
                for fut in as_completed(futures):
                    results.append(fut.result())

        # 사전필터 SKIP 조 — 빈 추출로 채움 (rules 가 required 여부 따라 MISSING/OK 판정)
        for art_no in skipped_arts:
            slots = by_art_original[art_no]
            results.append((art_no, slots, make_skipped_extractions(slots), None))

        results.sort(key=lambda r: r[0])
        return results


# ─────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────
def _case_id(file_path: Path) -> str:
    """원본 run.py:_case_id 그대로 — 파일 stem + 내용 sha256[:12]."""
    try:
        h = hashlib.sha256(file_path.read_bytes()).hexdigest()[:12]
    except OSError:
        h = hashlib.sha256(str(file_path).encode()).hexdigest()[:12]
    return f"{file_path.stem[:20]}_{h}"


def _to_review_full_out(
    report: ReportVO,
    article_titles: dict[int, str],
    *,
    summary_only: bool,
) -> ReviewFullOut:
    """ReportVO (내부 flat) → ReviewFullOut (조별 그룹 DTO)."""
    n_findings = len(report.findings)

    if summary_only:
        article_results: list[ArticleResultOut] = []
    else:
        by_article: dict[int, list[FindingVO]] = {}
        for f in report.findings:
            by_article.setdefault(f.article, []).append(f)
        article_results = [
            ArticleResultOut(
                article=art,
                title=article_titles.get(art, ""),
                findings=[_to_finding_out(f) for f in by_article[art]],
            )
            for art in sorted(by_article.keys())
        ]

    return ReviewFullOut(
        case_id=report.case_id,
        filename=report.filename,
        overall_label=report.overall_label,
        summary=report.summary,
        n_findings=n_findings,
        elapsed_sec=report.elapsed_sec,
        llm_model=report.llm_model,
        article_results=article_results,
    )


def _to_finding_out(f: FindingVO) -> FindingOut:
    return FindingOut(
        slot_id=f.slot_id,
        article=f.article,
        bucket=classify(f),
        status=f.status,
        severity=f.severity,
        comparator=f.comparator,
        reason=f.reason,
        user_reason=f.user_reason,
        quote=f.quote,
        extracted_value=f.extracted_value,
        penalty_omission=f.penalty_omission,
        penalty_violation=f.penalty_violation,
        fix_example=f.fix_example,
    )
