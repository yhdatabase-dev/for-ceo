"""EC 근로자 유형 분류 서비스 — 원본 `cgr/ec/services/classify.py:run` 이관.

원본 로직 요약
- 입력: extracted_text
- 출력: {worker_types: list[str], doc_kind: str, reason: str}
- LLM 이 계약서를 읽어 정규직/기간제/단시간/일용직/연소자/외국인 중 해당 분류.
"""
from __future__ import annotations

import time

import psycopg

from app.core.exceptions import ValidationError
from app.core.security import mask_pii_text
from app.integrations.llm.cache import make_cache_key
from app.integrations.llm.client import get_llm_client
from app.integrations.llm.prompts import resolve_prompt
from app.integrations.llm.prompts.ec import EC_ALLOWED_WORKER_TYPES
from app.schemas.ec.requests import ClassifyIn
from app.schemas.ec.responses import ClassifyOut
from app.utils.json_repair import safe_json_parse

_PROMPT_KEY = "ec_classify"
_PROMPT_VERSION = "v1"
# 원본과 동일 — 분류에는 앞 6000자면 충분
_MAX_CHARS = 6000


class ClassifyService:
    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db

    def run(self, payload: ClassifyIn) -> ClassifyOut:
        text = (payload.extracted_text or "").strip()
        if not text:
            raise ValidationError("분류할 텍스트가 비어 있습니다.")

        client = get_llm_client()
        system = resolve_prompt(self.db, _PROMPT_KEY)
        masked = mask_pii_text(text[:_MAX_CHARS])
        user = f"[근로계약서 텍스트]\n{masked}"

        cache_key = make_cache_key(_PROMPT_KEY, _PROMPT_VERSION, system, user)
        t0 = time.perf_counter()
        resp = client.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},   # 원본 동일
            cache_key=cache_key,
        )
        elapsed = time.perf_counter() - t0

        parsed = safe_json_parse(resp["content"], default={}) or {}
        # 허용 목록 밖 값 필터 (원본 정책)
        types = [
            t for t in (parsed.get("worker_types") or [])
            if t in EC_ALLOWED_WORKER_TYPES
        ]
        if not types:
            types = ["정규직"]

        return ClassifyOut(
            worker_types=types,
            doc_kind=str(parsed.get("doc_kind") or "근로계약서").strip(),
            reason=str(parsed.get("reason") or "").strip(),
            elapsed_sec=round(elapsed, 3),
            model=resp.get("model", ""),
        )
