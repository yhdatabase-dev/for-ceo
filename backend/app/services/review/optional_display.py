"""선택 조 디스플레이 (LLM 버전) — 검사 없이 참고 정보만 사용자에게 표시.

===============================================================================
원본 이관
===============================================================================
원본: `cgr/optional_display.py` → v2 로 이관.

변경점
- `cgr.master_db.MasterDB` 직접 의존 → **시그니처를 `articles: list[OptionalArticleSpec]`**
  로 바꿔 repository 결합 제거 (호출자가 카탈로그에서 로드해 전달).
- `cgr.models.OptionalDisplay` → `OptionalDisplayVO`
- `cgr.prompt_store` + inline default → `resolve_prompt(conn, "optional_display")`
- `OpenAI(...)` → `get_llm_client()`  (PII·캐시 어댑터 내장)
- 로직·batch 크기·스키마·필터 규칙(excluded/required 제외) 은 원본과 동일

※ 현재 v2 오케스트레이션에서는 임베딩 버전(`optional_display_emb`)이 기본 —
   이 파일은 LLM fallback 이 필요할 때 사용 (원본에서도 이미 대체됨).
"""
from __future__ import annotations

import json
from typing import Any, TypedDict

import psycopg

from app.core.logging import get_logger
from app.integrations.llm.cache import make_cache_key
from app.integrations.llm.client import LLMClient, get_llm_client
from app.integrations.llm.prompts.resolver import resolve_prompt
from app.schemas.review.values import OptionalDisplayVO

log = get_logger(__name__)


class OptionalArticleSpec(TypedDict, total=False):
    """호출자가 준비하는 선택 조 명세.

    원본 MasterDB 의 title/body/_cell(guide)/note/article(scope)/is_required 를
    v2 리포지토리가 미리 로드해 이 dict 리스트로 전달.
    """

    article: int
    title: str
    body: str
    guide: str
    note: str
    scope: str
    required: bool   # True 면 이 함수가 자동 필터 (선택만 남김)


def build_optional_displays(
    conn: psycopg.Connection,
    document_text: str,
    articles: list[OptionalArticleSpec],
    *,
    excluded_articles: set[int] | None = None,
    model: str | None = None,
    batch_size: int = 30,
) -> list[OptionalDisplayVO]:
    """선택(또는 미정)으로 분류된 조에 대해 디스플레이 데이터 생성.

    Args:
        conn:              프롬프트 override 조회
        document_text:     사업장 본문
        articles:          카탈로그 전체 (원본 db.all_articles() 상응)
        excluded_articles: 이미 검사된 필수 조 (slot 카탈로그에 있는 조)
        batch_size:        LLM 호출당 조 개수 (응답 정확도 유지 목적)
    """
    excluded = excluded_articles or set()
    targets: list[tuple[int, str]] = []
    meta_by_no: dict[int, OptionalArticleSpec] = {}
    for a in articles:
        n = a["article"]
        if n in excluded:
            continue
        if a.get("required"):
            continue  # 필수는 슬롯 검사가 담당
        title = a.get("title", "")
        targets.append((n, title))
        meta_by_no[n] = a

    if not targets:
        return []

    client = get_llm_client()
    sys_prompt = resolve_prompt(conn, "optional_display")

    out: list[OptionalDisplayVO] = []
    for i in range(0, len(targets), batch_size):
        chunk = targets[i : i + batch_size]
        payload = _call_extract(
            client, sys_prompt, model, document_text, chunk
        )
        by_no = {p["article"]: p for p in payload}
        for n, title in chunk:
            p = by_no.get(n, {})
            present = bool(p.get("present"))
            quote = p.get("quote") or ""
            a = meta_by_no[n]
            out.append(
                OptionalDisplayVO(
                    article=n,
                    title=title,
                    scope=str(a.get("scope") or "선택"),
                    master_body=a.get("body") or "",
                    master_guide=a.get("guide") or "",
                    master_note=a.get("note") or "",
                    user_quote=quote if present and quote else None,
                    user_present=present,
                )
            )
    return out


def _call_extract(
    client: LLMClient,
    sys_prompt: str,
    model: str | None,
    document_text: str,
    targets: list[tuple[int, str]],
) -> list[dict[str, Any]]:
    spec = "\n".join(f"- 제{n}조: {t}" for n, t in targets)
    user = (
        f"[사업장 취업규칙 본문]\n```\n{document_text}\n```\n\n"
        f"[조 주제 {len(targets)}건]\n{spec}\n\n"
        "각 조 주제에 대해 본문 존재여부와 인용을 submit_displays 함수로 제출하라."
    )
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["displays"],
        "properties": {
            "displays": {
                "type": "array",
                "minItems": len(targets),
                "maxItems": len(targets),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["article", "present", "quote"],
                    "properties": {
                        "article": {"type": "integer", "enum": [n for n, _ in targets]},
                        "present": {"type": "boolean"},
                        "quote": {"type": "string"},
                    },
                },
            }
        },
    }

    cache_key = make_cache_key(
        "optional_display", model or "", sys_prompt, user, schema
    )
    result = client.chat(
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user},
        ],
        model=model,
        temperature=0.0,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "submit_displays",
                    "description": "조 주제별 사업장 본문 인용 제출",
                    "parameters": schema,
                },
            }
        ],
        cache_key=cache_key,
    )
    tool_calls = result.get("tool_calls") or []
    if not tool_calls:
        return []
    args_str = (tool_calls[0].get("function") or {}).get("arguments") or "{}"
    try:
        args = json.loads(args_str)
    except json.JSONDecodeError as e:
        log.warning("optional_display.parse_failed — %s", e)
        return []
    return args.get("displays", [])
