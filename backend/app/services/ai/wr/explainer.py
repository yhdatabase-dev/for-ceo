"""위반 사유 LLM 풀이 — 코드 룰의 기술적 메시지를 감독관용 평이한 한국어로 변환.

배치 처리: VIOLATION/MISSING 핀딩만 모아서 1회 호출로 user_reason 생성.
interpret 슬롯은 LLM verdict_reason 이 이미 평이하므로 그대로 user_reason 으로 복사.
"""
from __future__ import annotations

import contextvars

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.integrations.llm import cache as llm_cache
from app.core.config import get_api_key, get_llm_model
from app.schemas.wr.values import Finding, SlotDef


# 외부 프롬프트 오버라이드 경로 (관리자 대시보드에서 편집 가능)
_PROMPT_OVERRIDE_PATH = Path(__file__).resolve().parents[4] / "data" / "prompts" / "explainer.md"


def _system_prompt() -> str:
    """관리자 override(prompt_store, 볼륨 영구화) 우선, 없으면 모듈 내장 기본값.
    레거시 explainer.md 파일도 계속 지원(override 없을 때)."""
    from app.repositories.shared import prompt as prompt_store

    ov = prompt_store.get_or_default("wr_explainer", "")
    if ov.strip():
        return ov
    if _PROMPT_OVERRIDE_PATH.exists():
        try:
            text = _PROMPT_OVERRIDE_PATH.read_text(encoding="utf-8").strip()
            if text:
                return text
        except Exception:
            pass
    return _SYSTEM_PROMPT


_SYSTEM_PROMPT = """당신은 한국 노동법 전문가이자 근로감독관 보조이다.

[역할]
- 자동 검토 시스템이 산출한 기술적 위반 사유 N개를, 감독관이 사업장 측에 시정 지시할 때 그대로 인용할 수 있는 **평이한 한국어**로 다시 쓴다.

[중요 — 비교 방향 절대 헷갈리지 말 것]
- "법정_기준값" 은 **현행법이 정한 기준** (휴가일수·연령·시간 한도 등). 일부는 최소(>=)·일부는 최대(<=)·일부는 정확값(==).
- "사업장_규정값" 은 사업장 취업규칙에 적힌 값.
- 입력 데이터의 `비교_방향` 필드를 반드시 따른다:
  * `>=` 면 "사업장값 ≥ 법정값" 이어야 적정. 미달 시 사업장값을 **상향** 시정.
  * `<=` 면 "사업장값 ≤ 법정값" 이어야 적정. 초과 시 사업장값을 **하향** 시정.
  * `==` 면 정확 일치 필요.
  * `object_match` 면 부적정_핵심_키 들이 누락·불일치.
- 절대 법정값과 사업장값을 거꾸로 쓰지 말 것 (예: 법정 6일을 "3일이 맞다"로 쓰면 안 됨).
- 슬롯의 `note` 필드에 "구법 N" 표기가 있어도, 그것은 과거 기준일 뿐이며 현재 비교 기준은 항상 "법정_기준값"이다.

[object_match 슬롯 — 키별 차이만 사유로 작성]
- 부적정_핵심_키 에 명시된 키만 사유에 언급한다. 그 외 키는 사업장 규정에 적합하므로 건드리지 말 것.
- 키별_비교 의 "사업장값" 과 "기준값" 은 객관적 사실이므로 그대로 따른다.
- **사업장 인용 문구에 명시된 내용을 부정하지 말 것**. 인용에 "X를 가산한 기간"이 있으면 "가산이 빠졌다"고 쓰면 안 된다. "가산은 있으나 가산 배수가 1배(법정 2배 미달)"처럼 정확한 차이를 짚어야 한다.
- 사업장 표현이 신법의 일부 요건만 누락한 경우, "전체 가산 자체가 누락" 이 아니라 "특정 요건(예: 2배 가산)이 누락" 으로 정확히 작성하라.

[수치·키별 차이 표현 가이드]
- "사업장 규정은 N으로 되어 있으나 법정 기준은 M이므로, N→M 으로 수정하여야 합니다." 식으로 정확한 수치를 명시.
- 막연한 "기준에 미달"·"적용이 빠짐" 같은 모호한 표현은 피하고, 어느 키·어느 수치가 어떻게 다른지 명시.

[작성 규칙]
- 1~3문장. 결론(어떻게 잘못되었는지) → 근거(법령·법정 기준값) → 시정방향 순.
- 사업장 본문 인용을 가능하면 1번 짧게 인용 ("...") 으로 포함하여 구체화.
- 법령 조항 번호와 법명을 정확히 표기 (예: 근로기준법 제56조).
- "추출값 6 > 기준 5 (<= 필요)" 같은 기술적 표현 금지.
- 어조: 감독관이 사업장에게 시정을 지시하는 공식적인 한국어. "~합니다", "~하여야 합니다", "~수정이 필요합니다".
- 감정·과장 표현 금지.
- "LLM", "AI", "자동 검토", "본문 매칭", "임베딩", "유사도", "코사인", "추출값" 등 시스템 내부 용어 사용 절대 금지. 사람이 검토한 것처럼 자연스럽게 작성.
- "보입니다", "보이지 않습니다" 처럼 시각 동사를 쓰지 말고 "명시되어 있습니다", "명시되어 있지 않습니다" 처럼 단정적·법령적 어조로 작성.
- ⛔ **영문 변수명·내부 키 절대 사용 금지** — `slot_id`, `extracted_value`, `default_months`, `special_extension_months`, `unused_multiplier`, `age_max`, `grade_max`, `early_weeks_max`, `late_weeks_min`, `annual_days`, `per_use_min_days` 등의 영문 키를 사용자 사유에 그대로 쓰지 말 것.
  반드시 한국어 표현으로 풀어 쓰라:
    · default_months → "기본 기간"
    · special_extension_months → "특별연장 6개월"
    · unused_multiplier → "미사용 가산 배수"
    · age_max → "대상 자녀 연령 한도"
    · grade_max → "대상 자녀 학년 한도"
    · late_weeks_min → "임신 후기 단축 시작 주차"
    · annual_days → "연간 일수"
    · per_use_min_days → "1회 최소 일수"
  입력 데이터의 "법정_기준_객체"·"사업장_규정_객체"·"부적정_핵심_항목" 은 이미 한국어로 변환되어 있으니 그것을 그대로 사용.

[예시]
입력: 법정_기준값=6, 사업장_규정값=3, 비교_방향=">=", 인용="연간 3일 이내의 휴가"
올바른 출력: "난임치료휴가는 법정 기준상 연간 6일 이상 부여하여야 합니다. 사업장 규정에는 '연간 3일 이내의 휴가'로만 되어 있어 법정 기준에 미달하므로, 6일 이상으로 상향 수정이 필요합니다."
잘못된 출력 (절대 금지): "연간 6일이 아니라 3일 이내로 부여하여야 합니다." ← 법정과 사업장값을 거꾸로 표기했으므로 명백한 오류.

[결정성]
- 같은 입력에 같은 출력을 보장한다."""


