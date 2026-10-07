#
# 근로계약서 단일 항목 재검토.
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.10.02      이시영      최초 생성 (구조 이행 — 기존 backend/cgr 코드를 분리·이동)
# 2026.10.02      이시영      구조 조정 (web/ai 파트 디렉터리 → 도메인 단일 디렉터리)
# 2026.10.06      이시영      API 경로 표준화 (/api/cgr)
# 2026.10.07      이시영      검토번호 서버 발급, 변경 사유 주석 추가
#
# Author: 이시영
# Since: 2026.10.02
#
"""근로계약서 단일 항목 재검토."""
from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from app.core.security import require_api_key
from app.schemas.ec.request import ValidateFieldIn
from app.schemas.ec.response import ValidateFieldOut
from app.services.ec import validate_field as validate_field_service

# 프로그램명세서 AI-P02-006: POST /api/cgr/ec/field-validations (기존: /api/v1/ec/validate-field)
router = APIRouter(tags=["employment_contract"])


@router.post(
    "/field-validations",
    response_model=ValidateFieldOut,
    summary="근로계약서 단일 항목 즉시 재검토 (칸 편집 후 점 갱신용)",
    dependencies=[Depends(require_api_key)],
)
def post_validate_field(body: ValidateFieldIn) -> ValidateFieldOut:
    try:
        out = validate_field_service.validate_field(
            body.field,
            body.value,
            business_size=body.business_size,
            worker_types=body.worker_types,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"항목 재검토 실패: {type(e).__name__}: {e}",
        )
    return ValidateFieldOut(적절성=out.get("적절성", "보완필요"), 이유=out.get("이유", ""))
