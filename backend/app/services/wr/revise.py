#
# 원문 보존 수정본 생성 — 공용 revise 서비스 (SC·WR 공유).
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
"""원문 보존 수정본 생성 — 공용 revise 서비스 (SC·WR 공유).

철학: "문제없는 내용은 두고, 수정할 내용만 수정해서 내보낸다."
EC/WS 의 '표준 양식 재작성(generate)' 과 달리, 추출된 **원문 전체를 입력**으로 받아
사용자가 확정한 수정 목록만 반영한 '수정본'을 출력한다.

  - 수정 목록에 없는 문장·조항·서식 → 원문 그대로 보존
  - 수정 목록의 각 항목 → 원문의 해당 위치를 찾아 교체
  - 원문에 아예 없는(누락) 항목 → 문맥상 적절한 위치에 추가

호출자(라우터):
  - POST /sc/generate/start     → run('노무제공자 계약서', ...)
  - POST /review/generate/start → run('취업규칙', ...)

결정성: temperature=0 + llm_cache (schema={"kind": "revise", "doc": doc_label}).
PII: 외부 LLM 호출 직전 원문·수정 목록 모두 마스킹 (ec generate 와 동일 게이트).
"""
from __future__ import annotations

import time

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from app.integrations.llm import cache as llm_cache
from app.core.config import get_api_key, get_llm_model
from app.core.pii_mask import mask_pii_in_payload, mask_pii_text


_CALL_TIMEOUT = 180.0
_MAX_RETRIES = 3
_RETRY_BACKOFF = (2.0, 5.0, 10.0)


def _build_system_prompt(
    doc_label: str, has_standard: bool, mark_changes: bool = False
) -> str:
    base = (
        "당신은 노동법 문서 수정 전문가입니다.\n"
        f"입력된 원문을 **그대로 유지**하되, 아래 수정 목록의 항목만 반영한 "
        f"'{doc_label} 수정본' 전체를 출력하세요.\n\n"
        "규칙:\n"
        "1. 수정 목록에 없는 문장·조항·서식은 한 글자도 바꾸지 않는다.\n"
        "2. 각 수정 항목은 원문에서 해당 위치를 찾아 '수정 문구'로 교체한다.\n"
        "3. 원문에 아예 없는(누락) 항목은 문맥상 적절한 조항 위치에 새로 추가한다.\n"
        "4. 순수 텍스트만 출력한다 — 머리말·해설·마크다운 코드블록 금지.\n"
        "5. **계약서 문체(조문체)로 변환** — '수정 문구'가 설명·권고문\n"
        "   (예: '퇴직금을 제공해야 해요', '~하는 것이 좋습니다', '~를 명시하세요')\n"
        "   이면 절대 그대로 넣지 말고, 실제 계약 조항 문장으로 바꿔 쓴다.\n"
        "   (예: '퇴직금을 제공해야 해요' → '제O조(퇴직급여) 위탁자는 근로자퇴직급여\n"
        "   보장법에 따라 퇴직급여를 지급한다.')\n"
        "   '~해요/~하세요/~좋습니다/권장/필요합니다' 같은 표현은 최종 문서에\n"
        "   등장해서는 안 된다."
    )
    if has_standard:
        base += (
            "\n5. **표준 양식 준용** — 문구를 교체·추가할 때는 [표준 양식] 의 해당 조항"
            " 표현·체계를 기준으로 삼는다. 수정 문구가 표준 양식과 충돌하면 표준 양식의"
            " 법정 기준을 우선하되, 사업장 고유 정보(상호·일자·금액·인명 등)는 반드시"
            " 원문의 값을 유지한다. 표준 양식은 참조 기준일 뿐 — 원문에 없는 조항을"
            " 표준 양식에서 통째로 가져와 덧붙이지 않는다(수정 목록에 있는 항목만 반영)."
        )
    if mark_changes:
        # 주의: 이 규칙은 mark_changes=True 호출(WR)에만 붙는다.
        # False 경로(SC)의 system 프롬프트는 종전과 byte-동일해야 기존 캐시가 유지됨.
        base += (
            "\n6. **수정 위치 마커** — 교체·추가한 모든 문구는 정확히 그 범위만"
            " 【수정】…【/수정】 마커로 감싼다. 수정하지 않은 원문에는 절대 마커를"
            " 붙이지 않는다. 마커는 이 두 토큰 외 다른 형태(괄호 변형·대체 기호·"
            "중첩) 금지."
        )
    return base


