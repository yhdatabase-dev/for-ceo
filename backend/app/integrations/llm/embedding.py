"""OpenAI text-embedding-3-large 클라이언트.

- 모델: text-embedding-3-large (default 3072 dim, 1024 로 truncate)
- 단일 호출에 batch input 가능
- 결정성: 임베딩은 본질적으로 결정적
"""
from __future__ import annotations

import time
from typing import Any

import requests

from app.core.config import get_api_key, get_embed_dim, get_embed_model

DEFAULT_ENDPOINT = "https://api.openai.com/v1/embeddings"
_TIMEOUT = 60.0
_MAX_RETRIES = 3


class Embedder:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str | None = None,
        dim: int | None = None,
        endpoint: str = DEFAULT_ENDPOINT,
    ) -> None:
        self.api_key = get_api_key(api_key)
        if not self.api_key:
            raise ValueError("OpenAI API Key 없음")
        self.model = get_embed_model(model)
        self.dim = get_embed_dim(dim)
        self.endpoint = endpoint

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        clean = [t if t and t.strip() else " " for t in texts]
        payload: dict[str, Any] = {
            "model": self.model,
            "input": clean,
            "dimensions": self.dim,
        }
        last_err: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = requests.post(
                    self.endpoint,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=_TIMEOUT,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("data") or []
                    return [d["embedding"] for d in items]
                if resp.status_code in (429, 503):
                    time.sleep(2**attempt)
                    continue
                raise RuntimeError(
                    f"임베딩 HTTP {resp.status_code}: {(resp.text or '')[:300]}"
                )
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_err = e
                time.sleep(2**attempt)
        raise RuntimeError(f"임베딩 호출 실패 ({_MAX_RETRIES}회 재시도 후): {last_err}")


def cosine(a: list[float], b: list[float]) -> float:
    """코사인 유사도. dim 동일 가정."""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
