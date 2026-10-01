"""EC 단일 항목 재검토 서비스 — 원본 `cgr/ec/services/validate_field.py:validate_field` 이관.

===============================================================================
원본 이관
===============================================================================
원본
- 입력: (field, value, business_size, worker_types)
- 출력: {"적절성": "적절"|"보완필요"|"부적정", "이유": "...", "작성예시": "..."}
- LLM: 항목 1개만 재판정 (전체 33 매핑 재분석 X · 빠름)

변경점
- `OpenAI(...)` 직접 → `get_llm_client().chat(...)` (재시도·PII·캐시 어댑터)
- 프롬프트 상수 → `resolve_prompt(conn, "ec_validate_field")`
- PII 마스킹: `mask_pii_text(value)` — value 만 (field 는 시스템 필드명)
- 빈 field 방어 (원본과 동일)
- 적절 시 작성예시 비우기 (원본 정책)
- 적절성 값 검증 — 허용 외 값은 "보완필요" 로 (원본과 동일)
"""
from __future__ import annotations

import psycopg

from app.core.security import mask_pii_text
from app.integrations.llm.cache import make_cache_key
from app.integrations.llm.client import get_llm_client
from app.integrations.llm.prompts import resolve_prompt
from app.schemas.ec.requests import ValidateFieldIn
from app.schemas.ec.responses import ValidateFieldOut
from app.utils.json_repair import safe_json_parse

_PROMPT_KEY = "ec_validate_field"
_PROMPT_VERSION = "v2"
_ALLOWED_VERDICTS = {"적절", "보완필요", "부적정"}


class ValidateFieldService:
    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db

    def run(self, payload: ValidateFieldIn) -> ValidateFieldOut:
        field = (payload.field or "").strip()
        value = mask_pii_text((payload.value or "").strip())
        worker_types = payload.worker_types or []
        business_size = payload.business_size or ""

        if not field:
            return ValidateFieldOut(
                적절성="보완필요",
                이유="항목명이 비어 있습니다.",
                작성예시="",
            )

        client = get_llm_client()
        system = resolve_prompt(self.db, _PROMPT_KEY)
        types_line = (
            " · 유형 " + ", ".join(worker_types) if worker_types else ""
        )
        user = (
            f"[항목] {field}\n"
            f"[입력값] {value or '(빈칸)'}\n"
            f"[사업장] 상시근로자 {business_size or '미상'}{types_line}\n\n"
            "위 항목의 입력값이 근로기준법상 적정한지 판정하세요. "
            "빈칸이거나 법정 필수 내용(예: 기간·시간·금액·구체 조건)이 빠졌으면 "
            "'부적정' 또는 '보완필요' 로 판정합니다."
        )

        cache_key = make_cache_key(_PROMPT_KEY, _PROMPT_VERSION, system, user)
        resp = client.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            cache_key=cache_key,
        )

        parsed = safe_json_parse(resp.get("content") or "", default={}) or {}
        verdict = str(parsed.get("적절성") or "").strip()
        if verdict not in _ALLOWED_VERDICTS:
            verdict = "보완필요"
        reason = str(parsed.get("이유") or "").strip()
        example = str(parsed.get("작성예시") or "").strip()
        if verdict == "적절":
            example = ""

        return ValidateFieldOut(
            적절성=verdict,
            이유=reason,
            작성예시=example,
        )