def _build_user_prompt(
    original_text: str,
    corrections: list[dict],
    standard_text: str | None,
) -> str:
    lines: list[str] = []
    for i, c in enumerate(corrections, start=1):
        name = str(c.get("name", "")).strip()
        now = str(c.get("now", "")).strip() or "(기재 없음)"
        fix = str(c.get("fix", "")).strip()
        lines.append(f"{i}. [{name}] 현재: {now} → 수정: {fix}")
    corrections_block = "\n".join(lines)
    parts = [f"[원문]\n{original_text}", f"[수정 목록]\n{corrections_block}"]
    if standard_text:
        parts.append(f"[표준 양식 — 수정 문구의 준용 기준]\n{standard_text}")
    return "\n\n".join(parts)


def run(
    doc_label: str,
    original_text: str,
    corrections: list[dict],
    *,
    standard_text: str | None = None,
    model: str | None = None,
    mark_changes: bool = False,
) -> str:
    """원문 + 수정 목록 (+ 표준 양식) → 수정본 전문 텍스트.

    Args:
        doc_label: 문서 이름 (예: '노무제공자 계약서', '취업규칙') — 프롬프트·캐시 키.
        original_text: 추출된 원문 전체.
        corrections: [{"name": 항목명, "now": 현재 표현, "fix": 수정 문구}, ...]
        standard_text: 준용 기준이 되는 표준 양식 전문 (예: 고용노동부 표준취업규칙).
            전달 시 수정 문구가 표준 양식의 조항 표현을 준용하도록 프롬프트에 주입.
        mark_changes: True 면 교체·추가된 문구를 【수정】…【/수정】 마커로 감싸도록
            지시 — 프론트가 하이라이트 렌더에 사용 (WR 전용). 캐시 키 schema 에
            "marked" 가 포함되어 무마커 캐시와 분리된다. 기본 False (SC 경로 불변).

    실패 시 빈 문자열을 반환하지 않고 raise. 호출자는 HTTP 500 처리.
    """
    if not (original_text or "").strip():
        raise ValueError("원문 텍스트가 비어 있습니다.")
    if not corrections:
        raise ValueError("수정 목록이 비어 있습니다. 반영할 항목을 먼저 담아 주세요.")

    # PII 비식별 게이트 — 원문·수정 목록 모두 마스킹 후 외부 전송
    # (표준 양식은 공개 배포 자료라 마스킹 불요)
    original_text = mask_pii_text(original_text)
    corrections = [mask_pii_in_payload(dict(c)) for c in corrections]

    # 표준 양식이 과도하게 길면 컷 — 준용 기준 용도로는 본문 핵심이면 충분
    if standard_text and len(standard_text) > 80_000:
        standard_text = standard_text[:80_000]

    model_name = get_llm_model(model)
    sys_prompt = _build_system_prompt(
        doc_label, has_standard=bool(standard_text), mark_changes=mark_changes
    )
    user_prompt = _build_user_prompt(original_text, corrections, standard_text)

    # 캐시 키 — 마커 모드는 schema 에 명시해 무마커 캐시와 분리.
    # mark_changes=False 일 때는 종전 schema 그대로 (기존 SC 캐시 보존).
    cache_schema: dict = {"kind": "revise", "doc": doc_label}
    if mark_changes:
        cache_schema["marked"] = True
    cache_key = llm_cache.make_key(
        system=sys_prompt,
        user=user_prompt,
        schema=cache_schema,
        model=model_name,
    )
    cached = llm_cache.get(cache_key)
    if cached is not None and isinstance(cached.get("revised_text"), str):
        return cached["revised_text"]

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
                temperature=0,
                top_p=1,
            )
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                raise RuntimeError("수정본 응답이 비어 있습니다.")
            llm_cache.put(cache_key, {"revised_text": text})
            return text
        except (APITimeoutError, APIConnectionError, RateLimitError) as e:
            last_err = e
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_BACKOFF[attempt])
                continue
            raise
        except Exception as e:
            last_err = e
            raise

    raise RuntimeError(f"수정본 생성 호출 실패: {last_err}")
