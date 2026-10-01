"""위반 사유 LLM 풀이 — 코드 룰의 기술적 메시지를 감독관용 평이한 한국어로 변환.

===============================================================================
원본 이관
===============================================================================
원본: `cgr/explainer.py` (327줄) → v2 로 이관.

변경점
- `cgr.models.SlotDef / Finding` → `SlotDefVO / FindingVO`
- FindingVO 는 평면 구조라 `f.extracted.quote/extracted_value/verdict_reason` 접근 불가.
  · `f.quote` / `f.extracted_value` 는 그대로 사용
  · verdict_reason 은 FindingVO 에 없음 → **시그니처에 `extractions_by_id` 추가**
    (오케스트레이터가 rules.evaluate() 전의 ExtractionVO 사전을 유지해서 전달)
- `cgr.llm_cache` → `app.integrations.llm.cache` (make_cache_key)
- `cgr.prompt_store` + `data/prompts/explainer.md` → `resolve_prompt(conn, "wr_explainer")`
- `OpenAI(...)` 직접 인스턴스화 → `get_llm_client()` (재시도·PII·캐시 어댑터 내장)
- ThreadPoolExecutor 5 batch × 5 finding 병렬 구조는 원본 그대로 유지
- `_KEY_LABELS`, `_DIR_DESC`, `_format_finding_input` 등 매핑·포맷은 100% 동일

배치 처리
- VIOLATION/MISSING 핀딩만 모아 5건 × 5 병렬 호출 → user_reason 채움
- interpret 슬롯은 ExtractionVO.verdict_reason 이 이미 평이하므로 그대로 복사
"""
from __future__ import annotations

import contextvars
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import psycopg

from app.core.logging import get_logger
from app.integrations.llm.cache import make_cache_key
from app.integrations.llm.client import LLMClient, get_llm_client
from app.integrations.llm.prompts.resolver import resolve_prompt
from app.schemas.review.values import ExtractionVO, FindingVO, SlotDefVO

log = get_logger(__name__)


_DIR_DESC = {
    ">=": "사업장값이 법정값 이상이어야 함 (미달 시 사업장값을 상향 시정)",
    "<=": "사업장값이 법정값 이하여야 함 (초과 시 사업장값을 하향 시정)",
    "==": "정확 일치 필요",
    "object_match": "객체 키별 일치 필요",
    "presence": "본문에 명시 필요",
    "interpret": "LLM 해석 (verdict_reason 우선)",
}

# 영문 변수명 → 사용자 노출용 한국어 라벨
_KEY_LABELS = {
    "default_months": "기본 기간(개월)",
    "special_extension_months": "특별연장 기간(개월)",
    "base_year": "기본 연수",
    "unused_multiplier": "미사용 가산 배수",
    "age_max": "대상 자녀 연령 한도",
    "grade_max": "대상 자녀 학년 한도",
    "early_weeks_max": "임신 초기 주차 상한",
    "late_weeks_min": "임신 후기 주차 하한",
    "annual_days": "연간 일수",
    "per_use_min_days": "1회 최소 일수",
    "min_hours_per_week": "주당 최소 근로시간",
    "max_hours_per_week": "주당 최대 근로시간",
    "총액": "임금 총액",
    "구성항목": "임금 구성항목",
    "계산방법": "임금 계산방법",
    "공제내역": "공제 내역",
    "지급일": "지급일",
}


def _kor_key(key: str) -> str:
    return _KEY_LABELS.get(key, key)


def _format_finding_input(s: SlotDefVO, f: FindingVO) -> dict[str, Any]:
    """LLM 풀이용 입력 — object_match 의 경우 키별 차이를 명시화.

    원본과 동치 (Finding.extracted.* 는 FindingVO 평면 필드로 대체).
    """
    base: dict[str, Any] = {
        "slot_id": f.slot_id,
        "article": f.article,
        "item": s.slot_id,
        "extract_target": (s.extract_target or "").strip().split("\n")[0],
        "기술적_사유": f.reason,
        "비교_방향": f"{f.comparator} — {_DIR_DESC.get(f.comparator, '')}",
        "사업장_인용": (f.quote or "")[:300],
        "관련_법령": (s.penalty or [None])[0],
    }
    if f.comparator == "object_match":
        # 마스터 기준 객체 (note/unit 제외) — v2 MasterValueVO 는 keys 에 담김
        master_obj: dict[str, Any] = {}
        if s.master_value and s.master_value.keys:
            master_obj = dict(s.master_value.keys)
        master_obj.pop("value", None)
        master_obj.pop("unit", None)
        master_obj.pop("note", None)

        extracted_obj = f.extracted_value or {}
        if not isinstance(extracted_obj, dict):
            extracted_obj = {"_raw": extracted_obj}

        diffs = []
        for k, v_master in master_obj.items():
            v_user = extracted_obj.get(k) if isinstance(extracted_obj, dict) else None
            match = (v_master == v_user) or (
                v_master is not None and v_user is not None and str(v_master) == str(v_user)
            )
            diffs.append(
                {"항목": _kor_key(k), "사업장값": v_user, "기준값": v_master, "일치": match}
            )
        base["법정_기준_객체"] = {_kor_key(k): v for k, v in master_obj.items()}
        base["사업장_규정_객체"] = (
            {_kor_key(k): v for k, v in extracted_obj.items()}
            if isinstance(extracted_obj, dict)
            else extracted_obj
        )
        base["키별_비교"] = diffs
        base["부적정_핵심_항목"] = [d["항목"] for d in diffs if not d["일치"]]
    else:
        base["사업장_규정값"] = f.extracted_value
        base["법정_기준값"] = s.master_value.value if s.master_value else None
    return base


