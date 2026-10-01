"""LLM 슬롯 추출기 — WR 취업규칙 본문 → 슬롯별 추출 결과.

===============================================================================
원본 이관
===============================================================================
원본: `cgr/extractor.py` (319줄) → v2 로 이관.

변경점
- `cgr.models.SlotDef / Extraction` → `SlotDefVO / ExtractionVO`
- `cgr.llm_cache` → `app.integrations.llm.cache` (make_cache_key/cache_get/cache_put)
- `cgr.prompt_store` + `data/prompts/extractor.md` 파일 fallback
  → `app.integrations.llm.prompts.resolver.resolve_prompt(conn, "wr_extractor")`
  (DB `cgr_admin.prompt` override → 코드 default 폴백)
- `OpenAI(...)` 직접 인스턴스화 (재시도 인라인) → `get_llm_client().chat(...)`
  · 어댑터 안에 PII 게이트웨이 + 캐시 + 오류 표준화가 이미 있음
  · 재시도는 v2 에선 어댑터 상위에서 관리 (여기서는 단일 호출)
- tool_choice 강제 · schema 구성 · 슬롯 spec 포맷은 원본과 100% 동일
- 시그니처에 `conn: psycopg.Connection` 추가 (프롬프트 override 조회용)

프롬프트 캐시
- 원본은 `system + user prefix` 를 고정하고 슬롯 spec 만 뒤에 붙였음 (OpenAI prompt cache).
- v2 도 동일 구조 유지 — 사업장 본문이 앞쪽, 슬롯 spec 이 뒤쪽.
"""
from __future__ import annotations

import json
from typing import Any

import psycopg

from app.core.logging import get_logger
from app.integrations.llm.cache import make_cache_key
from app.integrations.llm.client import get_llm_client
from app.integrations.llm.prompts.resolver import resolve_prompt
from app.schemas.review.values import ExtractionVO, SlotDefVO

log = get_logger(__name__)


def _build_tool_schema(slots: list[SlotDefVO]) -> dict[str, Any]:
    """function calling 용 JSON Schema.

    interpret 슬롯이 1개라도 있으면 verdict/verdict_reason 필드 추가.
    원본 로직 동일.
    """
    has_interpret = any(s.comparator == "interpret" for s in slots)
    item_required = ["slot_id", "found", "extracted_value", "quote", "confidence"]
    item_props: dict[str, Any] = {
        "slot_id": {"type": "string", "enum": [s.slot_id for s in slots]},
        "found": {"type": "boolean"},
        "extracted_value": {},  # any
        "quote": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    }
    if has_interpret:
        item_required.extend(["verdict", "verdict_reason"])
        item_props["verdict"] = {
            "type": ["string", "null"],
            "enum": ["OK", "VIOLATION", "AMBIGUOUS", None],
        }
        item_props["verdict_reason"] = {"type": ["string", "null"]}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["extractions"],
        "properties": {
            "extractions": {
                "type": "array",
                "minItems": len(slots),
                "maxItems": len(slots),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": item_required,
                    "properties": item_props,
                },
            }
        },
    }


def _format_slot_spec(s: SlotDefVO) -> str:
    """슬롯 정의 → user 프롬프트에 삽입할 텍스트 블록. 원본 포맷 그대로."""
    parts = [
        f"## {s.slot_id}",
        f"- article: 제{s.article}조" + (f" {s.parent_clause}" if s.parent_clause else ""),
        f"- required: {s.required}",
        f"- comparator: {s.comparator}",
        f"- 추출 대상: {(s.extract_target or '').strip()}",
        f"- extract_schema: {json.dumps(s.extract_schema, ensure_ascii=False)}",
    ]
    if s.master_value:
        parts.append(
            "- 마스터 기준값(참고용·LLM 은 비교하지 말 것): "
            f"{s.master_value.model_dump(exclude_none=True)}"
        )
    if s.comparator == "interpret" and s.interpret_criteria:
        parts.append(
            f"- 해석 기준 (이 슬롯은 verdict 채우기 필수): {s.interpret_criteria.strip()}"
        )
    if s.example_compliant:
        parts.append(f"- 적정 표현 예시: {s.example_compliant}")
    return "\n".join(parts)