_DIR_DESC = {
    ">=": "사업장값이 법정값 이상이어야 함 (미달 시 사업장값을 상향 시정)",
    "<=": "사업장값이 법정값 이하여야 함 (초과 시 사업장값을 하향 시정)",
    "==": "정확 일치 필요",
    "object_match": "객체 키별 일치 필요",
    "presence": "본문에 명시 필요",
    "interpret": "LLM 해석 (verdict_reason 우선)",
}

# 영문 변수명 → 사용자 노출용 한국어 라벨
# (시스템 내부 키가 사용자 사유에 그대로 노출되지 않도록)
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
    """영문/내부 키를 사용자 노출용 한국어 라벨로 변환."""
    return _KEY_LABELS.get(key, key)


def _format_finding_input(s: SlotDef, f: Finding) -> dict[str, Any]:
    """LLM 풀이용 입력 — object_match 의 경우 키별 차이를 명시화."""
    base: dict[str, Any] = {
        "slot_id": f.slot_id,
        "article": f.article,
        "item": s.slot_id,
        "extract_target": s.extract_target.strip().split("\n")[0],
        "기술적_사유": f.reason,
        "비교_방향": f"{f.comparator} — {_DIR_DESC.get(f.comparator, '')}",
        "사업장_인용": (f.extracted.quote or "")[:300],
        "관련_법령": (s.penalty or [None])[0],
    }
    if f.comparator == "object_match":
        # 마스터 기준 객체 (note/unit 제외)
        master_obj = (
            s.master_value.model_dump(exclude_none=True) if s.master_value else {}
        )
        master_obj.pop("value", None)
        master_obj.pop("unit", None)
        master_obj.pop("note", None)
        # 추출값 객체
        extracted_obj = f.extracted.extracted_value or {}
        if not isinstance(extracted_obj, dict):
            extracted_obj = {"_raw": extracted_obj}
        # 키별 일치/불일치 분석 — 키는 한국어 라벨로 변환 (LLM 출력에 영문 변수명 노출 방지)
        diffs = []
        for k, v_master in master_obj.items():
            v_user = extracted_obj.get(k) if isinstance(extracted_obj, dict) else None
            match = (v_master == v_user) or (
                v_master is not None and v_user is not None and str(v_master) == str(v_user)
            )
            diffs.append({"항목": _kor_key(k), "사업장값": v_user, "기준값": v_master, "일치": match})
        # 법정 기준·사업장 규정 객체도 한국어 키로 변환해 전달
        base["법정_기준_객체"] = {_kor_key(k): v for k, v in master_obj.items()}
        base["사업장_규정_객체"] = (
            {_kor_key(k): v for k, v in extracted_obj.items()}
            if isinstance(extracted_obj, dict)
            else extracted_obj
        )
        base["키별_비교"] = diffs
        # 부적정 핵심: 불일치 항목들 (한국어 라벨)
        bad_items = [d["항목"] for d in diffs if not d["일치"]]
        base["부적정_핵심_항목"] = bad_items
    else:
        base["사업장_규정값"] = f.extracted.extracted_value
        base["법정_기준값"] = s.master_value.value if s.master_value else None
    return base


