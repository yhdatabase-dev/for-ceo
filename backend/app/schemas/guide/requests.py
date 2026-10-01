"""guide 도메인 요청 DTO — 프론트가 보내는 body/query 계약.

원본 매핑
- `POST /guide/chat`   → GuideChatIn  (원본 cgr/api/routes/guide.py:918)
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class GuideChatTurn(BaseModel):
    """대화 히스토리 한 턴."""

    role: str = Field(..., description="user | assistant")
    content: str


class GuideChatIn(BaseModel):
    """`POST /guide/chat` 요청."""

    message: str = Field(..., description="사용자 질문 (자연어)")
    history: list[GuideChatTurn] = Field(
        default_factory=list,
        description="이전 대화 (최근 6턴까지만 활용)",
    )