_BATCH_SIZE = 5     # 호출당 finding 수
_MAX_WORKERS = 5    # 동시 호출 수


def _explain_batch(
    items: list[dict],
    *,
    client: LLMClient,
    sys_prompt: str,
    model: str | None,
) -> dict[str, str]:
    """단일 batch 호출 — slot_id → user_reason 반환.

    캐시는 client 어댑터가 cache_key 기반으로 자체 처리.
    """
    if not items:
        return {}
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["rewrites"],
        "properties": {
            "rewrites": {
                "type": "array",
                "minItems": len(items),
                "maxItems": len(items),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["slot_id", "user_reason"],
                    "properties": {
                        "slot_id": {"type": "string"},
                        "user_reason": {"type": "string"},
                    },
                },
            }
        },
    }
    user_msg = (
        "[위반/누락 사유 풀이 요청]\n\n"
        + json.dumps(items, ensure_ascii=False, indent=2)
        + "\n\n각 항목에 대해 위 [작성 규칙]에 따라 user_reason 을 작성하여 submit_rewrites 함수로 제출하라."
    )

    cache_key = make_cache_key("wr_explainer", model or "", sys_prompt, user_msg, schema)
    result = client.chat(
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_msg},
        ],
        model=model,
        temperature=0.0,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "submit_rewrites",
                    "description": "위반 사유 평이한 한국어 풀이 제출",
                    "parameters": schema,
                },
            }
        ],
        cache_key=cache_key,
    )

    tool_calls = result.get("tool_calls") or []
    if not tool_calls:
        return {}
    args_str = (tool_calls[0].get("function") or {}).get("arguments") or "{}"
    try:
        args = json.loads(args_str)
    except json.JSONDecodeError as e:
        log.warning("explainer.parse_failed — %s", e)
        return {}
    return {r["slot_id"]: (r.get("user_reason") or "").strip() for r in args.get("rewrites", [])}


def explain_findings(
    conn: psycopg.Connection,
    findings: list[FindingVO],
    slots_by_id: dict[str, SlotDefVO],
    extractions_by_id: dict[str, ExtractionVO],
    *,
    model: str | None = None,
) -> list[FindingVO]:
    """위반/누락 핀딩의 user_reason 채움. 적정/오류는 건드리지 않음.

    Args:
        conn:              프롬프트 override 조회용
        findings:          평가 완료된 FindingVO 리스트 (in-place 수정)
        slots_by_id:       slot_id → SlotDefVO
        extractions_by_id: slot_id → ExtractionVO (interpret verdict_reason 복사용)
        model:             모델 override

    배치 5건씩 병렬 5 호출 — 25건 위반 시 ~5초.
    """
    pending: list[FindingVO] = []
    for f in findings:
        if f.status not in ("VIOLATION", "MISSING"):
            continue
        # interpret 슬롯은 ExtractionVO.verdict_reason 이 이미 평이 → 그대로 복사
        if f.comparator == "interpret":
            ext = extractions_by_id.get(f.slot_id)
            if ext and ext.verdict_reason:
                f.user_reason = ext.verdict_reason.strip()
                continue
        pending.append(f)

    if not pending:
        return findings

    items_payload: list[dict[str, Any]] = []
    item_to_finding: dict[str, FindingVO] = {}
    for f in pending:
        s = slots_by_id.get(f.slot_id)
        if s is None:
            continue
        items_payload.append(_format_finding_input(s, f))
        item_to_finding[f.slot_id] = f

    if not items_payload:
        return findings

    batches = [
        items_payload[i : i + _BATCH_SIZE]
        for i in range(0, len(items_payload), _BATCH_SIZE)
    ]

    sys_prompt = resolve_prompt(conn, "wr_explainer")
    client = get_llm_client()

    by_slot: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(batches))) as ex:
        futures = [
            ex.submit(
                contextvars.copy_context().run,
                _explain_batch,
                batch,
                client=client,
                sys_prompt=sys_prompt,
                model=model,
            )
            for batch in batches
        ]
        for fut in as_completed(futures):
            try:
                by_slot.update(fut.result())
            except Exception as e:  # noqa: BLE001
                log.warning("[사유풀이 batch 실패] %s: %s", type(e).__name__, e)

    for sid, reason in by_slot.items():
        f = item_to_finding.get(sid)
        if f is not None:
            f.user_reason = reason
    return findings
