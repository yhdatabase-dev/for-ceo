"""분석 결과 → 표준 근로계약서 텍스트 (LLM).

기존 `server/services/openaiService.js#generateLegalContract` 를 옮긴 것.
- system: GENERATION_PROMPT (고용노동부 표준 양식, 최저시급 보정 규칙 등 포함)
- user:   build_generate_user_prompt(analysis_result)
- 출력: 순수 텍스트 (HTML/JSON 아님) — 다운로드용 표준 계약서 본문

호출자(라우터)는 받은 텍스트를 `text/plain` 으로 반환하거나
저장·다운로드용 파일로 가공한다.
"""
from __future__ import annotations

import time
from typing import Any

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from app.services.ec import prompts
from app.integrations.llm import cache as llm_cache
from app.core.config import get_api_key, get_llm_model
from app.core.pii_mask import mask_pii_in_payload


_CALL_TIMEOUT = 120.0
_MAX_RETRIES = 3
_RETRY_BACKOFF = (2.0, 5.0, 10.0)


def run(
    analysis_result: dict[str, Any],
    *,
    user_overrides: dict[str, str] | None = None,
    model: str | None = None,
) -> str:
    """분석 결과 → 표준 근로계약서 텍스트.

    `user_overrides` (항목명 → 사용자 직접 작성한 보완 표현) 는 generation 프롬프트의
    별도 섹션으로 전달되어 LLM 이 해당 항목을 사용자 표현 그대로 사용하도록 유도.

    실패 시 빈 문자열을 반환하지 않고 raise. 호출자는 HTTP 500 처리.
    """
    if not isinstance(analysis_result, dict):
        raise ValueError("analysis_result 가 dict 가 아닙니다.")

    # PII 비식별 게이트
    analysis_result = mask_pii_in_payload(analysis_result)
    if user_overrides:
        user_overrides = mask_pii_in_payload(user_overrides)  # type: ignore[assignment]

    model_name = get_llm_model(model)
    sys_prompt = prompts.get_generation_prompt()
    user_prompt = prompts.build_generate_user_prompt(
        analysis_result, user_overrides=user_overrides
    )

    cache_key = llm_cache.make_key(
        system=sys_prompt,
        user=user_prompt,
        schema={"kind": "ec_generate"},
        model=model_name,
    )
    cached = llm_cache.get(cache_key)
    if cached is not None and isinstance(cached.get("contract_text"), str):
        return cached["contract_text"]

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
                raise RuntimeError("generation 응답이 비어 있습니다.")
            llm_cache.put(cache_key, {"contract_text": text})
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

    raise RuntimeError(f"generation 호출 실패: {last_err}")
