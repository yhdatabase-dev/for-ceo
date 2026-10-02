"""취업규칙 수정본 생성 (비동기 잡)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core import jobs
from app.core.config import get_llm_model
from app.core.security import require_api_key
from app.schemas.wr.request import GenerateIn
from app.schemas.wr.response import (
    GenerateResultOut,
    ReviewJobStartOut,
)
from app.services.wr import revise
from app.services.wr.dispatch import _load_standard_work_rules

router = APIRouter(tags=["review"])


@router.post(
    "/generate/start",
    response_model=ReviewJobStartOut,
    summary="비동기 취업규칙 수정본 생성 시작 — job_id 반환",
    description=(
        "원문은 그대로 유지하고, 사용자가 담은 수정 항목만 반영한 "
        "'취업규칙 수정본' 전문을 생성합니다."
    ),
    dependencies=[Depends(require_api_key)],
)
def post_generate_start(body: GenerateIn):
    original_text = body.original_text
    corrections = [c.model_dump() for c in body.corrections]
    standard = _load_standard_work_rules()

    def _do() -> str:
        # mark_changes=True — 교체·추가 문구를 【수정】…【/수정】 로 감싸 반환.
        # 프론트(wr/contract)가 하이라이트 렌더에 사용. SC 경로는 기본 False 유지.
        return revise.run(
            "취업규칙",
            original_text,
            corrections,
            standard_text=standard,
            mark_changes=True,
        )

    return ReviewJobStartOut(job_id=jobs.start_job(_do))

@router.get(
    "/generate/result/{job_id}",
    response_model=GenerateResultOut,
    summary="비동기 취업규칙 수정본 생성 결과 폴링",
    dependencies=[Depends(require_api_key)],
)
def get_generate_result(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="생성 작업을 찾을 수 없어요. 작업이 만료됐거나 서버가 재시작됐을 수 있어요. 다시 시도해 주세요.",
        )
    return GenerateResultOut(
        status=job["status"],
        revised_text=job["result"],
        error=job["error"],
        elapsed_sec=job["elapsed"],
        model=get_llm_model(),
    )
