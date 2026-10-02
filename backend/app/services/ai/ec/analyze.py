"""근로계약서 33-매핑 위반 분석 (LLM).

기존 `server/services/openaiService.js#performLegalAnalysis` 를 옮긴 것.
- system: ANALYSIS_PROMPT (33-매핑 테이블 + meta 태그 지시 포함)
- user:   build_analyze_user_prompt(structured_data, business_size, worker_types, legal_guidelines)
- 출력: 33매핑 검토 결과 dict

출력 JSON 스키마(기존과 동일):
```
{
  "riskLevel": "상/중/하",
  "overallStatus": "위험/보완필요/적정",
  "overallOpinion": "전반적인 검토 결과 총평",
  "results": [
    {
      "항목": str,
      "적용조건": "공통/5인이상/...",
      "서면명시의무": str,
      "적절성": "적절/부적절/보완필요",
      "판단이유": str  // <meta db='...' n='...' /> 태그 포함
      "발견내용": str,
      "법적근거": str,
      "개선권고": str,
    }
  ],
  "finalRecommendations": str,
}
```
"""
from __future__ import annotations

import re
import time
from typing import Any

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from app.services.ai.ec import prompts
from app.services.ai.ec.topic_lookup import topics_for_item
from app.integrations.llm import cache as llm_cache
from app.core.config import get_api_key, get_llm_model
from app.core.pii_mask import mask_pii_in_payload


_CALL_TIMEOUT = 120.0  # 분석은 출력 길어서 여유 있게

_META_RE = re.compile(r"<meta\b[^>]*?>", re.IGNORECASE)


def _attach_real_topic_refs(data: dict[str, Any]) -> dict[str, Any]:
    """LLM 이 판단이유에 넣은 <meta> 태그(부정확·환각: 'DB_xxx 1.1' 같은 placeholder)를
    제거하고, 각 항목의 **DB 실제 연관주제**(check_item_topic 조인)로 교체한다.
    → '참고 자료' 칩이 항상 정확한 주제·섹션을 가리킨다(결정적). idempotent."""
    try:
        results = data.get("results")
        if not isinstance(results, list):
            return data
        for item in results:
            if not isinstance(item, dict):
                continue
            field = (item.get("항목") or "").strip()
            reason = _META_RE.sub("", item.get("판단이유") or "")
            reason = re.sub(r"\s{2,}", " ", reason).strip()
            refs = (topics_for_item(field) if field else [])[:4]  # 칩 과다 방지
            metas = "".join(
                f"<meta db='DB_{topic}' n='{sec}' />" for topic, sec in refs
            )
            item["판단이유"] = (reason + (" " + metas if metas else "")).strip()
    except Exception:
        pass
    return data


# ── 임금 합계 결정적 검산 — LLM 산술 환각으로 인한 오탐 제거 ──
# LLM 은 산수를 신뢰성 있게 못 해서, 구성항목 합계가 지급총액과 맞는데도
# "합계 불일치"라며 부적절로 잡는 false positive 가 발생한다(자기모순 문구 포함).
# 여기서 코드로 직접 더해 일치하면 그 '산술 트집'을 무력화한다.
_NUM_RE = re.compile(r"-?\d[\d,]*")
# 합계 정합성과 관련된 표현(이게 있으면 '산술 트집' finding 으로 간주)
_SUM_KW = ("합계", "합산", "산식", "정합", "일치하지", "구성항목", "총액")
# 진짜 위반 신호(이게 있으면 등급은 유지하고 산술 문구만 정정)
_VIOL_KW = ("최저임금", "미달", "미만", "누락", "위반", "서면", "명시")


def _won(s: Any) -> int | None:
    """'4,259,070원' 같은 문자열에서 정수 금액 추출. 숫자 없으면 None."""
    m = _NUM_RE.search(str(s or ""))
    if not m:
        return None
    try:
        return int(m.group().replace(",", ""))
    except ValueError:
        return None


def _wage_total_consistent(structured_data: dict[str, Any]) -> tuple[bool, int, int] | None:
    """임금 섹션의 (기본급+제수당+상여금) 합계가 임금총액과 일치하는지 결정적으로 판단.
    반환: (consistent, comp_sum, total) 또는 검산 불가 시 None."""
    try:
        wage = structured_data.get("임금")
        if not isinstance(wage, dict):
            return None

        def _val(key: str) -> int | None:
            cell = wage.get(key)
            if isinstance(cell, dict):
                return _won(cell.get("value"))
            return _won(cell)

        total = _val("임금총액")
        if total is None or total <= 0:
            return None  # 총액 자체가 미기재/비정상 → 검산 불가(보수적으로 손대지 않음)
        comps = [_val("기본급"), _val("제수당"), _val("상여금")]
        nums = [c for c in comps if c is not None]
        if not nums:
            return None
        comp_sum = sum(nums)
        # 1원 이내(반올림 허용) 일치 → 정합
        return (abs(comp_sum - total) <= 1, comp_sum, total)
    except Exception:
        return None


