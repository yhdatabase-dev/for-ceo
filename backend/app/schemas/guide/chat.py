"""노무 가이드(guide) 챗봇 요청·응답 스키마."""
from __future__ import annotations

from pydantic import BaseModel, Field  # noqa: E402


class GuideChatTurn(BaseModel):
    role: str = Field(..., description="user 또는 assistant")
    content: str

class GuideChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[GuideChatTurn] | None = None

class RelatedFormHint(BaseModel):
    code: str
    form_name: str
    category: str
    audience: str
    has_local: bool
    purpose: str = ""

class GuideChatOut(BaseModel):
    answer: str
    matched_sources: list[str] = Field(
        default_factory=list,
        description="컨텍스트로 사용된 가이드 카테고리 (사용자 신뢰용)",
    )
    follow_ups: list[str] = Field(
        default_factory=list,
        description="이어서 물어볼만한 후속 질문 (사업주 자율점검 범위, 답변 컨텍스트 인지)",
    )
    related_forms: list[RelatedFormHint] = Field(
        default_factory=list,
        description="질문·답변에 등장한 주제와 관련된 사업주용 서식 (다운로드 chip 노출)",
    )
    clarify: str | None = Field(
        default=None,
        description="여러 변형 서식이 매칭된 경우 사용자에게 한 번 더 묻는 질문 (예: '어떤 유형의 근로계약서인가요?'). 없으면 null.",
    )
