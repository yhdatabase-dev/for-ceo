"""LLM 슬롯 추출기.

전체 사업장 취업규칙 본문 + 슬롯 정의 N개를 1회 호출로 일괄 추출.
- 모델: gpt-5.4-mini (config 기본)
- 결정성: temperature=0, top_p=1
- 구조화 출력: function calling (tool_choice 강제)
- 호출 timeout 60s + 재시도 3회 (rate limit / hang 방지)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from app.integrations.llm import cache as llm_cache
from app.core.config import get_api_key, get_llm_model
from app.schemas.wr.values import Extraction, SlotDef


_CALL_TIMEOUT = 60.0       # 단일 호출 최대 60s — hang 방지
_MAX_RETRIES = 3
_RETRY_BACKOFF = (2.0, 5.0, 10.0)

# 외부 프롬프트 오버라이드 경로 (관리자 대시보드에서 편집 가능)
_PROMPT_OVERRIDE_PATH = Path(__file__).resolve().parents[4] / "data" / "prompts" / "extractor.md"


def _system_prompt() -> str:
    """관리자 override(prompt_store, 볼륨 영구화) 우선, 없으면 모듈 내장 기본값.
    레거시 extractor.md 파일도 계속 지원(override 없을 때)."""
    from app.repositories.shared import prompt as prompt_store

    ov = prompt_store.get_or_default("wr_extractor", "")
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


_SYSTEM_PROMPT = """당신은 한국 노동법 전문가이며 취업규칙 검토를 보조한다.

[역할]
- 사용자가 제공한 한 사업장의 취업규칙 본문에서, 지정된 N개 "슬롯" 각각에 대해 다음을 추출한다:
  1) found: 해당 슬롯에 관한 규정이 본문에 있는지(true/false)
  2) extracted_value: 슬롯이 요구하는 값(숫자/문자/boolean/object). 추출 가능하면 채우고, 없으면 null
  3) quote: 본문에서 인용한 가장 가까운 1~3 문장(원문 그대로, 빈칸·기호 보존)
  4) confidence: 추출 자기 확신도 (0~1)

[추출 규칙]
- 추측 금지. 본문에 없으면 found=false, value=null, quote="" 로 응답.
- value 의 타입은 슬롯의 extract_schema 를 따른다 (integer / boolean / object).
- 객체 추출(object) 시 누락된 키는 null 로 채운다.
- quote 는 반드시 본문 원문에서만 발췌. 가공·요약·번역 금지.

[추출 vs 판정 분리 — 매우 중요]
- 너의 임무는 **추출**이다. 적정·부적정 판정은 코드 룰이 한다.
- **구법 표현이라도 본문에 있으면 무조건 found=true / value=본문 수치 로 추출**:
  · 본문 "1주 6시간" → found=true, value=6 (코드 룰이 마스터 5시간과 비교해 위반 판정)
  · 본문 "만 8세 이하" → found=true, value=8 (마스터 12세와 비교해 위반)
  · 본문 "임신 11주 이내 5일" → found=true, value=5 (마스터 10일과 비교해 위반)
  · 본문 "그 기간을 가산 (1배)" → found=true, unused_multiplier=1 (마스터 2배와 비교해 위반)
- ⚠️ extract_target / disambiguation 헤더에 신법 기준이 적혀 있어도, 그것은 **마스터 기준 참고용**이지
  본문에 그 표현이 정확히 있어야 found=true 가 되는 게 아니다.
  **본문에 동등한 의미·구법 표현이 있으면 그것을 추출하라**.
- 절대 "신법 표현이 본문에 없다" 는 이유로 found=false 처리하지 말 것.
- 추출 단계에서 "이건 부적정" 같은 판단을 내리지 마라.

[수치 추출 — 다단계 구간일 때 보수적 추출]
- 본문에 같은 슬롯에 대해 여러 단계가 있으면 (예: "11주 이내 5일, 12-15주 10일, 16-21주 30일"),
  슬롯의 extract_target 이 지시하는 구간에서 **가장 보수적인(가장 작은) 일수**를 value 로 추출하라.
- 이렇게 해야 코드 룰이 ">=" 비교로 위반(구법 잔존)을 정확히 잡을 수 있다.
- 절대 본문 중 가장 큰 값만 보고 OK 처리에 유리한 추출을 하지 말 것.
- extract_target 이 명시적으로 "최소값", "최단일수" 등으로 지시하면 반드시 따를 것.

[사업장 본문의 표현 다양성 — 5가지 형식 모두 인식할 것]
1. 표준취업규칙 형식: 제N조(제목) ① ②
2. 부제 형식: 【제목】 또는 [제목] 본문
3. 자유 서술: 조 번호 없이 단락 단위
4. 표·괘도 형식: 행/열로 정리된 정보
5. 짤막한 메모식: "연차 15일", "정년 60세" 등 키워드만
법조항 인용 부재 ≠ 미명시. "청구하면 부여한다" 같은 평이 표현도 의미가 같으면 found=true 인정.

