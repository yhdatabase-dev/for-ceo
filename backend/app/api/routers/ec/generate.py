"""표준 근로계약서 본문 생성."""
from __future__ import annotations


from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from app.core import jobs
from app.core.config import get_llm_model
from app.core.security import require_api_key
from app.schemas.ec.request import GenerateIn
from app.schemas.ec.response import GenerateResultOut, JobStartOut
from app.services.ec import generate as generate_service

# 프로그램명세서 AI-P02-009: POST /api/cgr/ec/drafts + GET /drafts/{job_id}
#   (기존: /api/v1/ec/generate/start, /generate/result/{job_id})
router = APIRouter(tags=["employment_contract"])


@router.post(
    "/drafts",
    response_model=JobStartOut,
    summary="비동기 계약서 생성 시작 — job_id 반환",
    dependencies=[Depends(require_api_key)],
)
def post_generate_start(body: GenerateIn):
    def _do() -> str:
        return generate_service.run(
            body.analysis_result,
            user_overrides=body.user_overrides or None,
        )

    job_id = jobs.start_job(_do)
    return JobStartOut(job_id=job_id)

@router.get(
    "/drafts/{job_id}",
    response_model=GenerateResultOut,
    summary="비동기 계약서 생성 결과 폴링",
    dependencies=[Depends(require_api_key)],
)
def get_generate_result(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="생성 작업을 찾을 수 없어요. 다시 시도해 주세요.",
        )
    return GenerateResultOut(
        status=job["status"],
        contract_text=job["result"],
        error=job["error"],
        elapsed_sec=job["elapsed"],
        model=get_llm_model(),
    )
