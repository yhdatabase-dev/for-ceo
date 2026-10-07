#
# 표준 근로계약서 본문 생성.
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.10.02      이시영      최초 생성 (구조 이행 — 기존 backend/cgr 코드를 분리·이동)
# 2026.10.02      이시영      구조 조정 (web/ai 파트 디렉터리 → 도메인 단일 디렉터리)
# 2026.10.06      이시영      API 경로 표준화 (/api/cgr)
# 2026.10.07      이시영      화면 경로 /cgr·features 구조 이동, sync API 삭제, 업로드 원본 미저장
# 2026.10.07      이시영      검토번호 서버 발급, 변경 사유 주석 추가
#
# Author: 이시영
# Since: 2026.10.02
#
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
