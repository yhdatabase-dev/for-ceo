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

router = APIRouter(tags=["employment_contract"])


@router.post(
    "/validate-field",
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
