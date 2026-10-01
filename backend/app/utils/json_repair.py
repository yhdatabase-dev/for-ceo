"""LLM 응답 JSON 복구 유틸 — 원본 `cgr/ec/prompts.py` 의 3개 함수 이관.

원본
- clean_json_response(text)  L364 — ```json fence 제거
- _repair_truncated_json(s)  L393 — 잘린 JSON 복구 시도
- safe_json_parse(text, default) L446 — 위 둘 조합 + json.loads 실패 시 default

이 함수들은 LLM 답변 자체를 다루는 순수 함수이므로 utils.
"""
from __future__ import annotations

import json
import re
from typing import Any


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def clean_json_response(text: str) -> str:
    """LLM 응답에서 ```json ...``` 펜스만 뽑아냄. 없으면 원본 반환."""
    if not text:
        return ""
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def _repair_truncated_json(s: str) -> str:
    """잘린 JSON 을 최대한 파싱 가능하게 복구.

    원본 로직 이관 예정. 지금은 아주 간단한 브래킷 자동 닫기만.
    TODO: 원본 로직 이관.
    """
    s = s.strip()
    # 여는 괄호와 닫는 괄호 카운트 맞춤
    opens = s.count("{") - s.count("}")
    if opens > 0:
        s = s + "}" * opens
    opens = s.count("[") - s.count("]")
    if opens > 0:
        s = s + "]" * opens
    return s


def safe_json_parse(text: str, default: Any) -> Any:
    """LLM 답변 → JSON 파싱. 실패해도 default 반환 (예외 X).

    호출자는 default 를 반드시 제공해야 함 (실패 시 폴백).
    """
    if not text:
        return default
    cleaned = clean_json_response(text)
    for candidate in (cleaned, _repair_truncated_json(cleaned)):
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
    return default