_BATCH_SIZE = 5      # 호출당 finding 수 — 5개씩 묶어 병렬 호출
_MAX_WORKERS = 5     # 동시 호출 수


def _explain_batch(
    items: list[dict],
    *,
    client: OpenAI,
    model: str,
) -> dict[str, str]:
    """단일 batch 호출 — slot_id → user_reason 반환."""
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
    # 캐시 확인
    sys_prompt = _system_prompt()
    cache_key = llm_cache.make_key(sys_prompt, user_msg, schema, model)
    cached = llm_cache.get(cache_key)
    if cached is not None:
        args = cached
    else:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ],
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
            tool_choice={"type": "function", "function": {"name": "submit_rewrites"}},
            temperature=0,
            top_p=1,
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return {}
        args = json.loads(msg.tool_calls[0].function.arguments)
        llm_cache.put(cache_key, args)
    return {r["slot_id"]: r["user_reason"].strip() for r in args.get("rewrites", [])}


def explain_findings(
    findings: list[Finding],
    slots_by_id: dict[str, SlotDef],
    *,
    model: str | None = None,
    api_key: str | None = None,
) -> list[Finding]:
    """위반/누락 핀딩의 user_reason 채움. 적정/오류는 건드리지 않음.

    배치 5건씩 병렬 5 호출 — 25건 위반 시 ~5초 (이전 12초 → 60% 단축).
    """
    pending: list[Finding] = []
    for f in findings:
        if f.status not in ("VIOLATION", "MISSING"):
            continue
        if f.comparator == "interpret" and f.extracted.verdict_reason:
            f.user_reason = f.extracted.verdict_reason.strip()
            continue
        pending.append(f)

    if not pending:
        return findings

    items_payload = []
    item_to_finding: dict[str, Finding] = {}
    for f in pending:
        s = slots_by_id.get(f.slot_id)
        if s is None:
            continue
        items_payload.append(_format_finding_input(s, f))
        item_to_finding[f.slot_id] = f

    if not items_payload:
        return findings

    # batch 분할 (5건씩)
    batches = [
        items_payload[i : i + _BATCH_SIZE]
        for i in range(0, len(items_payload), _BATCH_SIZE)
    ]

    client = OpenAI(api_key=get_api_key(api_key), timeout=45.0)
    model_name = get_llm_model(model)

    by_slot: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(batches))) as ex:
        futures = [
            ex.submit(
                contextvars.copy_context().run,
                _explain_batch, batch, client=client, model=model_name,
            )
            for batch in batches
        ]
        for fut in as_completed(futures):
            try:
                by_slot.update(fut.result())
            except Exception as e:
                from app.core.logging import get_logger

                get_logger(__name__).warning(
                    "[사유풀이 batch 실패] %s: %s", type(e).__name__, e
                )

    for sid, reason in by_slot.items():
        f = item_to_finding.get(sid)
        if f is not None:
            f.user_reason = reason
    return findings
