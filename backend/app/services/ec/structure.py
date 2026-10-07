#
# 근로계약서 OCR 텍스트 → 8섹션 구조화 JSON.
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.05.28      kimzion77   최초 생성
# 2026.10.02      이시영      구조 이행 (backend/cgr → backend/app)
# 2026.10.02      이시영      구조 조정 (web/ai 파트 디렉터리 → 도메인 단일 디렉터리)
#
# Author: kimzion77
# Since: 2026.05.28
#
"""근로계약서 OCR 텍스트 → 8섹션 구조화 JSON.

기존 `server/services/openaiService.js#structureText` 를 옮긴 것.
- system: STRUCTURE_PROMPT
- user:   build_structure_user_prompt(text)
- 출력: 8섹션 + 기타사항 의 dict (`기본정보 / 계약사항 / 근로시간 / 휴일휴가 / 임금 /
  퇴직급여 / 사회보험 / 계약체결 / 기타사항`)

호출자는 Step2 (사용자 검토·수정) 페이지로 이 dict 를 그대로 넘긴다.
"""
from __future__ import annotations

import time
from typing import Any

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from app.services.ec import prompts
from app.integrations.llm import cache as llm_cache
from app.core.config import get_api_key, get_llm_model
from app.core.pii_mask import mask_pii_text


_CALL_TIMEOUT = 60.0
_MAX_RETRIES = 3
_RETRY_BACKOFF = (2.0, 5.0, 10.0)

# 8섹션 빈 골격 — LLM 실패 시 fallback / 사용자 검토 시작점.
_EMPTY_STRUCTURE: dict[str, Any] = {
    "기본정보": {
        "사업장명": {"value": "", "note": ""},
        "사업주성명": {"value": "", "note": ""},
        "사업장소재지": {"value": "", "note": ""},
        "근로자성명": {"value": "", "note": ""},
        "근로자생년월일": {"value": "", "note": ""},
        "근로자주소": {"value": "", "note": ""},
    },
    "계약사항": {
        "근로계약기간": {"value": "", "note": ""},
        "수습기간": {"value": "", "note": ""},
        "근무장소": {"value": "", "note": ""},
        "업무내용": {"value": "", "note": ""},
        "근로계약서교부": {"value": "", "note": ""},
    },
    "근로시간": {
        "소정근로시간": {"value": "", "note": ""},
        "시업시각": {"value": "", "note": ""},
        "종업시각": {"value": "", "note": ""},
        "휴게시간": {"value": "", "note": ""},
    },
    "휴일휴가": {
        "근무일": {"value": "", "note": ""},
        "주휴일": {"value": "", "note": ""},
        "연차유급휴가": {"value": "", "note": ""},
    },
    "임금": {
        "임금총액": {"value": "", "note": ""},
        "기본급": {"value": "", "note": ""},
        "제수당": {"value": "", "note": ""},
        "상여금": {"value": "", "note": ""},
        "임금지급일": {"value": "", "note": ""},
        "임금지급방법": {"value": "", "note": ""},
    },
    "퇴직급여": {"퇴직금": {"value": "", "note": ""}},
    "사회보험": {"4대보험가입여부": {"value": "", "note": ""}},
    "계약체결": {
        "계약서작성일": {"value": "", "note": ""},
        "사업주서명": {"value": "", "note": ""},
        "근로자서명": {"value": "", "note": ""},
        "계약서교부": {"value": "", "note": ""},
    },
    "기타사항": [],
}


def empty_structure() -> dict[str, Any]:
    """8섹션 빈 골격 사본. 사용자가 OCR 결과 없이 처음부터 작성하는 경우 등에 사용."""
    import copy
    return copy.deepcopy(_EMPTY_STRUCTURE)


def run(extracted_text: str, *, model: str | None = None) -> dict[str, Any]:
    """OCR 텍스트를 8섹션 구조화 dict 로 변환.

    실패 시 빈 골격을 반환하지 않고 raise — 호출 라우터에서 HTTP 500 으로 떨어뜨려
    사용자가 재시도하도록. 빈 골격 반환은 의도적 fallback 일 때만.
    """
    if not extracted_text or not extracted_text.strip():
        return empty_structure()

    # PII 비식별 게이트
    extracted_text = mask_pii_text(extracted_text)

    model_name = get_llm_model(model)
    sys_prompt = prompts.get_structure_prompt()
    user_prompt = prompts.build_structure_user_prompt(extracted_text)

    cache_key = llm_cache.make_key(
        system=sys_prompt,
        user=user_prompt,
        schema={"kind": "ec_structure"},
        model=model_name,
    )
    cached = llm_cache.get(cache_key)
    if cached is not None and isinstance(cached.get("structured"), dict):
        return cached["structured"]

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
                response_format={"type": "json_object"},
                temperature=0,
                top_p=1,
                # 구조화는 값 추출이라 장황한 산문 불요 → verbosity low 로 생성 단축.
                verbosity="low",
            )
            raw = resp.choices[0].message.content or ""
            data = prompts.safe_json_parse(raw, default=None)
            if not isinstance(data, dict):
                raise RuntimeError(f"structure 응답이 JSON object 가 아닙니다: {raw[:200]}")
            llm_cache.put(cache_key, {"structured": data})
            return data
        except (APITimeoutError, APIConnectionError, RateLimitError) as e:
            last_err = e
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_BACKOFF[attempt])
                continue
            raise
        except Exception as e:
            last_err = e
            raise

    raise RuntimeError(f"structure 호출 실패: {last_err}")
