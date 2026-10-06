"""취업규칙 근로환경 AI 1차 분류 (비동기 잡)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.core import jobs
from app.core.security import require_api_key
from app.schemas.wr.request import WrClassifyIn
from app.schemas.wr.response import JobStartOut, WrClassifyResultOut
from app.services.wr import classify as wr_classify_service

router = APIRouter(tags=["review"])


@router.post(
    "/classifications",
    response_model=JobStartOut,
    summary="비동기 분류 시작 — 취업규칙 근로환경 AI 판별",
    dependencies=[Depends(require_api_key)],
)
def post_wr_classify_start(body: WrClassifyIn):
    text = body.extracted_text

    def _do() -> dict[str, Any]:
        return wr_classify_service.run(text)

    return JobStartOut(job_id=jobs.start_job(_do))

@router.get(
    "/classifications/{job_id}",
    response_model=WrClassifyResultOut,
    summary="비동기 분류 결과 폴링",
    dependencies=[Depends(require_api_key)],
)
def get_wr_classify_result(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="분류 작업을 찾을 수 없어요. 다시 시도해 주세요.",
        )
    r = job["result"] or {}
    return WrClassifyResultOut(
        status=job["status"],
        shift_work_used=r.get("shift_work_used"),
        osha_applicable=r.get("osha_applicable"),
        chemical_handling=r.get("chemical_handling"),
        workenv_measurement=r.get("workenv_measurement"),
        doc_kind=r.get("doc_kind"),
        reason=r.get("reason"),
        error=job["error"],
        elapsed_sec=job["elapsed"],
    )
