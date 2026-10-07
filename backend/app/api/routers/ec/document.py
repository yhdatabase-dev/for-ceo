#
# 근로계약서 본문 → Word(.docx) 다운로드.
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
"""근로계약서 본문 → Word(.docx) 다운로드."""
from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from fastapi.responses import Response

from app.core.security import require_api_key
from app.integrations.docx_export import DOCX_MIMETYPE, text_to_docx
from app.schemas.ec.request import GenerateDocxIn

# 프로그램명세서 WEB-P02-004: POST /api/cgr/ec/documents (기존: /api/v1/ec/generate-docx)
router = APIRouter(tags=["employment_contract"])


@router.post(
    "/documents",
    summary="평문 본문 → .docx 변환·다운로드",
    description="사용자가 편집한 계약서 본문을 .docx 로 변환. 한글 폰트·A4·표준 양식.",
    dependencies=[Depends(require_api_key)],
    response_class=Response,
)
def post_generate_docx(body: GenerateDocxIn):
    try:
        docx_bytes = text_to_docx(
            body.contract_text,
            title="표준 근로계약서",
            subtitle="영세사업장 자율점검 서비스 — AI 기반 시정안 반영",
            footer_note=(
                "※ 본 문서는 AI 자율점검 결과를 반영한 표준안입니다. "
                "법적 효력은 사업장·노무사 검토 후 확정됩니다."
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
            f"attachment; filename=\"document.docx\"; "
            f"filename*=UTF-8''{fname_quoted}"
        ),
    }
    return Response(
        content=docx_bytes,
        media_type=DOCX_MIMETYPE,
        headers=headers,
    )
