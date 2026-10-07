#
# MVP 파이프라인 오케스트레이션.
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.05.28      kimzion77   최초 생성
# 2026.10.02      이시영      구조 이행 (backend/cgr → backend/app)
# 2026.10.02      이시영      구조 조정 (web/ai 파트 디렉터리 → 도메인 단일 디렉터리)
#
# Author: kimzion77
# Since: 2026.05.28
#
"""MVP 파이프라인 오케스트레이션.

review_file(file_path, catalog_path) → Report
"""
from __future__ import annotations

import contextvars
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from app.services.wr.applicability import is_slot_applicable
from app.services.wr.article_prefilter import filter_articles_by_embedding, make_skipped_extractions
from app.repositories.wr.catalog import load_catalog_with_master_db, slots_by_article
from app.services.wr.embed_matcher import EmbedMatcher
from app.services.wr.explainer import explain_findings
from app.services.wr.extractor import extract_slots
from app.repositories.wr.master import get_master_db
from app.schemas.wr.values import ArticleResult, Extraction, Finding, Report, WorkplaceContext
from app.services.wr.optional_display_emb import build_optional_displays_emb
from app.integrations.parsers.dispatcher import parse_to_text
from app.services.wr.rules import evaluate
from app.core.logging import get_logger
from app.services.wr.verdict import finalize_report


log = get_logger(__name__)


def _case_id(file_path: Path) -> str:
    h = hashlib.sha256(file_path.read_bytes()).hexdigest()[:12]
    return f"{file_path.stem[:20]}_{h}"


