"""LLM 응답 캐시 — 입력 해시 기반 디스크 캐시.

목적:
  - 같은 입력 → 100% 같은 출력 (재현성 보장)
  - 동일 사업장 재검토 시 LLM 호출 0회
  - 디버그 시 "이번엔 왜 다른 결과?" 변동 차단

Key 구성: SHA256(system + user + schema + model) → 16자 hex
Cache: data/llm_cache/<key>.json
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "llm_cache"


def _disabled() -> bool:
    return os.environ.get("CGR_DISABLE_CACHE") == "1"


def make_key(system: str, user: str, schema: Any, model: str) -> str:
    h = hashlib.sha256()
    h.update(system.encode("utf-8"))
    h.update(b"\x00")
    h.update(user.encode("utf-8"))
    h.update(b"\x00")
    h.update(json.dumps(schema, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    h.update(b"\x00")
    h.update(model.encode("utf-8"))
    return h.hexdigest()[:24]


def get(key: str) -> dict[str, Any] | None:
    if _disabled():
        return None
    p = CACHE_DIR / f"{key}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def put(key: str, payload: dict[str, Any]) -> None:
    if _disabled():
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = CACHE_DIR / f"{key}.json"
    try:
        p.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def stats() -> dict[str, int]:
    if not CACHE_DIR.exists():
        return {"entries": 0, "size_kb": 0}
    files = list(CACHE_DIR.glob("*.json"))
    size = sum(f.stat().st_size for f in files)
    return {"entries": len(files), "size_kb": size // 1024}


def clear() -> int:
    if not CACHE_DIR.exists():
        return 0
    n = 0
    for f in CACHE_DIR.glob("*.json"):
        try:
            f.unlink()
            n += 1
        except Exception:
            pass
    return n