[의미적 등가성]
- 동의어·평이 표현 인정. "근로계약 체결한 자" = "회사와 합의한 사람" 모두 OK.
- 한국어 수량·시간 등가 인정: "보름"=15일, "한 달"=30일, "환갑"=60세, "반년"=6개월 등.
- 단, **extracted_value 는 정규화된 정수·표준 표현으로 추출**:
    · 본문 "보름의 휴가" → quote="보름의 휴가" 그대로, value=15
    · 본문 "1년 6개월" → value=18 (개월) 또는 객체로 분해
  코드 룰이 정수 비교하므로, LLM 은 의미 보존하며 캐노니컬 값으로 변환할 것.

[한 조에 다중 슬롯 — quote 재사용 허용]
- 한 단락이 여러 슬롯 정보를 함께 담는 경우 (예: "연차 15일 + 3년 이상 매 2년 1일 가산 + 최대 25일")
- 각 슬롯에 대해 같은 단락을 quote 로 재사용해도 무방. 단, 추출값은 슬롯별로 정확히 분리.

[인용 길이]
- 50~300자 권장. 핵심 한 줄 + 직접 맥락만.
- 너무 짧으면(<30자) 맥락 부족, 너무 길면(>400자) 토큰 낭비.

[해석 슬롯 — comparator='interpret']
- 일부 슬롯은 단순 수치/존재 비교가 어려운 "해석 여지"가 있는 항목이다.
  슬롯 spec 의 comparator='interpret' 가 명시되고 interpret_criteria 가 함께 제공된다.
- 이 슬롯에 한해, found/quote/value 외에 추가로:
    verdict: "OK" | "VIOLATION" | "AMBIGUOUS"
    verdict_reason: 짧은 한국어 사유
  를 채워야 한다.
- **슬롯 영역 엄격 분리 매트릭스** — 아래 조항들은 이름이 비슷하나 모두 별개 항목이다. 절대 혼동하지 말고, 슬롯 이름이 가리키는 정확한 조항만 quote·extracted_value·verdict 근거로 사용하라.
  · **육아휴직** ≠ **육아기 근로시간 단축**: 휴직(전부 휴업) vs 단축(부분 근로). 분할 횟수·기간 한도 모두 별개.
  · **임신기 근로시간 단축** ≠ **육아기 근로시간 단축**: 임신기는 임신 12주 이내·32주 이후 / 육아기는 만 12세·초6 이하 자녀.
  · **출산전후휴가** ≠ **배우자 출산휴가**: 전자는 본인 출산(여성) / 후자는 배우자 출산(남성).
  · **출산전후휴가 단태아·다태아·미숙아**: 셋 다 별개 일수 (90/120/100).
  · **유산사산휴가** ≠ **출산전후휴가**: 별개 휴가 (15주 이내 10일 등).
  · **가족돌봄휴직** ≠ **가족돌봄휴가** ≠ **가족돌봄 등을 위한 근로시간 단축**: 셋 다 별개 항목.
    - 가족돌봄휴직: 무급 휴직 (남녀고용평등법 제22조의2, 연 90일·1회 30일 이상)
    - 가족돌봄휴가: 휴가 (남녀고용평등법 제22조의2 제2항, 연 10일)
    - 가족돌봄 단축: 근로시간 단축 (남녀고용평등법 제22조의3, 주 15~30시간)
  · **재해보상 근기법** ≠ **재해보상 산재보험법**: 같은 조 안에서도 별개 슬롯.
  · **연차 출근간주 — 육아휴직 / 육아기단축 / 임신기단축**: 셋 다 별개 슬롯 (각각의 출근 간주 명시 여부).
  · **직장내괴롭힘 정의 3요소** (지위우위 / 적정범위초과 / 고통환경악화): 셋 다 별개 슬롯.
  · **괴롭힘 절차** (예방교육 / 신고접수 / 조사의무 / 피해자보호 / 불리처우금지 / 행위자조치): 6개 별개 슬롯, 같은 조라도 각각 분리.

  ⚠️ 슬롯 extract_target 이 명시한 정확한 조항만 quote 로 가져올 것.
  ⚠️ "근로시간 단축" 같은 일반적 표현이 본문에 있다고 모든 단축 슬롯에 found=true 로 추출하지 말 것.
     반드시 그 단축이 어떤 사유(임신기·육아기·가족돌봄)인지 본문 맥락 확인.
  ⚠️ interpret_criteria 에 "검토 대상이 아님" 으로 명시된 항목은 절대 위반 근거로 인용하지 말 것.
- verdict_reason 작성 규칙:
    · "본문 매칭", "LLM", "AI", "추출", "유사도", "임베딩" 등 시스템 내부 용어 절대 금지
    · "보입니다 / 보이지 않습니다" 같은 시각 동사 금지 → "명시되어 있습니다 / 명시되어 있지 않습니다" 등 단정적 어조
    · verdict=OK 인 경우 부정문(예: "~이 잔존하지 않습니다") 보다는 긍정문(예: "본문에 부적합한 표현이 없습니다") 또는 "기준 충족" 으로 간단 작성
    · verdict=VIOLATION 인 경우 어떤 부분이 어긋나는지 1문장으로 명료히
