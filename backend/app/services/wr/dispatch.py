"""취업규칙·근로계약서 검토 요청 실행 — 동기·비동기 라우트가 공유하는 실행부와 응답 변환."""
from __future__ import annotations

import time
from functools import lru_cache  # noqa: E402
from pathlib import Path

from fastapi import HTTPException, status

from app.core.config import get_llm_model
from app.core.logging import bind_context, get_logger
from app.repositories.shared import access_log
from app.repositories.shared import review_history as history
from app.schemas.ec.response import EcFindingOut, EcReviewOut
from app.schemas.wr.response import (
    ArticleResultOut,
    FindingOut,
    ReviewFullOut,
)
from app.schemas.wr.values import WorkplaceContext
from app.services.ec.review import review_ec_file
from app.services.wr.penalty_parser import format_for_user
from app.services.wr.review import review_file
from app.services.wr.verdict import classify

log = get_logger(__name__)


_PROJECT_ROOT = Path(__file__).resolve().parents[3]

_CATALOG_PATH = _PROJECT_ROOT / "data" / "slots" / "atomic_slots_v0.yaml"

_STANDARD_WR_PATH = _PROJECT_ROOT / "data" / "standards" / "표준취업규칙_2026.txt"

@lru_cache(maxsize=1)
def _load_standard_work_rules() -> str | None:
    """고용노동부 표준취업규칙(2026) 전문 — 수정본 생성 시 준용 기준으로 주입.

    파일이 없어도(과거 배포 이미지 등) 수정본 생성 자체는 동작해야 하므로
    None 을 반환하고 revise 는 표준 없이 진행한다.
    """
    try:
        return _STANDARD_WR_PATH.read_text(encoding="utf-8")
    except Exception as e:
        log.warning("실패 — None 반환: %s: %s", type(e).__name__, e)
        return None

def _finding_to_out(f, ar_title: str) -> FindingOut:
    """cgr.models.Finding → API 응답 FindingOut."""
    penalty_groups = format_for_user(f.penalty or [])
    return FindingOut(
        slot_id=f.slot_id,
        article=f.article,
        bucket=classify(f),
        status=f.status,
        severity=f.severity or "",
        comparator=f.comparator,
        reason=f.reason or "",
        user_reason=f.user_reason,
        quote=(f.extracted.quote if f.extracted else "") or "",
        extracted_value=(f.extracted.extracted_value if f.extracted else None),
        penalty_omission=penalty_groups["omission"],
        penalty_violation=penalty_groups["violation"],
        fix_example=f.fix_example,
    )

def _to_bool(v: str | None) -> bool | None:
    if v is None or v == "" or v.lower() == "null":
        return None
    return v.lower() in ("true", "1", "yes", "y")

def _parse_worker_types(v: str | None) -> list[str]:
    """`정규직,기간제,단시간` 같은 콤마 구분 문자열 → list."""
    if not v:
        return []
    return [t.strip() for t in v.split(",") if t.strip()]

def _dispatch_review(
    tmp_path: Path,
    filename: str,
    document_type: str,
    context: WorkplaceContext,
    summary_only: bool,
    case_id: str = "",
) -> dict:
    """검토 실행 후 JSON 직렬화 dict 반환 — 백그라운드 잡에서 호출."""
    try:
        if document_type == "employment_contract":
            out = _run_employment_contract(tmp_path, filename, context)
        else:
            out = _run_work_rules(tmp_path, filename, context, summary_only, case_id)
        return out.model_dump(mode="json")
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception as e:
            log.warning("무시된 예외 — %s: %s", type(e).__name__, e)

