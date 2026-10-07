#
# 취업규칙 1차 분류 (LLM) — 근로환경 특성 자동 판별.
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.06.12      kimzion77   최초 생성
# 2026.10.02      이시영      구조 이행 (backend/cgr → backend/app)
# 2026.10.02      이시영      구조 조정 (web/ai 파트 디렉터리 → 도메인 단일 디렉터리)
#
# Author: kimzion77
# Since: 2026.06.12
#
"""취업규칙 1차 분류 (LLM) — 근로환경 특성 자동 판별.

사업장들은 교대제·산안법 적용·화학물질·작업환경측정 같은 근로환경 항목을
잘 모른다. 업로드된 취업규칙 텍스트를 AI 가 먼저 읽고 추정하고, 사용자는
그 결과를 확인만 한다 (틀렸다고 할 때만 직접 고른다) — EC 근로자 유형
분류와 동일한 UX 철학.

출력 스키마:
```
{
  "shift_work_used": true | false | null,      # 교대근로 도입
  "osha_applicable": true | false,             # 산업안전보건법 적용 업종
  "chemical_handling": true | false | null,    # 화학물질 취급
  "workenv_measurement": true | false | null,  # 작업환경측정 대상
  "doc_kind": "제조업 취업규칙",                 # 사용자에게 보여줄 한 줄 명칭
  "reason": "교대근무 조항(제25조)이 있고 ..."   # 판단 근거 1~2문장
}
```
null = 취업규칙 본문만으로는 판단 불가(모름) — 검토 룰은 보수적으로 검사함.
"""
from __future__ import annotations

import json
import time
from typing import Any

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from app.integrations.llm import cache as llm_cache
from app.core.config import get_api_key, get_llm_model
from app.services.ec import prompts
from app.core.pii_mask import mask_pii_in_payload

_CALL_TIMEOUT = 90.0
_MAX_RETRIES = 3
_RETRY_BACKOFF = (2.0, 5.0, 10.0)

# 취업규칙은 길다 — 교대제는 근로시간 장, 안전보건은 별도 장에 흩어져 있어
# 분류엔 본문 대부분이 필요. 약 8k 토큰 분량까지만 전송.
_MAX_CHARS = 24_000

_SYSTEM = (
    "너는 한국 노동법 취업규칙 분석 전문가다. 입력된 취업규칙 텍스트를 읽고\n"
    "이 사업장의 근로환경 특성을 추정해 JSON 으로만 답한다.\n\n"
    "판별 항목:\n"
    "- shift_work_used (교대근로 도입): 교대제·교대근무·2조2교대·3조3교대 등 조항이\n"
    "  실제 운영 전제로 규정되어 있으면 true, '도입할 수 있다' 수준의 일반 문구만\n"
    "  있거나 언급이 없으면 false, 정말 판단 불가면 null\n"
    "- osha_applicable (산업안전보건법 적용 업종): 본문의 업종·직무 단서(제조·건설·\n"
    "  운수·음식점 등)로 추정. 대부분의 업종이 적용 대상이므로 명백한 적용 제외\n"
    "  단서가 없으면 true\n"
    "- chemical_handling (화학물질 취급): 유해물질·화학물질·MSDS·보호구 착용 조항\n"
    "  등 단서가 있으면 true, 사무직·서비스업 등 취급 정황이 없으면 false,\n"
    "  판단 불가면 null\n"
    "- workenv_measurement (작업환경측정 대상): 소음·분진·유기용제 등 측정 대상\n"
    "  유해인자 단서가 있으면 true, 없으면 false, 판단 불가면 null\n\n"
    "출력 JSON 스키마 (이 키만):\n"
    '{"shift_work_used": true/false/null, "osha_applicable": true/false, '
    '"chemical_handling": true/false/null, "workenv_measurement": true/false/null, '
    '"doc_kind": "사용자에게 보여줄 한 줄 명칭 (예: 제조업 취업규칙)", '
    '"reason": "판단 근거 1~2문장 (사장님이 읽을 쉬운 한국어)"}'
)


def _to_bool_or_none(v: Any) -> bool | None:
    """LLM 출력의 true/false/null 외 변형("yes" 등)을 안전하게 정규화."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "yes", "y", "도입", "해당"):
            return True
        if s in ("false", "no", "n", "미도입", "비해당"):
            return False
    return None


def run(extracted_text: str, *, model: str | None = None) -> dict[str, Any]:
    """취업규칙 텍스트 → 근로환경 추정 dict. 실패 시 raise."""
    text = (extracted_text or "").strip()
    if not text:
        raise ValueError("분류할 텍스트가 비어 있습니다.")

    masked = mask_pii_in_payload({"t": text[:_MAX_CHARS]})["t"]
    user_prompt = f"[취업규칙 텍스트]\n{masked}"

    model_name = get_llm_model(model)
    cache_key = llm_cache.make_key(
        system=_SYSTEM,
        user=user_prompt,
        schema={"kind": "wr_classify"},
        model=model_name,
    )
    cached = llm_cache.get(cache_key)
    if cached is not None and isinstance(cached.get("classify"), dict):
        return cached["classify"]

    client = OpenAI(api_key=get_api_key(), timeout=_CALL_TIMEOUT)
    last_err: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                top_p=1,
            )
            raw = resp.choices[0].message.content or ""
            data = prompts.safe_json_parse(raw, default=None)
            if not isinstance(data, dict):
                raise RuntimeError(f"wr classify 응답 형식 오류: {raw[:120]}")
            osha = _to_bool_or_none(data.get("osha_applicable"))
            out = {
                "shift_work_used": _to_bool_or_none(data.get("shift_work_used")),
                # 산안법은 대부분 적용 — 판단 불가면 보수적으로 true
                "osha_applicable": True if osha is None else osha,
                "chemical_handling": _to_bool_or_none(data.get("chemical_handling")),
                "workenv_measurement": _to_bool_or_none(data.get("workenv_measurement")),
                "doc_kind": str(data.get("doc_kind") or "취업규칙").strip(),
                "reason": str(data.get("reason") or "").strip(),
            }
            llm_cache.put(cache_key, {"classify": out})
            return out
        except (APITimeoutError, APIConnectionError, RateLimitError) as e:
            last_err = e
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_BACKOFF[attempt])
                continue
            raise
        except json.JSONDecodeError as e:
            last_err = e
            raise
    raise RuntimeError(f"wr classify 호출 실패: {last_err}")
