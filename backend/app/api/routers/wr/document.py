"""취업규칙 수정본·신구대조표 → Word(.docx) 다운로드."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.core.security import require_api_key
from app.integrations.docx_export import (
    DOCX_MIMETYPE,
    text_to_docx,
    wr_comparison_to_docx,
)
from app.schemas.wr.request import ComparisonDocxIn, GenerateDocxIn

router = APIRouter(tags=["review"])


@router.post(
    "/revision-documents",
    summary="취업규칙 수정본 본문 → .docx 변환·다운로드",
    description="수정본 본문을 .docx 로 변환. 한글 폰트(맑은 고딕)·A4·표준 여백.",
    dependencies=[Depends(require_api_key)],
    response_class=Response,
)
def post_generate_docx(body: GenerateDocxIn):
    try:
        docx_bytes = text_to_docx(
            body.contract_text,
            title="취업규칙 수정본",
            subtitle="영세사업장 자율점검 서비스 — 사용자 확정 수정안 반영",
            footer_note=(
                "※ 본 문서는 AI 자율점검 결과를 반영한 수정본입니다. "
                "법적 효력은 사업장·노무사 검토 후 확정됩니다."
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"docx 변환 실패: {type(e).__name__}: {e}",
        )
    # 한글 파일명 — RFC 6266 (filename*=UTF-8) 방식
    from urllib.parse import quote

    fname_quoted = quote(body.filename, safe="")
    headers = {
        "Content-Disposition": (
            f"attachment; filename=\"document.docx\"; "
            f"filename*=UTF-8''{fname_quoted}"
        ),
    }
    return Response(
        content=docx_bytes,
        media_type=DOCX_MIMETYPE,
        headers=headers,
    )

@router.post(
    "/comparison-documents",
    summary="취업규칙 신구대조표(표) + 의견청취서 → .docx 다운로드",
    description="신구대조표를 깨지지 않는 3열 표로 출력하고, 뒤에 의견청취서 양식을 함께 첨부.",
    dependencies=[Depends(require_api_key)],
    response_class=Response,
)
def post_comparison_docx(body: ComparisonDocxIn):
    try:
        docx_bytes = wr_comparison_to_docx(
            body.rows,
            effective_date=body.effective_date,
            footer_note=(
                "※ 본 신구대조표는 AI 자율점검 결과를 반영한 개정안입니다. "
                "시행은 의견청취·동의 등 법정 절차를 거쳐 확정하세요."
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"docx 변환 실패: {type(e).__name__}: {e}",
        )
    from urllib.parse import quote

    fname_quoted = quote(body.filename, safe="")
    headers = {
        "Content-Disposition": (
            f"attachment; filename=\"comparison.docx\"; "
            f"filename*=UTF-8''{fname_quoted}"
        ),
    }
    return Response(content=docx_bytes, media_type=DOCX_MIMETYPE, headers=headers)