def _reconcile_wage_total(data: dict[str, Any], structured_data: dict[str, Any]) -> dict[str, Any]:
    """구성항목 합계가 지급총액과 일치하면, '합계 불일치'성 오탐을 정정한다. idempotent."""
    try:
        check = _wage_total_consistent(structured_data)
        if check is None:
            return data
        consistent, comp_sum, total = check
        if not consistent:
            return data  # 실제로 안 맞으면 LLM 판정을 존중

        results = data.get("results")
        if not isinstance(results, list):
            return data

        changed = False
        for item in results:
            if not isinstance(item, dict):
                continue
            field = (item.get("항목") or "")
            text = (item.get("판단이유") or "") + " " + (item.get("발견내용") or "")
            is_total_item = ("총액" in field) or ("합계" in field)
            mentions_sum = any(k in text for k in _SUM_KW)
            # 임금총액 항목이거나, 임금류 항목이 합계 트집을 잡은 경우만 대상
            if not (is_total_item or ("임금" in field and mentions_sum)):
                continue
            if (item.get("적절성") or "") == "적절":
                continue
            has_violation = any(k in text for k in _VIOL_KW)
            fact = f"구성항목 합계({comp_sum:,}원)가 지급합계액({total:,}원)과 정확히 일치합니다."
            if mentions_sum and not has_violation:
                # 오탐 — 산술 트집뿐 → 적절로 정정
                item["적절성"] = "적절"
                item["판단이유"] = fact
                item["발견내용"] = fact
                item["개선권고"] = ""
                changed = True
            else:
                # 다른 실제 위반과 섞임 → 등급 유지, 산술 정합 사실만 덧붙임
                reason = (item.get("판단이유") or "").strip()
                if "일치합니다" not in reason:
                    item["판단이유"] = (reason + " " + fact).strip()
                    changed = True

        # 등급을 바꿨다면 총평/위험도도 항목 등급에서 결정적으로 재계산
        if changed:
            grades = [(it.get("적절성") or "") for it in results if isinstance(it, dict)]
            n_bad = sum(1 for g in grades if g == "부적절")
            n_warn = sum(1 for g in grades if g == "보완필요")
            data["overallStatus"] = "위험" if n_bad else ("보완필요" if n_warn else "적정")
            data["riskLevel"] = "상" if n_bad else ("중" if n_warn else "하")
    except Exception:
        pass
    return data


def _postprocess(data: dict[str, Any], structured_data: dict[str, Any]) -> dict[str, Any]:
    """분석 결과 결정적 후처리 — 참고자료 칩 교정 + 임금합계 오탐 정정. idempotent."""
    data = _attach_real_topic_refs(data)
    data = _reconcile_wage_total(data, structured_data)
    return data


_MAX_RETRIES = 3
_RETRY_BACKOFF = (2.0, 5.0, 10.0)


_FALLBACK_RESULT: dict[str, Any] = {
    "riskLevel": "중",
    "overallStatus": "보완필요",
    "overallOpinion": "분석 중 오류가 발생했습니다.",
    "results": [],
    "finalRecommendations": "시스템 오류로 인해 분석을 완료하지 못했습니다. 다시 시도해주세요.",
}


def run(
    structured_data: dict[str, Any],
    business_size: str,
    worker_types: list[str],
    *,
    legal_guidelines: str = "",
    model: str | None = None,
) -> dict[str, Any]:
    """구조화된 근로계약서 + 사용자 컨텍스트 → 위반 분석 결과 dict.

    `legal_guidelines` 는 기존 RAG 검색 결과 자리. 풀 이식 1단계는 빈 문자열로 가고,
    이후 단계에서 슬롯·주제 임베딩 매칭으로 채울 예정.
    """
    if not isinstance(structured_data, dict):
        raise ValueError("structured_data 가 dict 가 아닙니다.")

    # PII 비식별 게이트 — 8섹션 중첩 dict 모든 string 값 마스킹
    structured_data = mask_pii_in_payload(structured_data)

    model_name = get_llm_model(model)
    sys_prompt = prompts.get_analysis_prompt()
    user_prompt = prompts.build_analyze_user_prompt(
        structured_data=structured_data,
        business_size=business_size or "",
        worker_types=worker_types or [],
        legal_guidelines=legal_guidelines or "",
    )

    cache_key = llm_cache.make_key(
        system=sys_prompt,
        user=user_prompt,
        schema={"kind": "ec_analyze"},
        model=model_name,
    )
    cached = llm_cache.get(cache_key)
    if cached is not None and isinstance(cached.get("analysis"), dict):
        # 구 캐시(부정확 meta·합계 오탐)도 결정적으로 교정해 반환 (idempotent)
        return _postprocess(cached["analysis"], structured_data)

    client = OpenAI(api_key=get_api_key(), timeout=_CALL_TIMEOUT)
    last_err: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        try:
            # 주의: max_tokens 를 지정하지 말 것 — gpt-5.x 계열은 이 파라미터를
            # 거부함(max_completion_tokens 사용). 미지정 시 모델 기본 최대치 사용.
            # truncation 은 비동기 잡(게이트웨이 타임아웃 우회)으로 이미 해결됨.
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                top_p=1,
                # gpt-5.x 출력 장황함 축소 — 33항목 JSON 생성 시간을 ~15-20% 단축.
                # 스키마/판단은 유지하고 산문만 간결화(측정: 4778→3767 토큰).
                verbosity="low",
            )
            raw = resp.choices[0].message.content or ""
            data = prompts.safe_json_parse(raw, default=None)
            if not isinstance(data, dict) or "results" not in data:
                raise RuntimeError(
                    f"analyze 응답 형식이 올바르지 않습니다: {raw[:200]}"
                )
            # 결정적 후처리 — 참고자료 칩 교정 + 임금합계 오탐 정정
            data = _postprocess(data, structured_data)
            # 캐시 저장 — 같은 입력 → 같은 결과 (결정성)
            llm_cache.put(cache_key, {"analysis": data})
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

    raise RuntimeError(f"analyze 호출 실패: {last_err}")


def fallback_result() -> dict[str, Any]:
    """LLM 미가용 등 비상 fallback. 호출자가 명시적으로 사용해야 한다."""
    import copy
    return copy.deepcopy(_FALLBACK_RESULT)
