#
# 취업규칙 수정본·신구대조표 → Word(.docx) 다운로드.
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

# 프로그램명세서 WEB-P03-004: POST /api/cgr/wr/comparison-documents (기존: /api/v1/review/comparison-docx)
# 개발표준정의서 API 엔드포인트: /api/cgr/<도메인>/<리소스> — 복수형 케밥, 동사·버전 금지 — 수정본 Word 는 /revision-documents (기존: /api/v1/review/generate-docx)
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
