"""근로계약서 근로자 유형 AI 분류."""
from __future__ import annotations

from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from app.core import jobs
from app.core.security import require_api_key
from app.schemas.ec.request import ClassifyIn
from app.schemas.ec.response import ClassifyResultOut, JobStartOut
from app.services.ec import classify as classify_service

# 프로그램명세서 AI-P02-003: POST /api/cgr/ec/classifications + GET /classifications/{job_id}
#   (기존: /api/v1/ec/classify/start, /classify/result/{job_id})
router = APIRouter(tags=["employment_contract"])


@router.post(
    "/classifications",
    response_model=JobStartOut,
    summary="비동기 분류 시작 — 근로자 유형 AI 판별",
    dependencies=[Depends(require_api_key)],
)
def post_classify_start(body: ClassifyIn):
    text = body.extracted_text

    def _do() -> dict[str, Any]:
        return classify_service.run(text)

    return JobStartOut(job_id=jobs.start_job(_do))

@router.get(
    "/classifications/{job_id}",
    response_model=ClassifyResultOut,
    summary="비동기 분류 결과 폴링",
    dependencies=[Depends(require_api_key)],
)
def get_classify_result(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="분류 작업을 찾을 수 없어요. 다시 시도해 주세요.",
        )
    r = job["result"] or {}
    return ClassifyResultOut(
        status=job["status"],
        worker_types=r.get("worker_types"),
        doc_kind=r.get("doc_kind"),
        reason=r.get("reason"),
        error=job["error"],
        elapsed_sec=job["elapsed"],
    )
