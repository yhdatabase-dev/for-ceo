"""guide 챗봇 서비스 — 원본 `cgr/api/routes/guide.py:post_guide_chat` v2 이관.

===============================================================================
원본 이관
===============================================================================
원본
- 라우터 안에 OpenAI 클라이언트·llm_cache·프롬프트·SQL 조회·후처리 모두 인라인 (~350줄).

v2
- 라우터는 얇게 → 이 서비스가 오케스트레이션.
- LLM 호출: `get_llm_client().chat(...)` (PII·캐시 어댑터 내장)
- 프롬프트: `resolve_prompt(conn, "guide_chat")` (DB override → 코드 default)
- RAG · 서식 감지 · 후속 질문 · 낙인 정제: `chat_helpers.py` 로 분리
- 감사 로그: `InteractionLogRepo.log()`

원본 UX·정책과 100% 동일:
- 최근 6턴 히스토리 사용
- 컨텍스트에 낙인 표현 정제 후 주입 (LLM 이 echo 못 하게)
- 응답에서 [추천질문] 블록 분리 → follow_ups
- 응답 본문에도 낙인 표현 정제 (LLM 미준수 방어)
- 질문(question) 기반 서식 감지 → related_forms + clarify
"""
from __future__ import annotations

import time

import psycopg

from app.core.exceptions import LLMError, ValidationError
from app.core.logging import get_logger
from app.integrations.llm.cache import make_cache_key
from app.integrations.llm.client import get_llm_client
from app.integrations.llm.prompts import resolve_prompt
from app.repositories.shared import InteractionLogRepo
from app.schemas.guide.requests import GuideChatIn
from app.schemas.guide.responses import GuideChatOut
from app.services.guide.chat_helpers import (
    detect_related_forms,
    extract_followups,
    sanitize_sanctions,
    search_guide_context,
)

log = get_logger(__name__)

_NO_CTX_HINT = (
    "[가이드 DB 컨텍스트] (사용자 질문과 직접 매칭되는 자료가 없음 — 일반 "
    "노동법 상식으로 답하되 마지막에 '관할 고용센터 상담 권장' 안내)"
)


class GuideChatService:
    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db
        self.log_repo = InteractionLogRepo(db)

    def chat(
        self,
        payload: GuideChatIn,
        *,
        visitor: str | None = None,
    ) -> GuideChatOut:
        """가이드 챗봇 응답 생성."""
        msg = (payload.message or "").strip()
        if not msg:
            raise ValidationError("질문이 비어있어요.")

        # 1) 가이드 DB 검색 → 컨텍스트 조립 (+ 낙인 정제 후 주입)
        ctx_text, sources = search_guide_context(self.db, msg)
        ctx_text = sanitize_sanctions(ctx_text)

        # 2) 최근 6턴 히스토리
        hist_lines: list[str] = []
        if payload.history:
            for h in payload.history[-6:]:
                role = h.role if h.role in ("user", "assistant") else "user"
                hist_lines.append(f"- {role}: {h.content[:600]}")

        # 3) user 프롬프트 조립
        user_parts: list[str] = []
        if ctx_text:
            user_parts.append("[가이드 DB 컨텍스트 — 1차 근거로 사용]\n" + ctx_text)
        else:
            user_parts.append(_NO_CTX_HINT)
        if hist_lines:
            user_parts.append("[최근 대화]\n" + "\n".join(hist_lines))
        user_parts.append(f"[사용자 질문]\n{msg}")
        user_prompt = "\n\n".join(user_parts)

        # 4) LLM 호출
        system_prompt = resolve_prompt(self.db, "guide_chat")
        cache_key = make_cache_key(
            "guide_chat", "v1", system_prompt, user_prompt
        )
        client = get_llm_client()

        t0 = time.perf_counter()
        try:
            resp = client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                cache_key=cache_key,
            )
        except LLMError:
            raise
        elapsed = time.perf_counter() - t0

        raw_answer = (resp.get("content") or "").strip()

        # 5) 후속 질문 추출 + 본문 낙인 정제
        body, follow_ups = extract_followups(raw_answer)
        body = sanitize_sanctions(body)

        # 6) 관련 서식 감지 (질문 기반)
        related_forms, clarify = detect_related_forms(self.db, msg, body)
        if clarify:
            # clarify 는 본문 말미에 붙임 (원본 정책)
            body = f"{body}\n\n{clarify}"

        # 7) 감사 로그
        try:
            self.log_repo.log(
                kind="챗봇",
                model=resp.get("model", ""),
                input_text=msg,
                output_text=body,
                visitor=visitor,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("guide.chat.audit_log 실패: %s", e)

        return GuideChatOut(
            answer=body,
            matched_sources=sources,
            follow_ups=follow_ups,
            related_forms=related_forms,
            elapsed_sec=round(elapsed, 3),
            model=resp.get("model", ""),
        )