- **interpret_criteria 는 항상 현행 신법 기준이다.** 사업장 본문이 구법 표현이면 VIOLATION.
  절대 사업장 표현을 따라가서 "이게 맞다" 식으로 verdict 주지 말 것.
- 일반 슬롯에 대해서는 verdict / verdict_reason 을 null 로 둔다.

[found / verdict / AMBIGUOUS 구분]
- found=false: 본문에 그 슬롯 관련 규정 자체가 없을 때
- verdict=AMBIGUOUS: 관련 규정은 있으나(found=true), 적정·부적정 판단이
  본문 정보만으로 곤란할 때 (예: 산안법 적용 업종 여부 판별 안 됨)
- 즉 found=true 가 verdict 의 전제. found=false 면 verdict 도 null.

[결정성]
- 같은 입력에 같은 출력을 보장한다."""


def _build_tool_schema(slots: list[SlotDef]) -> dict[str, Any]:
    """function calling 용 JSON Schema 구성. interpret 슬롯이 1개라도 있으면 verdict 필드 추가."""
    has_interpret = any(s.comparator == "interpret" for s in slots)
    item_required = ["slot_id", "found", "extracted_value", "quote", "confidence"]
    item_props = {
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


def _format_slot_spec(s: SlotDef) -> str:
    parts = [
        f"## {s.slot_id}",
        f"- article: 제{s.article}조" + (f" {s.parent_clause}" if s.parent_clause else ""),
        f"- required: {s.required}",
        f"- comparator: {s.comparator}",
        f"- 추출 대상: {s.extract_target.strip()}",
        f"- extract_schema: {json.dumps(s.extract_schema, ensure_ascii=False)}",
    ]
    if s.master_value:
        parts.append(
            f"- 마스터 기준값(참고용·LLM 은 비교하지 말 것): "
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
    document_text: str,
    slots: list[SlotDef],
    *,
    model: str | None = None,
    api_key: str | None = None,
) -> list[Extraction]:
    """1회 LLM 호출로 N개 슬롯 일괄 추출."""
    if not slots:
        return []
    model_name = get_llm_model(model)

    spec_block = "\n\n".join(_format_slot_spec(s) for s in slots)
    # OpenAI prompt cache 활용 — 사업장 본문이 모든 호출에 동일하므로 prefix 위치에 둠.
    # 호출 간 cached prefix: system + 본문 + 작업 안내. 가변: 슬롯 spec.
    user_prompt = (
        f"=== 사업장 취업규칙 본문 ===\n\n"
        f"{document_text}\n\n"
        f"=== 작업 안내 ===\n"
        f"위 본문에서 아래 슬롯들에 대해 [역할]에 따라 추출하여 submit_extractions 함수로 제출하라.\n\n"
        f"----- 슬롯 spec -----\n\n"
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
    tool_choice = {"type": "function", "function": {"name": "submit_extractions"}}

    # 캐시 확인 — 같은 입력이면 LLM 호출 안 함 (client 생성도 안 함)
    sys_prompt = _system_prompt()
    cache_key = llm_cache.make_key(sys_prompt, user_prompt, schema, model_name)
    cached = llm_cache.get(cache_key)
    if cached is not None:
        payload = cached
        # cache hit — 추가 처리 없이 결과 변환만
    else:
        client = OpenAI(api_key=get_api_key(api_key), timeout=_CALL_TIMEOUT)
        last_err: Exception | None = None
        payload: dict[str, Any] = {}
        for attempt in range(_MAX_RETRIES):
            try:
                resp = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    tools=tools,
                    tool_choice=tool_choice,
                    temperature=0,
                    top_p=1,
                )
                msg = resp.choices[0].message
                if not msg.tool_calls:
                    raise RuntimeError(f"LLM 응답에 tool_call 없음: {msg}")
                args_str = msg.tool_calls[0].function.arguments
                payload = json.loads(args_str)
                llm_cache.put(cache_key, payload)
                break
            except (APITimeoutError, APIConnectionError, RateLimitError) as e:
                last_err = e
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_RETRY_BACKOFF[attempt])
                    continue
                raise
            except Exception as e:
                last_err = e
                raise

    out: list[Extraction] = []
    for item in payload.get("extractions", []):
        out.append(
            Extraction(
                slot_id=item["slot_id"],
                extracted_value=item.get("extracted_value"),
                quote=item.get("quote") or "",
                found=bool(item.get("found")),
                confidence=item.get("confidence"),
                verdict=item.get("verdict"),
                verdict_reason=item.get("verdict_reason"),
            )
        )
    by_id = {e.slot_id: e for e in out}
    ordered = []
    for s in slots:
        if s.slot_id in by_id:
            ordered.append(by_id[s.slot_id])
        else:
            ordered.append(
                Extraction(
                    slot_id=s.slot_id,
                    extracted_value=None,
                    quote="",
                    found=False,
                    confidence=None,
                )
            )
    return ordered