def extract_slots(
    conn: psycopg.Connection,
    document_text: str,
    slots: list[SlotDefVO],
    *,
    model: str | None = None,
) -> list[ExtractionVO]:
    """1회 LLM 호출로 N개 슬롯 일괄 추출.

    Args:
        conn:           프롬프트 override 조회용 DB 커넥션
        document_text:  사업장 취업규칙 본문
        slots:          이번 호출로 추출할 슬롯 정의
        model:          모델 오버라이드 (None 이면 어댑터 기본)

    Returns:
        슬롯 순서와 동일한 ExtractionVO 리스트. LLM 이 누락한 슬롯은
        found=false 빈 결과로 채워짐.
    """
    if not slots:
        return []

    sys_prompt = resolve_prompt(conn, "wr_extractor")
    spec_block = "\n\n".join(_format_slot_spec(s) for s in slots)
    # OpenAI prompt cache 활용 — 본문/작업안내는 prefix 로 고정, 슬롯 spec 이 가변.
    user_prompt = (
        "=== 사업장 취업규칙 본문 ===\n\n"
        f"{document_text}\n\n"
        "=== 작업 안내 ===\n"
        "위 본문에서 아래 슬롯들에 대해 [역할]에 따라 추출하여 submit_extractions 함수로 제출하라.\n\n"
        "----- 슬롯 spec -----\n\n"
        f"{spec_block}"
    )
    schema = _build_tool_schema(slots)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "submit_extractions",
                "description": "각 슬롯의 추출 결과를 제출",
                "parameters": schema,
            },
        }
    ]

    # 캐시 키 — 원본은 (sys, user, schema, model) 조합. v2 도 동일.
    cache_key = make_cache_key(
        "wr_extractor", model or "", sys_prompt, user_prompt, schema
    )

    client = get_llm_client()
    result = client.chat(
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
        model=model,
        temperature=0.0,
        tools=tools,
        cache_key=cache_key,
    )

    payload = _payload_from_result(result)

    out: list[ExtractionVO] = []
    for item in payload.get("extractions", []):
        out.append(
            ExtractionVO(
                slot_id=item["slot_id"],
                extracted_value=item.get("extracted_value"),
                quote=item.get("quote") or "",
                found=bool(item.get("found")),
                confidence=item.get("confidence"),
                verdict=item.get("verdict"),
                verdict_reason=item.get("verdict_reason"),
            )
        )

    # 슬롯 순서 보존 + 누락 슬롯 fill
    by_id = {e.slot_id: e for e in out}
    ordered: list[ExtractionVO] = []
    for s in slots:
        if s.slot_id in by_id:
            ordered.append(by_id[s.slot_id])
        else:
            ordered.append(
                ExtractionVO(
                    slot_id=s.slot_id,
                    extracted_value=None,
                    quote="",
                    found=False,
                    confidence=None,
                )
            )
    return ordered


# ─────────────────────────────────────────────────────────────
# 어댑터 응답 파싱
# ─────────────────────────────────────────────────────────────
def _payload_from_result(result: dict[str, Any]) -> dict[str, Any]:
    """LLMClient.chat 표준 응답 → submit_extractions arguments dict.

    v2 어댑터는 tool_calls 를 `[tc.model_dump() for tc in ...]` 로 담아줌.
    각 항목: {id, type, function: {name, arguments(str)}}
    """
    tool_calls = result.get("tool_calls") or []
    if not tool_calls:
        raise RuntimeError(f"LLM 응답에 tool_call 없음: {result.get('content')!r}")
    fn = tool_calls[0].get("function") or {}
    args_str = fn.get("arguments") or "{}"
    try:
        return json.loads(args_str)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"LLM tool_call arguments 파싱 실패: {e}") from e
