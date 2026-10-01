"""EC 표준 계약서 생성 서비스 — 원본 `cgr/ec/services/generate.py:run` 이관.

===============================================================================
원본 이관
===============================================================================
원본
- 입력: analysis_result (33-매핑 결과) + user_overrides (사용자 편집)
- 시스템 프롬프트: ec::GENERATION_PROMPT (고용노동부 표준 양식, 최저시급 보정 규칙 등)
- LLM 이 표준 계약서 본문 텍스트 생성 (순수 텍스트 · JSON 아님)

변경점
- `OpenAI(...)` → `get_llm_client().chat(...)` (재시도·PII·캐시 어댑터)
- `prompts.get_generation_prompt()` → `resolve_prompt(conn, "ec::GENERATION_PROMPT")`
- `prompts.build_generate_user_prompt` → `prompt_builders.build_generate_user_prompt`
  · user_overrides 를 별도 섹션으로 강조하는 원본 정책 유지
- `mask_pii_in_payload(analysis_result / user_overrides)` PII 게이트
- 빈 응답 시 `LLMError` (원본 RuntimeError → v2 도메인 예외)
"""
from __future__ import annotations

import time

import psycopg

from app.core.exceptions import LLMError, ValidationError
from app.core.security import mask_pii_in_payload
from app.integrations.llm.cache import make_cache_key
from app.integrations.llm.client import get_llm_client
from app.integrations.llm.prompts import resolve_prompt
from app.schemas.ec.requests import GenerateIn
from app.schemas.ec.responses import GenerateOut
from app.services.ec.prompt_builders import build_generate_user_prompt

_PROMPT_KEY = "ec::GENERATION_PROMPT"
_PROMPT_VERSION = "v1"


class GenerateService:
    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db

    def run(self, payload: GenerateIn) -> GenerateOut:
        if not isinstance(payload.analysis_result, dict):
            raise ValidationError("analysis_result 가 dict 가 아닙니다.")

        # PII 게이트 — 중첩 dict 전체 마스킹
        analysis = mask_pii_in_payload(payload.analysis_result)
        overrides = (
            mask_pii_in_payload(payload.user_overrides)
            if payload.user_overrides
            else None
        )

        client = get_llm_client()
        system = resolve_prompt(self.db, _PROMPT_KEY)
        user = build_generate_user_prompt(analysis, user_overrides=overrides)
        cache_key = make_cache_key(_PROMPT_KEY, _PROMPT_VERSION, system, user)

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

        text = (resp.get("content") or "").strip()
        if not text:
            raise LLMError("표준 계약서 생성 응답이 비어 있습니다.")

        return GenerateOut(
            contract_text=text,
            elapsed_sec=round(elapsed, 3),
            model=resp.get("model", ""),
        )