def review_file(
    file_path: str | Path,
    catalog_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    context: WorkplaceContext | None = None,
) -> Report:
    fp = Path(file_path)
    text = parse_to_text(fp)
    db = get_master_db()
    log.info(f"[마스터 DB] {db.path} ({len(db.all_articles())}개 조)")
    catalog = load_catalog_with_master_db(catalog_path, db)

    # 사업장 정보 기반 슬롯 필터링
    skipped_slots: dict[str, str] = {}  # slot_id → reason
    if context is not None:
        active_slots = []
        for s in catalog.slots:
            ok, reason = is_slot_applicable(s, context)
            if ok:
                active_slots.append(s)
            else:
                skipped_slots[s.slot_id] = reason or "N/A"
        n_skipped = len(catalog.slots) - len(active_slots)
        log.info(f"[사업장 정보] {n_skipped}개 슬롯 SKIP (미적용)")
        catalog.slots = active_slots

    by_art = slots_by_article(catalog)

    # 조별 LLM 추출을 병렬 실행 (각 조는 독립 LLM 호출, embed_match 슬롯은 분리)
    def _extract_article(article: int, slots):
        t0 = time.time()
        try:
            # embed_match vs LLM 슬롯 분리
            embed_slots = [s for s in slots if s.comparator == "embed_match"]
            llm_slots = [s for s in slots if s.comparator != "embed_match"]
            extractions: list[Extraction] = []
            if embed_slots:
                extractions.extend(embed_matcher.match_many(embed_slots))
            if llm_slots:
                extractions.extend(extract_slots(text, llm_slots))
            # 슬롯 원래 순서대로 정렬
            ext_by_id = {e.slot_id: e for e in extractions}
            ordered = [ext_by_id.get(s.slot_id) for s in slots]
            ordered = [e for e in ordered if e is not None]
            elapsed = time.time() - t0
            log.info(
                f"  [제{article}조] 추출 완료 ({len(slots)}슬롯 [embed:{len(embed_slots)} llm:{len(llm_slots)}], {elapsed:.1f}s)"
            )
            return article, slots, ordered, None
        except Exception as e:
            elapsed = time.time() - t0
            log.warning(f"  [제{article}조] 추출 실패 ({elapsed:.1f}s): {e}")
            return article, slots, [], e

    # 사전필터 — 사업장 본문에 부재한 영역의 조는 LLM 호출 안 함
    log.info(f"[사전필터] {len(by_art)}개 조 임베딩 유사도 검사...")
    pf_t0 = time.time()
    try:
        active_by_art, skipped_arts = filter_articles_by_embedding(text, by_art, db)
        log.info(
            f"[사전필터] LLM 호출 {len(active_by_art)}개 / SKIP {len(skipped_arts)}개 "
            f"({time.time() - pf_t0:.1f}s)"
        )
    except Exception as e:
        log.warning(f"[사전필터] 실패 — 모든 조 LLM 호출로 진행: {e}")
        active_by_art = by_art
        skipped_arts = {}

    # embed_match 슬롯 1번 batch 사전 임베딩 (사전필터 결과 기반)
    em_t0 = time.time()
    embed_matcher = EmbedMatcher(text)
    all_active_slots = [s for slots in active_by_art.values() for s in slots]
    embed_matcher.prepare_slots(all_active_slots)
    n_embed_slots = sum(1 for s in all_active_slots if s.comparator == "embed_match")
    log.info(
        f"[임베딩 매처] 본문 청크 {len(embed_matcher.chunks)}개 + 슬롯 {n_embed_slots}개 사전 임베딩 ({time.time() - em_t0:.1f}s)"
    )

    # 선택 디스플레이 임베딩을 추출과 동시 시작 (별도 thread)
    log.info("[선택 조 디스플레이] 임베딩 매칭 시작 (백그라운드)...")
    od_executor = ThreadPoolExecutor(max_workers=1)
    od_t0 = time.time()
    covered = set(by_art.keys())
    od_future = od_executor.submit(
        contextvars.copy_context().run,
        build_optional_displays_emb, text, db, excluded_articles=covered,
    )

    log.info(f"[추출 시작] {len(active_by_art)}개 조 병렬 호출 (동시성 30)")
    t0 = time.time()
    article_results: list[ArticleResult] = []
    with ThreadPoolExecutor(max_workers=min(30, len(active_by_art) or 1)) as ex:
        futures = [
            ex.submit(contextvars.copy_context().run, _extract_article, a, s)
            for a, s in sorted(active_by_art.items())
        ]
        results = []
        for fut in as_completed(futures):
            results.append(fut.result())
    # SKIP 된 조: 빈 추출로 채움 (모든 슬롯 found=false → MISSING/OK 처리됨)
    for art_no, reason in skipped_arts.items():
        slots = by_art[art_no]
        results.append((art_no, slots, make_skipped_extractions(slots), None))
    log.info(f"[추출 완료] 총 {time.time() - t0:.1f}s")

    # 조 번호 순 정렬 후 평가
    results.sort(key=lambda r: r[0])
    for article, slots, extractions, err in results:
        if err is not None or not extractions:
            # 호출 실패 시 모든 슬롯 ERROR 로 마킹
            findings = [
                evaluate(
                    s,
                    Extraction(slot_id=s.slot_id, found=False, extracted_value=None, quote="", confidence=None),
                )
                for s in slots
            ]
        else:
            findings = [evaluate(s, e) for s, e in zip(slots, extractions)]
        # 부적합/불명확 슬롯에 fix_example 주입 (slot 정의에서)
        slots_by_id = {s.slot_id: s for s in slots}
        for f in findings:
            if f.status in ("VIOLATION", "MISSING", "AMBIGUOUS"):
                s = slots_by_id.get(f.slot_id)
                if s and s.fix_example:
                    f.fix_example = s.fix_example
        article_results.append(
            ArticleResult(
                article=article,
                title=db.title(article),
                findings=findings,
                article_text="",
                scope=db.article(article).get("scope") if db.article(article) else None,
            )
        )

    # 위반/누락 사유 LLM 풀이 — 감독관용 평이한 한국어로 변환
    all_findings: list[Finding] = []
    for ar in article_results:
        all_findings.extend(ar.findings)
    slots_by_id = {s.slot_id: s for s in catalog.slots}
    log.info("[사유 풀이] LLM 호출 중...")
    t0 = time.time()
    try:
        explain_findings(all_findings, slots_by_id)
        log.info(f"[사유 풀이] 완료 ({time.time() - t0:.1f}s)")
    except Exception as e:
        log.warning(f"[사유 풀이] 실패 — 기술적 사유 그대로 표시: {e}")

    # 선택 디스플레이 — 추출과 병렬로 시작했던 future 회수
    try:
        optional_displays = od_future.result(timeout=30.0)
        log.info(
            f"[선택 조 디스플레이] {len(optional_displays)}개 조 (전체 {time.time() - od_t0:.1f}s · 병렬 효과)"
        )
    except Exception as e:
        log.warning(f"[선택 조 디스플레이] 임베딩 실패 — 빈 디스플레이로 진행: {e}")
        optional_displays = []
    finally:
        od_executor.shutdown(wait=False)

    report = Report(
        case_id=_case_id(fp),
        source_file=str(fp),
        article_results=article_results,
        optional_displays=optional_displays,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    return finalize_report(report)