def _run_work_rules(
    tmp_path: Path,
    filename: str,
    context: WorkplaceContext,
    summary_only: bool,
    case_id: str = "",
) -> ReviewFullOut:
    """취업규칙 검토 흐름 (기존 로직).

    case_id 는 프론트 리뷰 세션 id — 홈 추출 단계에서 보관한 원본 파일(이미지/문서)과
    이 검토 로그를 연결하는 키. 비면 백엔드가 만든 report.case_id 로 폴백한다.
    """
    t0 = time.time()
    try:
        report = review_file(tmp_path, _CATALOG_PATH, context=context)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"검토 실패: {type(e).__name__}: {e}",
        )
    elapsed = time.time() - t0

    # 이력 누적
    try:
        entry = history.build_entry_from_report(report)
        entry["filename"] = filename
        entry["service"] = "취업규칙"
        history.append_history(entry)
    except Exception as e:
        log.warning("무시된 예외 — %s: %s", type(e).__name__, e)
    try:
        access_log.log_event(
            service="취업규칙",
            action="review",
            meta={"filename": filename, "via": "api"},
        )
    except Exception as e:
        log.warning("무시된 예외 — %s: %s", type(e).__name__, e)

    article_results = []
    if not summary_only:
        for ar in report.article_results:
            article_results.append(
                ArticleResultOut(
                    article=ar.article,
                    title=ar.title or "",
                    findings=[_finding_to_out(f, ar.title or "") for f in ar.findings],
                )
            )

    try:
        import json as _json

        from app.repositories.shared import analytics as _an

        # 원본 파일(이미지/문서)은 홈 추출 단계(/ec/extract/start, service=취업규칙)에서
        # 같은 case_id 로 이미 보관됨 → 여기선 로그를 case_id 로 연결만 한다.
        # (취업규칙 검토는 사용자가 확인·수정한 텍스트를 .txt 로 감싸 보내므로
        #  tmp_path 는 원본이 아니라 가공 텍스트라 따로 저장하지 않는다.)
        _case = (case_id or report.case_id or "").strip() or None
        bind_context(case=_case)  # report 산출 후 확정 case 재바인드

        # 무엇을 위반/누락으로 잡았는지 — 조항·판정·근거·원문 인용·권고까지 전체 기록
        _flagged: list[dict] = []
        _ok = 0
        for _ar in report.article_results:
            for _f in _ar.findings:
                _b = classify(_f)
                if _b == "적정":
                    _ok += 1
                    continue
                _flagged.append(
                    {
                        "article": _f.article,
                        "title": (_ar.title or "")[:120],
                        "bucket": _b,
                        "severity": _f.severity or "",
                        "reason": (_f.reason or "")[:600],
                        "quote": ((_f.extracted.quote if _f.extracted else "") or "")[:400],
                        "fix": (_f.fix_example or "")[:600],
                    }
                )
        _payload = {
            "overall": report.overall_label or "",
            "summary": dict(report.summary or {}),
            "flagged": _flagged[:80],
            "flagged_total": len(_flagged),
            "ok_count": _ok,
            "case_id": report.case_id,
        }
        _an.log_interaction(
            kind="취업규칙",
            model=get_llm_model(),
            input_text=f"[취업규칙 검토] {filename}",
            output_text=_json.dumps(_payload, ensure_ascii=False)[:12000],
            visitor="",
            case_id=_case,
        )
    except Exception as e:
        log.warning("무시된 예외 — %s: %s", type(e).__name__, e)

    return ReviewFullOut(
        case_id=report.case_id,
        filename=filename,
        overall_label=report.overall_label or "",
        summary=dict(report.summary),
        n_findings=sum(report.summary.values()) if report.summary else 0,
        elapsed_sec=round(elapsed, 2),
        llm_model=get_llm_model(),
        article_results=article_results,
    )

def _run_employment_contract(
    tmp_path: Path,
    filename: str,
    context: WorkplaceContext,
) -> EcReviewOut:
    """근로계약서 검토 흐름 (3-Bucket)."""
    try:
        report = review_ec_file(tmp_path, context=context)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"근로계약서 검토 실패: {type(e).__name__}: {e}",
        )

    # 이력 누적 (취업규칙과 분리)
    try:
        access_log.log_event(
            service="근로계약서",
            action="review",
            meta={
                "filename": filename,
                "via": "api",
                "overall_label": report.overall_label,
            },
        )
    except Exception as e:
        log.warning("무시된 예외 — %s: %s", type(e).__name__, e)

    findings_out = [
        EcFindingOut(
            slot_id=f.slot_id,
            field=f.field,
            bucket=f.bucket,
            severity=f.severity,
            present=f.present,
            extracted=f.extracted,
            reason=f.reason,
            required_content=f.required_content,
            purpose=f.purpose,
            laws=f.laws,
            topic_meta=f.topic_meta,
            fix_example=f.fix_example,
        )
        for f in report.findings
    ]

    return EcReviewOut(
        case_id=report.case_id,
        filename=filename,
        doc="employment_contract",
        overall_label=report.overall_label,
        summary=report.summary,
        n_findings=len(report.findings),
        skipped=report.skipped,
        elapsed_sec=report.elapsed_sec,
        findings=findings_out,
    )
