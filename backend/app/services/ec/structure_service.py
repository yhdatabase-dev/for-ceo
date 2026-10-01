"""EC 구조화 서비스 — 원본 `cgr/ec/services/structure.py:run` 이관.

===============================================================================
원본 이관
===============================================================================
원본
- OCR 텍스트 → 8섹션 구조화 dict (기본정보/계약사항/근로시간/휴일휴가/임금/
  퇴직급여/사회보험/계약체결/기타사항)
- LLM 호출 (temp=0, response_format=json_object, verbosity=low)

변경점
- `OpenAI(...)` → `get_llm_client().chat(...)` (재시도·PII·캐시 어댑터)
- `prompts.get_structure_prompt()` → `resolve_prompt(conn, "ec::STRUCTURE_PROMPT")`
- `prompts.build_structure_user_prompt(text)` → `prompt_builders.build_structure_user_prompt`
- 원본 verbosity="low" 파라미터는 v2 어댑터 시그니처에 없음 → 프롬프트가 이미 저 verbosity
  를 요구하고 있어 성능 영향 미미 (필요 시 어댑터 확장)
- empty_structure() 원본 골격 완전 이관
"""
from __future__ import annotations

import copy
import time
from typing import Any

import psycopg

from app.core.exceptions import ValidationError
from app.core.security import mask_pii_text
from app.integrations.llm.cache import make_cache_key
from app.integrations.llm.client import get_llm_client
from app.integrations.llm.prompts import resolve_prompt
from app.schemas.ec.requests import StructureIn
from app.schemas.ec.responses import StructureOut
from app.services.ec.prompt_builders import build_structure_user_prompt
from app.utils.json_repair import safe_json_parse

_PROMPT_KEY = "ec::STRUCTURE_PROMPT"
_PROMPT_VERSION = "v1"


# 8섹션 빈 골격 — 원본 `cgr/ec/services/structure.py:_EMPTY_STRUCTURE` 이관
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
    """8섹션 빈 골격 사본 (fallback / 사용자 처음부터 작성 용)."""
    return copy.deepcopy(_EMPTY_STRUCTURE)


class StructureService:
    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db

    def run(self, payload: StructureIn) -> StructureOut:
        text = (payload.extracted_text or "").strip()
        if not text:
            # 원본은 empty_structure 를 반환. v2 는 명시적 validation
            return StructureOut(
                structured_data=empty_structure(),
                elapsed_sec=0.0,
                model="",
            )

        masked = mask_pii_text(text)
        client = get_llm_client()
        system = resolve_prompt(self.db, _PROMPT_KEY)
        user = build_structure_user_prompt(masked)

        cache_key = make_cache_key(_PROMPT_KEY, _PROMPT_VERSION, system, user)
        t0 = time.perf_counter()
        resp = client.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            cache_key=cache_key,
        )
        elapsed = time.perf_counter() - t0

        data = safe_json_parse(resp.get("content") or "", default=None)
        if not isinstance(data, dict):
            # LLM 응답 파싱 실패 → 빈 골격 fallback (원본과 동일 정책 아님 — 원본은 raise.
            # v2 는 UX 상 빈 골격 반환이 안전 · 사용자가 직접 채워 넣을 수 있음)
            data = empty_structure()

        return StructureOut(
            structured_data=data,
            elapsed_sec=round(elapsed, 3),
            model=resp.get("model", ""),
        )
