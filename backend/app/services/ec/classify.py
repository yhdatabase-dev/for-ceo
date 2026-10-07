#
# 근로계약서 1차 분류 (LLM) — 근로자 유형 자동 판별.
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.06.11      kimzion77   최초 생성
# 2026.10.02      이시영      구조 이행 (backend/cgr → backend/app)
# 2026.10.02      이시영      구조 조정 (web/ai 파트 디렉터리 → 도메인 단일 디렉터리)
#
# Author: kimzion77
# Since: 2026.06.11
#
"""근로계약서 1차 분류 (LLM) — 근로자 유형 자동 판별.

업로드된 계약서 텍스트를 보고 어떤 근로자 유형의 계약서인지 AI 가 먼저
판단한다. 사용자는 그 결과를 확인만 하면 되고, 틀렸다고 할 때만 직접
유형을 고른다 (UX: 선택 부담 제거).

출력 스키마:
```
{
  "worker_types": ["기간제", "단시간"],   # 복수 가능
  "doc_kind": "기간제·단시간 근로계약서",  # 사용자에게 보여줄 한 줄 명칭
  "reason": "계약기간이 명시되고 주 소정근로시간이 30시간으로 ..."
}
```
worker_types 는 프론트 ALL_WORKER_TYPES 와 정확히 일치해야 한다:
정규직 / 기간제 / 단시간 / 일용직 / 연소자 / 외국인 / 외국인-농축어업
"""
from __future__ import annotations

import json
import time
from typing import Any

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from app.services.ec import prompts
from app.integrations.llm import cache as llm_cache
from app.core.config import get_api_key, get_llm_model
from app.core.pii_mask import mask_pii_in_payload

_CALL_TIMEOUT = 60.0
_MAX_RETRIES = 3
_RETRY_BACKOFF = (2.0, 5.0, 10.0)

# 프론트 WorkplaceForm.ALL_WORKER_TYPES 와 1:1 — 변경 시 양쪽 함께.
ALLOWED_TYPES = [
    "정규직",
    "기간제",
    "단시간",
    "일용직",
    "연소자",
    "외국인",
    "외국인-농축어업",
]

_SYSTEM = (
    "너는 한국 노동법 근로계약서 분류 전문가다. 입력된 근로계약서 텍스트를 보고\n"
    "어떤 근로자 유형의 계약서인지 판별해 JSON 으로만 답한다.\n\n"
    "허용되는 worker_types 값 (이 목록의 문자열만, 복수 선택 가능):\n"
    f"  {', '.join(ALLOWED_TYPES)}\n\n"
    "판별 기준:\n"
    "- 기간제: 계약 종료일이 명시되거나 '계약기간 만료' 문구가 있음\n"
    "- 단시간: 1주 소정근로시간이 통상 근로자(40시간)보다 짧음, '파트타임'·'아르바이트'\n"
    "- 일용직: 일 단위 고용, 일당 표기\n"
    "- 연소자: 만 18세 미만, 친권자·후견인 동의 관련 문구\n"
    "- 외국인: 외국인등록번호·체류자격·E-9 등 문구 (농축어업이면 외국인-농축어업)\n"
    "- 위에 해당 없으면 정규직\n"
    "- 복수 해당 가능 (예: 기간제이면서 단시간)\n\n"
    "출력 JSON 스키마 (이 키만):\n"
    '{"worker_types": ["..."], "doc_kind": "사용자에게 보여줄 한 줄 명칭 (예: 기간제 근로계약서)", '
    '"reason": "판단 근거 1~2문장 (사장님이 읽을 쉬운 한국어)"}'
)


def run(extracted_text: str, *, model: str | None = None) -> dict[str, Any]:
    """계약서 텍스트 → {worker_types, doc_kind, reason}. 실패 시 raise."""
    text = (extracted_text or "").strip()
    if not text:
        raise ValueError("분류할 텍스트가 비어 있습니다.")

    # PII 마스킹 + 길이 제한 (분류엔 앞부분이면 충분)
    masked = mask_pii_in_payload({"t": text[:6000]})["t"]
    user_prompt = f"[근로계약서 텍스트]\n{masked}"

    model_name = get_llm_model(model)
    cache_key = llm_cache.make_key(
        system=_SYSTEM,
        user=user_prompt,
        schema={"kind": "ec_classify"},
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
                raise RuntimeError(f"classify 응답 형식 오류: {raw[:120]}")
            # 허용 목록 밖 값 필터 — LLM 이 변형해서 내도 안전
            types = [t for t in (data.get("worker_types") or []) if t in ALLOWED_TYPES]
            if not types:
                types = ["정규직"]
            out = {
                "worker_types": types,
                "doc_kind": str(data.get("doc_kind") or "근로계약서").strip(),
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
        except json.JSONDecodeError as e:  # safe_json_parse 가 처리하지만 방어
            last_err = e
            raise
    raise RuntimeError(f"classify 호출 실패: {last_err}")
