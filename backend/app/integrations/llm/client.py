"""LLM 클라이언트 어댑터 — 모델 교체형.

===============================================================================
원본 대비 주요 변경
===============================================================================
원본
- 각 서비스 파일 (`extractor.py`, `explainer.py`, `ec/services/*.py` 등) 이
  `OpenAI(api_key=get_api_key(), timeout=...)` 를 직접 인스턴스화 (13곳).
- 모델 교체·재시도·게이트웨이 통과가 각자 구현.

v2
- `LLMClient` 프로토콜을 정의하고 이를 감싸는 단일 진입점 (`get_llm_client()`).
- 서비스는 `client.chat(...)` / `client.embed(...)` 만 호출.
- 어댑터 내부에서: PII 게이트웨이 통과 → 캐시 조회 → OpenAI 호출 → 캐시 저장.
- RFP §C6 "LLM 어댑터는 모델 교체 가능한 구조" 를 코드 레벨에서 강제.
- 온프렘 모델 도입 시 새 어댑터 클래스만 추가.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Protocol

from openai import OpenAI

from app.core.config import get_settings
from app.core.exceptions import LLMError
from app.core.logging import get_logger
from app.core.security import ensure_masked_before_llm
from app.integrations.llm.cache import cache_get, cache_put, make_cache_key

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────
# 프로토콜 — 어댑터 교체점
# ─────────────────────────────────────────────────────────────
class LLMClient(Protocol):
    """LLM 어댑터 인터페이스. 온프렘·상용 무관하게 이걸 만족하면 됨."""

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        cache_key: str | None = None,
    ) -> dict[str, Any]:
        """채팅/추론 호출.

        반환:
            {
                "content": str,           # LLM 텍스트 응답
                "tool_calls": list | None,# function-calling 결과
                "model": str,             # 실제 사용된 모델명
                "usage": dict,            # 토큰 사용량
                "cache_hit": bool,
            }
        """
        ...

    def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        """텍스트 임베딩."""
        ...


# ─────────────────────────────────────────────────────────────
# OpenAI 어댑터 (기본 구현)
# ─────────────────────────────────────────────────────────────
class OpenAIAdapter:
    """OpenAI Chat Completions + Embeddings 어댑터.

    모든 호출은:
    1) messages 안의 user/system content 를 게이트웨이(`ensure_masked_before_llm`) 통과
    2) cache_key 있으면 캐시 조회 (hit 시 API 호출 안 함)
    3) OpenAI 호출
    4) cache_key 있으면 저장
    5) 표준화된 응답 dict 반환
    """

    def __init__(self, api_key: str, default_model: str) -> None:
        self._client = OpenAI(api_key=api_key, timeout=60.0)
        self._default_model = default_model

    def _mask_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """user/system content 를 PII 게이트웨이 통과."""
        out = []
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, str) and content:
                content = ensure_masked_before_llm(content)
            out.append({**m, "content": content})
        return out

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        cache_key: str | None = None,
    ) -> dict[str, Any]:
        mdl = model or self._default_model
        messages = self._mask_messages(messages)

        # 캐시 조회
        if cache_key:
            hit = cache_get(cache_key)
            if hit is not None:
                return {**hit, "cache_hit": True}

        # OpenAI 호출
        try:
            kwargs: dict[str, Any] = {
                "model": mdl,
                "messages": messages,
                "temperature": temperature,
            }
            if response_format:
                kwargs["response_format"] = response_format
            if tools:
                kwargs["tools"] = tools
            resp = self._client.chat.completions.create(**kwargs)
        except Exception as e:  # noqa: BLE001
            log.exception("llm.openai_error", extra={"model": mdl})
            raise LLMError(f"OpenAI 호출 실패: {e}", meta={"model": mdl}) from e

        # 응답 표준화
        choice = resp.choices[0]
        result = {
            "content": choice.message.content or "",
            "tool_calls": (
                [tc.model_dump() for tc in (choice.message.tool_calls or [])]
                if choice.message.tool_calls
                else None
            ),
            "model": resp.model,
            "usage": (resp.usage.model_dump() if resp.usage else {}),
            "cache_hit": False,
        }

        # 캐시 저장
        if cache_key:
            cache_put(cache_key, result)

        return result

    def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        s = get_settings()
        mdl = model or s.llm.embedding_model
        try:
            resp = self._client.embeddings.create(
                model=mdl,
                input=texts,
                dimensions=s.llm.embedding_dim,
            )
        except Exception as e:  # noqa: BLE001
            log.exception("llm.embed_error", extra={"model": mdl})
            raise LLMError(f"임베딩 호출 실패: {e}", meta={"model": mdl}) from e
        return [d.embedding for d in resp.data]


# ─────────────────────────────────────────────────────────────
# 팩토리
# ─────────────────────────────────────────────────────────────
@lru_cache
def get_llm_client() -> LLMClient:
    """싱글턴 LLM 클라이언트 — 설정에 따라 어댑터 선택.

    현재는 OpenAI 만 지원. 온프렘 도입 시 여기서 분기.
    """
    s = get_settings()
    api_key = s.llm.api_key.get_secret_value()
    if not api_key:
        raise LLMError("OPENAI_API_KEY 가 설정되지 않았습니다.")
    return OpenAIAdapter(api_key=api_key, default_model=s.llm.model)


# 편의 export
__all__ = ["LLMClient", "OpenAIAdapter", "get_llm_client", "make_cache_key"]
