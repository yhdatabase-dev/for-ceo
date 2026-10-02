"""근로계약서 후속 챗봇."""
from __future__ import annotations

import time

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from app.core.config import get_llm_model
from app.core.security import require_api_key
from app.schemas.ec.request import ChatIn
from app.schemas.ec.response import ChatOut
from app.services.ai.ec import chat as chat_service

router = APIRouter(tags=["employment_contract"])


@router.post(
    "/chat",
    response_model=ChatOut,
    summary="근로계약서 검토 결과 기반 대화형 후속 질문",
    description=(
        "사용자가 결과 페이지에서 본 항목에 대해 자연어로 후속 질문을 던지면,\n"
        "분석 결과 + 이전 대화 + 사용자가 본 항목을 컨텍스트로 LLM 이 답변."
    ),
    dependencies=[Depends(require_api_key)],
)
def post_chat(body: ChatIn):
    t0 = time.time()
    try:
        answer = chat_service.run(
            body.message,
            analysis_result=body.analysis_result,
            focused_item=body.focused_item,
            history=[
                {"role": h.role, "content": h.content} for h in body.history
            ],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"챗봇 호출 실패: {type(e).__name__}: {e}",
        )
    return ChatOut(
        answer=answer,
        elapsed_sec=round(time.time() - t0, 2),
        model=get_llm_model(),
    )
