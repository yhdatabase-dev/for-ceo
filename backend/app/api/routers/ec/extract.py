"""근로계약서 텍스트 추출 (파일 → 텍스트, 이미지·스캔은 Vision OCR)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)

from app.core import jobs
from app.core import upload as upload_tracker
from app.core.config import get_llm_model
from app.core.logging import bind_context, get_logger
from app.core.security import require_api_key
from app.integrations.parsers.dispatcher import parse_to_text
from app.schemas.ec.response import ExtractResultOut, JobStartOut

log = get_logger(__name__)

router = APIRouter(tags=["employment_contract"])


@router.post(
    "/extractions",
    response_model=JobStartOut,
    summary="비동기 추출 시작 — job_id 반환",
    dependencies=[Depends(require_api_key)],
)
async def post_extract_start(
    request: Request,
    file: UploadFile = File(...),
    case_id: str = Form(default=""),
    service: str = Form(default="근로계약서"),
):
    bind_context(case=case_id)  # 로그 상관 — 이후 이 요청·잡의 모든 로그에 case 부착
    content = await file.read()
    upload_tracker.validate_upload(file.filename or "", content)
    suffix = Path(file.filename or "upload.bin").suffix or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
        tf.write(content)
        tmp_path = Path(tf.name)
    filename = file.filename or ""
    # 업로드 메타 기록 (case_id 로 연결, 원본 파일은 저장하지 않음)
    if case_id:
        upload_tracker.record_upload(
            content=content,
            filename=filename,
            mime=file.content_type or "",
            service=service or "근로계약서",
            request=request,
            case_id=case_id,
        )

    def _do() -> dict[str, str]:
        try:
            return {"extracted_text": parse_to_text(tmp_path), "filename": filename}
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception as e:
                log.warning("무시된 예외 — %s: %s", type(e).__name__, e)

    return JobStartOut(job_id=jobs.start_job(_do))

@router.get(
    "/extractions/{job_id}",
    response_model=ExtractResultOut,
    summary="비동기 추출 결과 폴링",
    dependencies=[Depends(require_api_key)],
)
def get_extract_result(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="추출 작업을 찾을 수 없어요. 다시 시도해 주세요.",
        )
    r = job["result"] or {}
    return ExtractResultOut(
        status=job["status"],
        extracted_text=r.get("extracted_text"),
        filename=r.get("filename", ""),
        error=job["error"],
        elapsed_sec=job["elapsed"],
        model=get_llm_model(),
    )
