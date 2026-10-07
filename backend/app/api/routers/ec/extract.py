"""근로계약서 텍스트 추출 (파일 → 텍스트, 이미지·스캔은 Vision OCR)."""
from __future__ import annotations

import tempfile
import uuid
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
from app.schemas.ec.response import ExtractResultOut, ExtractStartOut

log = get_logger(__name__)

# 프로그램명세서 AI-P02-001: POST /api/cgr/ec/extractions + GET /extractions/{job_id}
#   (기존: /api/v1/ec/extract/start, /extract/result/{job_id})
router = APIRouter(tags=["employment_contract"])


@router.post(
    "/extractions",
    response_model=ExtractStartOut,
    summary="비동기 추출 시작 — job_id·case_id 반환",
    dependencies=[Depends(require_api_key)],
)
async def post_extract_start(
    request: Request,
    file: UploadFile = File(...),
    case_id: str = Form(default=""),
    service: str = Form(default="근로계약서"),
):
    # 프로그램명세서 AI-P02-001: 검토 건 번호(case_id)는 서버가 UUID 로 발급해 응답에 돌려준다.
    #   여러 장이면 첫 장 응답의 case_id 를 이후 요청에 실어 보내므로 받은 값은 그대로 쓴다.
    #   (기존: 브라우저가 tmp_ 번호를 만들어 보냄)
    case_id = (case_id or "").strip() or str(uuid.uuid4())
    bind_context(case=case_id)  # 로그 상관 — 이후 이 요청·잡의 모든 로그에 case 부착
    content = await file.read()
    upload_tracker.validate_upload(file.filename or "", content)
    suffix = Path(file.filename or "upload.bin").suffix or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
        tf.write(content)
        tmp_path = Path(tf.name)
    filename = file.filename or ""
    # 프로그램명세서 AI-P02-001: 업로드 파일 1건 기록 — case_id 가 항상 있으므로 매 업로드 기록
    #   (기존: 브라우저가 case_id 를 보낸 경우에만 기록, 원본 파일은 저장하지 않음)
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
            return {"extracted_text": parse_to_text(tmp_path), "filename": filename, "case_id": case_id}
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception as e:
                log.warning("무시된 예외 — %s: %s", type(e).__name__, e)

    return ExtractStartOut(job_id=jobs.start_job(_do), case_id=case_id)

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
        case_id=r.get("case_id", ""),
        error=job["error"],
        elapsed_sec=job["elapsed"],
        model=get_llm_model(),
    )
