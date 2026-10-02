"""근로계약서 8섹션 구조화."""
from __future__ import annotations

import time
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from app.core import jobs
from app.core.config import get_llm_model
from app.core.security import require_api_key
from app.schemas.ec.request import StructureIn
from app.schemas.ec.response import JobStartOut, StructureOut, StructureResultOut
from app.services.ai.ec import structure as structure_service

router = APIRouter(tags=["employment_contract"])


@router.post(
    "/structure",
    response_model=StructureOut,
    summary="OCR 텍스트 → 8섹션 구조화 JSON",
    description=(
        "Step2 검토 페이지의 입력 데이터. 사용자는 표 UI 에서 행 단위로 value/note 를 수정 후\n"
        "`/ec/analyze` 로 보낸다."
    ),
    dependencies=[Depends(require_api_key)],
)
def post_structure(body: StructureIn):
    t0 = time.time()
    try:
        data = structure_service.run(body.extracted_text)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"구조화 실패: {type(e).__name__}: {e}",
        )
    return StructureOut(
        structured_data=data,
        elapsed_sec=round(time.time() - t0, 2),
        model=get_llm_model(),
    )

@router.post(
    "/structure/start",
    response_model=JobStartOut,
    summary="비동기 구조화 시작 — job_id 반환",
    dependencies=[Depends(require_api_key)],
)
def post_structure_start(body: StructureIn):
    text = body.extracted_text

    def _do() -> dict[str, Any]:
        return structure_service.run(text)

    return JobStartOut(job_id=jobs.start_job(_do))

@router.get(
    "/structure/result/{job_id}",
    response_model=StructureResultOut,
    summary="비동기 구조화 결과 폴링",
    dependencies=[Depends(require_api_key)],
)
def get_structure_result(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="구조화 작업을 찾을 수 없어요. 다시 시도해 주세요.",
        )
    return StructureResultOut(
        status=job["status"],
        structured_data=job["result"],
        error=job["error"],
        elapsed_sec=job["elapsed"],
        model=get_llm_model(),
    )
