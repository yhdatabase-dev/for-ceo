"""취업규칙 근로환경 1차 분류 — 원본 `cgr/wr_classify.py:run` 이관.

원본 로직 요약
- 입력: 추출된 취업규칙 텍스트
- LLM 이 판단: 교대근로/산안법/화학물질/작업환경측정 여부 + 문서 종류
- 출력: {shift_work_used, osha_applicable, chemical_handling, workenv_measurement,
        doc_kind, reason}

이 결과가 WorkplaceContext 로 넘어가 이후 판정에서 슬롯 SKIP 판단에 사용됨.
"""
from __future__ import annotations

import psycopg

from app.core.security import mask_pii_text
from app.integrations.llm.cache import make_cache_key
from app.integrations.llm.client import get_llm_client
from app.integrations.llm.prompts import resolve_prompt
from app.schemas.review.requests import WrClassifyIn
from app.schemas.review.responses import WrClassifyOut
from app.utils.json_repair import safe_json_parse

_PROMPT_KEY = "wr_classify"
_PROMPT_VERSION = "v1"
# 취업규칙은 길다 — 교대제·안전보건 조항이 흩어져 있어 본문 대부분 필요.
# 원본과 동일하게 24k 자 상한 (약 8k 토큰).
_MAX_CHARS = 24_000


class WrClassifyService:
    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db

    def run(self, payload: WrClassifyIn) -> WrClassifyOut:
        text = (payload.extracted_text or "").strip()
        if not text:
            from app.core.exceptions import ValidationError
            raise ValidationError("분류할 텍스트가 비어 있습니다.")

        client = get_llm_client()
        system = resolve_prompt(self.db, _PROMPT_KEY)
        # 원본과 동일하게 8k 토큰 여유 확보 위해 앞 24k 자만 전송
        user = f"[취업규칙 텍스트]\n{mask_pii_text(text[:_MAX_CHARS])}"
        cache_key = make_cache_key(_PROMPT_KEY, _PROMPT_VERSION, system, user)

        resp = client.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},   # 원본과 동일
            cache_key=cache_key,
        )

        parsed = safe_json_parse(resp["content"], default={}) or {}
        osha = _to_bool_or_none(parsed.get("osha_applicable"))
        return WrClassifyOut(
            shift_work_used=_to_bool_or_none(parsed.get("shift_work_used")),
            # 원본 정책: 산안법은 대부분 적용 — 판단 불가면 보수적으로 true
            osha_applicable=True if osha is None else osha,
            chemical_handling=_to_bool_or_none(parsed.get("chemical_handling")),
            workenv_measurement=_to_bool_or_none(parsed.get("workenv_measurement")),
            doc_kind=str(parsed.get("doc_kind") or "취업규칙").strip(),
            reason=str(parsed.get("reason") or "").strip(),
        )


def _to_bool_or_none(v):
    """원본 `cgr/wr_classify.py:_to_bool_or_none` 이관."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "yes", "y", "1", "적용", "해당"):
            return True
        if s in ("false", "no", "n", "0", "미적용", "비해당"):
            return False
    return None
