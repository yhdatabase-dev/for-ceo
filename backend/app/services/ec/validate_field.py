#
# 근로계약서 — 단일 항목 즉시 재검토 (칸 편집 후 blur 시).
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.06.22      kimzion77   최초 생성
# 2026.10.02      이시영      구조 이행 (backend/cgr → backend/app)
# 2026.10.02      이시영      구조 조정 (web/ai 파트 디렉터리 → 도메인 단일 디렉터리)
#
# Author: kimzion77
# Since: 2026.06.22
#
"""근로계약서 — 단일 항목 즉시 재검토 (칸 편집 후 blur 시).

표준 계약서 작성 화면에서 사용자가 한 칸을 고치면, 그 칸 하나만 적정/부적정을
빠르게 재판정한다(전체 33매핑 재분석이 아니라 항목 1개 — 빠르고 저렴).

- temp=0 + llm_cache → 같은 (항목, 값, 컨텍스트) = 같은 판정(결정성).
- PII 는 호출 전 마스킹.
- 출력: {"적절성": "적절"|"보완필요"|"부적정", "이유": "한 줄"}.
"""
from __future__ import annotations

import json
import time
from typing import Any

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from app.integrations.llm import cache as llm_cache
from app.core.config import get_api_key, get_llm_model
from app.core.pii_mask import mask_pii_text


_CALL_TIMEOUT = 30.0  # 항목 1개라 짧게
_MAX_RETRIES = 2
_RETRY_BACKOFF = (1.5, 4.0)

_SYSTEM_PROMPT = """\
당신은 한국 근로기준법 전문가입니다.
근로계약서의 **특정 항목 한 개**에 입력된 값이 법적으로 적정한지 판정합니다.

[판정 기준]
- "적절": 법정 필수 내용이 충족되고 위반 소지가 없음.
- "보완필요": 기재는 있으나 불충분·모호하거나 일부 보완이 필요함.
- "부적정": 빈칸이거나 법정 필수 내용이 누락·법 위반 소지가 있음.

[출력 — JSON 한 개만, 다른 텍스트 금지]
{
  "적절성": "적절" | "보완필요" | "부적정",
  "이유": "판정 근거 한 줄(40자 내외)",
  "작성예시": "적절이 아니면, 이 칸에 그대로 적을 수 있는 간단한 예시 문구 한 줄. 적절이면 빈 문자열"
}

[작성예시 규칙]
- "부적정"·"보완필요" 이면 **반드시** 비어있지 않게 채운다(빈 문자열 금지). 그 칸에
  **그대로 입력 가능한** 구체적 예시(법정 기준 충족)를 한 줄로.
  예) 휴게시간 → "근로시간 4시간마다 30분 이상 부여"
  예) 업무내용 → "생산보조 — 포장·출고보조 등 OO라인 담당"
- "적절" 이면 "작성예시": "" (빈 문자열).
"""


def _safe_json(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```")
        try:
            return json.loads(cleaned)
        except Exception:
            return None


def validate_field(
    field: str,
    value: str,
    *,
    business_size: str = "",
    worker_types: list[str] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """근로계약서 항목 1개 재판정 → {"적절성", "이유"}."""
    field = (field or "").strip()
    value = mask_pii_text((value or "").strip())
    worker_types = worker_types or []
    if not field:
        return {"적절성": "보완필요", "이유": "항목명이 비어 있습니다.", "작성예시": ""}

    model_name = get_llm_model(model)
    user_prompt = (
        f"[항목] {field}\n"
        f"[입력값] {value or '(빈칸)'}\n"
        f"[사업장] 상시근로자 {business_size or '미상'}"
        f"{' · 유형 ' + ', '.join(worker_types) if worker_types else ''}\n\n"
        f"위 항목의 입력값이 근로기준법상 적정한지 판정하세요. "
        f"빈칸이거나 법정 필수 내용(예: 기간·시간·금액·구체 조건)이 빠졌으면 "
        f"'부적정' 또는 '보완필요' 로 판정합니다."
    )

    cache_key = llm_cache.make_key(
        system=_SYSTEM_PROMPT,
        user=user_prompt,
        schema={"kind": "ec_validate_field_v2"},
        model=model_name,
    )
    cached = llm_cache.get(cache_key)
    if cached is not None and isinstance(cached.get("verdict"), dict):
        return cached["verdict"]

    client = OpenAI(api_key=get_api_key(), timeout=_CALL_TIMEOUT)
    last_err: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                top_p=1,
            )
            data = _safe_json(resp.choices[0].message.content or "")
            verdict = "보완필요"
            reason = ""
            example = ""
            if isinstance(data, dict):
                v = str(data.get("적절성") or "").strip()
                if v in ("적절", "보완필요", "부적정"):
                    verdict = v
                reason = str(data.get("이유") or "").strip()
                example = str(data.get("작성예시") or "").strip()
            # 적절이면 예시 불필요
            if verdict == "적절":
                example = ""
            out = {"적절성": verdict, "이유": reason, "작성예시": example}
            llm_cache.put(cache_key, {"verdict": out})
            return out
        except (APITimeoutError, APIConnectionError, RateLimitError) as e:
            last_err = e
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_BACKOFF[attempt])
                continue
            raise
        except Exception as e:
            last_err = e
            raise

    raise RuntimeError(f"validate_field 호출 실패: {last_err}")
