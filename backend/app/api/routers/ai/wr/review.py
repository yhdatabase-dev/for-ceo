"""취업규칙 검토 실행 (동기 + 비동기 잡)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.core import jobs
from app.core.logging import bind_context, get_logger
from app.core.security import require_api_key
from app.schemas.ec.response import EcReviewOut
from app.schemas.wr.response import (
    ReviewFullOut,
    ReviewJobResultOut,
    ReviewJobStartOut,
)
from app.schemas.wr.values import WorkplaceContext
from app.services.ai.wr.dispatch import (
    _dispatch_review,
    _parse_worker_types,
    _run_employment_contract,
    _run_work_rules,
    _to_bool,
)

log = get_logger(__name__)

router = APIRouter(tags=["review"])


@router.post(
    "",
    response_model=ReviewFullOut | EcReviewOut,
    summary="사업장 문서 검토 (취업규칙·근로계약서)",
    description=(
        "`document_type` 으로 분기:\n"
        "- `work_rules` (기본): 취업규칙 → 5-Bucket (누락·위반·주의·검토필요·적정)\n"
        "- `employment_contract`: 근로계약서 → 3-Bucket (적절·보완필요·부적절)\n\n"
        "사업장 정보 폼은 통합 — 각 문서가 자기에게 필요한 필드만 사용.\n"
        "- 취업규칙: shift_work·osha·chemical·workenv\n"
        "- 근로계약서: business_size·worker_types"
    ),
    dependencies=[Depends(require_api_key)],
)
async def post_review(
    file: UploadFile = File(..., description="검토 대상 파일 (.docx/.hwp/.hwpx/.pdf/.txt)"),
    document_type: str = Form(
        default="work_rules",
        description="문서 종류: 'work_rules' | 'employment_contract'",
    ),
    # 취업규칙용
    shift_work_used: str | None = Form(default=None, description="교대근로 도입: 'true'/'false'/null"),
    osha_applicable: str | None = Form(default="true", description="산안법 적용 업종"),
    chemical_handling: str | None = Form(default=None, description="화학물질 취급"),
    workenv_measurement: str | None = Form(default=None, description="작업환경측정 대상"),
    # 근로계약서용
    business_size: str | None = Form(
        default=None,
        description="사업장 규모: '5+' / '5-' / 'any' / null",
    ),
    worker_types: str | None = Form(
        default=None,
        description="근로자 유형 콤마 구분: '정규직,기간제,단시간,일용직,연소자,외국인'",
    ),
    summary_only: bool = Form(default=False, description="true면 finding 상세 제외하고 summary 만"),
):
    # ── 임시 파일 저장
    suffix = Path(file.filename or "upload.bin").suffix
    if not suffix:
        suffix = ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
        content = await file.read()
        tf.write(content)
        tmp_path = Path(tf.name)

    # ── 사업장 컨텍스트 (통합 폼)
    bs = business_size if business_size in ("5+", "5-", "any") else None
    context = WorkplaceContext(
        shift_work_used=_to_bool(shift_work_used),
        osha_applicable=_to_bool(osha_applicable) if osha_applicable else True,
        chemical_handling=_to_bool(chemical_handling),
        workenv_measurement=_to_bool(workenv_measurement),
        business_size=bs,
        worker_types=_parse_worker_types(worker_types),
    )

    # ── document_type 분기
    try:
        if document_type == "employment_contract":
            return _run_employment_contract(tmp_path, file.filename or "", context)
        else:
            return _run_work_rules(tmp_path, file.filename or "", context, summary_only)
    finally:
        # 임시 파일 정리
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception as e:
            log.warning("무시된 예외 — %s: %s", type(e).__name__, e)

@router.post(
    "/start",
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
        return _dispatch_review(
            tmp_path, filename, document_type, context, summary_only, case_id
        )

    job_id = jobs.start_job(_do)
    return ReviewJobStartOut(job_id=job_id)

@router.get(
    "/result/{job_id}",
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
