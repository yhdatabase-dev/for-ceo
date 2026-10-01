"""프롬프트 조회 게이트웨이 — DB override → 코드 default 폴백 (psycopg raw SQL).

호출:
    from app.integrations.llm.prompts import resolve_prompt

    system = resolve_prompt(conn, "wr_extractor")

정책
- DB `cgr_admin.prompt` 에 key 존재 + is_override=TRUE → DB 내용
- 없거나 is_override=FALSE → 코드 default (도메인별 DEFAULT_PROMPTS)
- 코드 default 도 없으면 KeyError
"""
from __future__ import annotations

import psycopg

from app.integrations.llm.prompts.ec import DEFAULT_PROMPTS as EC_DEFAULTS
from app.integrations.llm.prompts.guide import DEFAULT_PROMPTS as GUIDE_DEFAULTS
from app.integrations.llm.prompts.review import DEFAULT_PROMPTS as REVIEW_DEFAULTS


_DEFAULTS: dict[str, str] = {}
_DEFAULTS.update(REVIEW_DEFAULTS)
_DEFAULTS.update(EC_DEFAULTS)
_DEFAULTS.update(GUIDE_DEFAULTS)


def resolve_prompt(conn: psycopg.Connection, key: str) -> str:
    """프롬프트 본문 조회."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT content, is_override
              FROM cgr_admin.prompt
             WHERE key = %s
            """,
            (key,),
        )
        row = cur.fetchone()
    if row and row["is_override"]:
        return row["content"]
    if key in _DEFAULTS:
        return _DEFAULTS[key]
    raise KeyError(f"프롬프트 default 없음: {key}")


def list_prompt_keys() -> list[str]:
    """등록된 default 프롬프트 키 목록."""
    return sorted(_DEFAULTS.keys())


def get_default(key: str) -> str | None:
    return _DEFAULTS.get(key)
