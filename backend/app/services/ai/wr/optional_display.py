"""선택 조 디스플레이 — 검사 없이 참고 정보만 사용자에게 표시.

마스터 DB 의 D(본문)·E(작성시 착안사항)·F(참고)를 가져오고,
사업장 본문에 관련 조가 있는지 LLM 1회 일괄 호출로 인용·존재여부 확인.
"""
from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from app.core.config import get_api_key, get_llm_model
from app.repositories.wr.master import MasterDB
from app.schemas.wr.values import OptionalDisplay


_SYSTEM_PROMPT = """당신은 한국 노동법 취업규칙 검토 보조이다.

[역할]
- 사용자가 제공한 사업장 취업규칙 본문에서, 지정된 N개 "조 주제" 각각에 대해
  본문에 관련 조항이 존재하는지 검출하고, 있으면 가장 직접적인 1~2 문장을 인용한다.

[규칙]
- 추측 금지. 본문에 명시 없으면 present=false, quote="".
- quote 는 사업장 본문에서만 발췌. 가공/요약/번역 금지.
- 사업장 취업규칙은 표준 형식이 아닐 수 있다 (【제목】, 제N조, 부제 등 다양).
- 같은 입력 → 같은 출력 (결정성 보장)."""


def build_optional_displays(
    document_text: str,
    db: MasterDB,
    *,
    excluded_articles: set[int] | None = None,
    model: str | None = None,
    api_key: str | None = None,
    batch_size: int = 30,
) -> list[OptionalDisplay]:
    """선택(또는 미정)으로 분류된 조에 대해 디스플레이 데이터 생성.

    Args:
        excluded_articles: 이미 검사된 필수 조는 제외 (slot 카탈로그에 있는 조).
    """
    excluded = excluded_articles or set()
    targets: list[tuple[int, str]] = []
    for n in db.all_articles():
        if n in excluded:
            continue
        if db.is_required(n):
            continue  # 필수는 슬롯 검사가 담당 — 슬롯 미정이면 별도 보강 필요
        title = db.title(n)
        targets.append((n, title))

    if not targets:
        return []

    # 인용 추출은 한 번에 너무 많은 조를 보내면 응답이 부정확해질 수 있어 batch.
    out: list[OptionalDisplay] = []
    client = OpenAI(api_key=get_api_key(api_key))
    model_name = get_llm_model(model)
    for i in range(0, len(targets), batch_size):
        chunk = targets[i : i + batch_size]
        payload = _call_extract(client, model_name, document_text, chunk)
        by_no = {p["article"]: p for p in payload}
        for n, title in chunk:
            p = by_no.get(n, {})
            present = bool(p.get("present"))
            quote = p.get("quote") or ""
            out.append(
                OptionalDisplay(
                    article=n,
                    title=title,
                    scope=str(db.article(n).get("scope") or "선택"),
                    master_body=db.body(n),
                    master_guide=db._cell(n, "guide"),
                    master_note=db.note(n),
                    user_quote=quote if present and quote else None,
                    user_present=present,
                )
            )
    return out


def _call_extract(
    client: OpenAI, model: str, document_text: str, targets: list[tuple[int, str]]
) -> list[dict[str, Any]]:
    spec = "\n".join(f"- 제{n}조: {t}" for n, t in targets)
    user = (
        f"[사업장 취업규칙 본문]\n```\n{document_text}\n```\n\n"
        f"[조 주제 {len(targets)}건]\n{spec}\n\n"
        f"각 조 주제에 대해 본문 존재여부와 인용을 submit_displays 함수로 제출하라."
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
    from app.repositories.shared import prompt as prompt_store

    sys_p = prompt_store.get_or_default("optional_display", _SYSTEM_PROMPT)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": sys_p},
            {"role": "user", "content": user},
        ],
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
        tool_choice={"type": "function", "function": {"name": "submit_displays"}},
        temperature=0,
        top_p=1,
    )
    msg = resp.choices[0].message
    if not msg.tool_calls:
        return []
    args = json.loads(msg.tool_calls[0].function.arguments)
    return args.get("displays", [])
