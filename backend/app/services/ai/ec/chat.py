"""근로계약서 대화형 챗봇 (SFR-001).

검토 결과를 본 사용자가 후속 질문을 자연어로 던지면, 분석 결과 컨텍스트 +
이전 대화 + 사용자 질문을 묶어 LLM 에 던지고 친근한 답변을 받아온다.

- system: CHAT_SYSTEM_PROMPT
- user:   build_chat_user_prompt(...)
- 출력: 답변 텍스트 (마크다운 허용, 프론트가 plain rendering)

결정성: temperature=0, top_p=1. 캐싱: llm_cache 활용 — 같은 질문+컨텍스트면 즉시 반환.
"""
from __future__ import annotations

import time
from typing import Any

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from app.services.ai.ec import prompts
from app.integrations.llm import cache as llm_cache
from app.core.config import get_api_key, get_llm_model
from app.core.pii_mask import mask_pii_in_payload, mask_pii_text


_CALL_TIMEOUT = 60.0
_MAX_RETRIES = 3
_RETRY_BACKOFF = (2.0, 5.0, 10.0)


def run(
    user_message: str,
    *,
    analysis_result: dict[str, Any] | None = None,
    focused_item: str | None = None,
    history: list[dict[str, str]] | None = None,
    model: str | None = None,
) -> str:
    """단일 사용자 질문에 대한 답변 텍스트."""
    if not user_message or not user_message.strip():
        raise ValueError("user_message 가 비어 있습니다.")

    # PII 비식별 게이트 — 사용자 질문 + 분석 결과 + 이전 대화 모두 마스킹
    user_message = mask_pii_text(user_message)
    if analysis_result:
        analysis_result = mask_pii_in_payload(analysis_result)
    if history:
        history = mask_pii_in_payload(history)  # type: ignore[assignment]

    model_name = get_llm_model(model)
    # 동적 빌더 — base 톤 + ANALYSIS_PROMPT 의 33-매핑 STEP 2~3 자동 포함
    sys_prompt = prompts.get_chat_system_prompt()
    user_prompt = prompts.build_chat_user_prompt(
        user_message,
        analysis_result=analysis_result,
        focused_item=focused_item,
        history=history,
    )

    cache_key = llm_cache.make_key(
        system=sys_prompt,
        user=user_prompt,
        schema={"kind": "ec_chat"},
        model=model_name,
    )
    cached = llm_cache.get(cache_key)
    if cached and isinstance(cached.get("text"), str):
        return cached["text"]

    client = OpenAI(api_key=get_api_key(), timeout=_CALL_TIMEOUT)
    last_err: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                top_p=1,
            )
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                raise RuntimeError("chat 응답이 비어 있습니다.")
            llm_cache.put(cache_key, {"text": text})
            return text
        except (APITimeoutError, APIConnectionError, RateLimitError) as e:
            last_err = e
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_BACKOFF[attempt])
                continue
            raise
        except Exception as e:
            last_err = e
            raise

    raise RuntimeError(f"chat 호출 실패: {last_err}")
