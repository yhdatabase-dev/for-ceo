"""표준 근로계약서 본문 생성."""
from __future__ import annotations

import time

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
from app.schemas.ec.response import GenerateOut, GenerateResultOut, JobStartOut
from app.services.ec import generate as generate_service

router = APIRouter(tags=["employment_contract"])


@router.post(
    "/drafts/sync",
    response_model=GenerateOut,
    summary="분석 결과 → 표준 근로계약서 텍스트",
    dependencies=[Depends(require_api_key)],
)
def post_generate(body: GenerateIn):
    t0 = time.time()
    try:
        text = generate_service.run(
            body.analysis_result,
            user_overrides=body.user_overrides or None,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"계약서 생성 실패: {type(e).__name__}: {e}",
        )
    return GenerateOut(
        contract_text=text,
        elapsed_sec=round(time.time() - t0, 2),
        model=get_llm_model(),
    )

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
