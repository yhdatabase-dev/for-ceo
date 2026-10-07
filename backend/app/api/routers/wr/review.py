"""취업규칙 검토 실행 (비동기 잡)."""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.core import jobs
from app.core.logging import bind_context, get_logger
from app.core.security import require_api_key
from app.schemas.wr.response import (
    ReviewJobResultOut,
    ReviewJobStartOut,
)
from app.schemas.wr.values import WorkplaceContext
from app.services.wr.dispatch import (
    _dispatch_review,
    _parse_worker_types,
    _to_bool,
)

log = get_logger(__name__)

# 프로그램명세서 AI-P03-001: POST /api/cgr/wr/reviews + GET /reviews/{job_id}
#   (기존: /api/v1/review/start, /review/result/{job_id})
router = APIRouter(tags=["review"])


@router.post(
    "/reviews",
    response_model=ReviewJobStartOut,
    summary="비동기 검토 시작 — job_id 반환",
    dependencies=[Depends(require_api_key)],
)
async def post_review_start(
    file: UploadFile = File(...),
    document_type: str = Form(default="work_rules"),
    shift_work_used: str | None = Form(default=None),
    osha_applicable: str | None = Form(default="true"),
    chemical_handling: str | None = Form(default=None),
    workenv_measurement: str | None = Form(default=None),
    business_size: str | None = Form(default=None),
    worker_types: str | None = Form(default=None),
    summary_only: bool = Form(default=False),
    case_id: str = Form(default=""),
):
    # 프로그램명세서 AI-P03-001: 검토 응답의 case_id 는 서버 생성 UUID.
    #   화면은 추출 단계에서 받은 번호를 보내고, 없으면 여기서 발급한다. (기존: 브라우저 tmp_ 번호 또는 파일 해시)
    case_id = (case_id or "").strip() or str(uuid.uuid4())
    bind_context(case=case_id)  # 로그 상관 — 이후 이 요청·잡의 모든 로그에 case 부착
    suffix = Path(file.filename or "upload.bin").suffix or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
        tf.write(await file.read())
        tmp_path = Path(tf.name)
    filename = file.filename or ""

    bs = business_size if business_size in ("5+", "5-", "any") else None
    context = WorkplaceContext(
        shift_work_used=_to_bool(shift_work_used),
        osha_applicable=_to_bool(osha_applicable) if osha_applicable else True,
        chemical_handling=_to_bool(chemical_handling),
        workenv_measurement=_to_bool(workenv_measurement),
        business_size=bs,
        worker_types=_parse_worker_types(worker_types),
    )

    def _do() -> dict:
        out = _dispatch_review(
            tmp_path, filename, document_type, context, summary_only, case_id
        )
        # 프로그램명세서 AI-P03-001: 응답 case_id 를 서버 발급 번호로 맞춘다
        #   (기존: 검토 엔진이 파일 내용으로 만든 해시값)
        out["case_id"] = case_id
        return out

    job_id = jobs.start_job(_do)
    return ReviewJobStartOut(job_id=job_id, case_id=case_id)

@router.get(
    "/reviews/{job_id}",
    response_model=ReviewJobResultOut,
    summary="비동기 검토 결과 폴링",
    dependencies=[Depends(require_api_key)],
)
def get_review_result(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="검토 작업을 찾을 수 없어요. 작업이 만료됐거나 서버가 재시작됐을 수 있어요. 다시 시도해 주세요.",
        )
    return ReviewJobResultOut(
        status=job["status"],
        result=job["result"],
        error=job["error"],
        elapsed_sec=job["elapsed"],
    )
