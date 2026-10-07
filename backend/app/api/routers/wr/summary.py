"""case_id 로 검토 이력 요약 조회."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import require_api_key
from app.repositories.shared import review_history as history
from app.schemas.wr.response import (
    ReviewSummaryOut,
)

# 개발표준정의서 API 엔드포인트: /api/cgr/<도메인>/<리소스> — 복수형 케밥, 동사·버전 금지
#   GET /api/cgr/wr/review-summaries/{case_id} (기존: /api/v1/review/{case_id})
router = APIRouter(tags=["review"])


@router.get(
    "/review-summaries/{case_id}",
    response_model=ReviewSummaryOut,
    summary="case_id 로 이력 검토 결과 조회",
    dependencies=[Depends(require_api_key)],
)
async def get_review_by_case(case_id: str) -> ReviewSummaryOut:
    rows = history.read_history()
    matched = [r for r in rows if r.get("case_id") == case_id]
    if not matched:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"case_id={case_id} 결과를 이력에서 찾지 못함",
        )
    r = matched[-1]
    by_bucket = r.get("by_bucket") or {}
    return ReviewSummaryOut(
        case_id=r.get("case_id", ""),
        filename=r.get("filename", ""),
        overall_label=r.get("overall_label", ""),
        summary=by_bucket,
        n_findings=r.get("n_findings", sum(by_bucket.values())),
        elapsed_sec=0.0,
        llm_model=r.get("llm_model", ""),
    )
