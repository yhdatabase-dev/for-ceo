"""guide 도메인 내부 VO — 챗봇 파이프라인 전용.

DTO 와 달리 프론트가 모름. 리팩·필드추가 자유.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatContextChunk(BaseModel):
    """`_search_guide_context()` 가 반환하는 매칭 조각.

    원본 `cgr/api/routes/guide.py:_search_guide_context` L620 의 dict 형태를 VO 로.
    """

    source_table: str          # guide_item / obligation_timeline / ... 어느 테이블
    source_id: int | str       # 매칭된 row id
    text: str                  # LLM 컨텍스트로 넘길 요약 텍스트
    weight: float = 1.0        # 랭킹 가중치


class ChatContext(BaseModel):
    """챗봇 최종 프롬프트에 첨부되는 컨텍스트 묶음."""

    query: str                                 # 정규화된 질문
    chunks: list[ChatContextChunk] = Field(default_factory=list)
    related_form_codes: list[str] = Field(default_factory=list)


class ChatRawResponse(BaseModel):
    """LLM 원본 응답 + 파싱 결과 (라우터엔 절대 노출 X)."""

    raw_text: str                              # LLM 원본
    answer: str                                # 정제된 답변
    follow_ups: list[str] = Field(default_factory=list)
    matched_sources: list[str] = Field(default_factory=list)
    model: str = ""
    elapsed_sec: float = 0.0
    cache_hit: bool = False
