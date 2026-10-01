"""EC 챗봇 서비스 — 원본 `cgr/ec/services/chat.py:run` 이관.

===============================================================================
원본 이관
===============================================================================
원본
- 입력: user_message, analysis_result?, focused_item?, history?
- 시스템 프롬프트: ec_chat_base + ANALYSIS_PROMPT STEP2~3 매핑 concat (`get_chat_system_prompt`)
- user 프롬프트: build_chat_user_prompt (분석 결과 요약·focused_item 매핑 topics·이전 대화)
- LLM (temp=0) → 답변 텍스트

변경점
- `OpenAI(...)` → `get_llm_client().chat(...)`
- `prompts.get_chat_system_prompt()` → `compose_chat_system_prompt(chat_base, analysis_prompt)`
  두 프롬프트 모두 `resolve_prompt(db, ...)` 로 조회
- `prompts.build_chat_user_prompt` → `prompt_builders.build_chat_user_prompt`
- PII 게이트 — 사용자 질문 / analysis_result / history 모두 마스킹
- 감사 로그 `InteractionLogRepo.log(kind='근로계약서')`
"""
from __future__ import annotations

import time

import psycopg

from app.core.exceptions import LLMError, ValidationError
from app.core.logging import get_logger
from app.core.security import mask_pii_in_payload, mask_pii_text
from app.integrations.llm.cache import make_cache_key
from app.integrations.llm.client import get_llm_client
from app.integrations.llm.prompts import resolve_prompt
from app.repositories.shared import InteractionLogRepo
from app.schemas.ec.requests import ChatIn
from app.schemas.ec.responses import ChatOut
from app.services.ec.prompt_builders import (
    build_chat_user_prompt,
    compose_chat_system_prompt,
)

log = get_logger(__name__)

_PROMPT_VERSION = "v1"


class ChatService:
    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db
        self.log_repo = InteractionLogRepo(db)

    def run(self, payload: ChatIn, *, visitor: str | None = None) -> ChatOut:
        message = (payload.message or "").strip()
        if not message:
            raise ValidationError("메시지가 비어 있습니다.")

        # PII 게이트
        masked_message = mask_pii_text(message)
        masked_analysis = (
            mask_pii_in_payload(payload.analysis_result)
            if payload.analysis_result
            else None
        )
        masked_history = (
            [
                {"role": t.role, "content": mask_pii_text(t.content)}
                for t in payload.history
            ]
            if payload.history
            else None
        )

        # 시스템 프롬프트 조립 = chat_base + ANALYSIS_PROMPT STEP2~3 매핑
        chat_base = resolve_prompt(self.db, "ec_chat_base")
        analysis_prompt = resolve_prompt(self.db, "ec::ANALYSIS_PROMPT")
        system = compose_chat_system_prompt(chat_base, analysis_prompt)

        user = build_chat_user_prompt(
            masked_message,
            analysis_result=masked_analysis,
            focused_item=payload.focused_item,
            history=masked_history,
            conn=self.db,
        )

        cache_key = make_cache_key(
            "ec_chat", _PROMPT_VERSION, system, user
        )

        client = get_llm_client()
        t0 = time.perf_counter()
        resp = client.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            cache_key=cache_key,
        )
        elapsed = time.perf_counter() - t0

        answer = (resp.get("content") or "").strip()
        if not answer:
            raise LLMError("EC 챗봇 응답이 비어 있습니다.")

        try:
            self.log_repo.log(
                kind="근로계약서",
                model=resp.get("model", ""),
                input_text=masked_message,
                output_text=answer,
                visitor=visitor,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("ec.chat.audit_log 실패: %s", e)

        return ChatOut(
            answer=answer,
            elapsed_sec=round(elapsed, 3),
            model=resp.get("model", ""),
        )
