"""LLM 응답 캐시.

===============================================================================
원본 대비 주요 변경
===============================================================================
원본 (`cgr/llm_cache.py`, 82줄)
- `CACHE_DIR = data/llm_cache/` 파일 캐시 (해시 파일명).
- get/put/stats/clear.

v2
- 인터페이스 동일 (`make_cache_key`, `cache_get`, `cache_put`, `cache_stats`, `cache_clear`).
- 기본 백엔드는 여전히 파일 (`{CGR_DATA_DIR}/llm_cache/*.json`) — 캐시는 로컬로 충분.
- `CGR_DISABLE_CACHE=true` 시 no-op (테스트 격리용).
- 향후 Redis/PG 로 갈아끼울 여지 위해 함수형 인터페이스 유지.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


def _cache_dir() -> Path:
    """캐시 디렉토리 — 최초 접근 시 생성."""
    p = get_settings().data.data_dir / "llm_cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def make_cache_key(*parts: Any) -> str:
    """캐시 키 생성 — 인자를 정규화하여 SHA-256.

    사용 예:
        key = make_cache_key(model, "wr_extractor", version, document_text, slot_ids)
    """
    raw = json.dumps(
        [p if isinstance(p, (str, int, float, bool)) else _canon(p) for p in parts],
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _canon(obj: Any) -> Any:
    """dict/list 를 정규화된 형태로 (키 정렬)."""
    if isinstance(obj, dict):
        return {k: _canon(v) for k, v in sorted(obj.items())}
    if isinstance(obj, (list, tuple)):
        return [_canon(v) for v in obj]
    return obj


def cache_get(key: str) -> dict[str, Any] | None:
    """캐시 조회 — miss/disable 시 None."""
    if get_settings().behavior.disable_cache:
        return None
    fp = _cache_dir() / f"{key}.json"
    if not fp.exists():
        return None
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        log.warning("llm_cache.read_failed", extra={"key": key})
        return None


def cache_put(key: str, payload: dict[str, Any]) -> None:
    """캐시 저장 — disable 시 no-op."""
    if get_settings().behavior.disable_cache:
        return
    fp = _cache_dir() / f"{key}.json"
    tmp = fp.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(fp)
    except Exception:  # noqa: BLE001
        log.warning("llm_cache.write_failed", extra={"key": key})


def cache_stats() -> dict[str, int]:
    """캐시 통계."""
    d = _cache_dir()
    files = list(d.glob("*.json"))
    size_kb = sum(f.stat().st_size for f in files) // 1024
    return {"entries": len(files), "size_kb": size_kb}


def cache_clear() -> int:
    """캐시 전체 삭제. 반환: 삭제된 파일 수."""
    d = _cache_dir()
    n = 0
    for f in d.glob("*.json"):
        try:
            f.unlink()
            n += 1
        except OSError:
            pass
    log.info("llm_cache.cleared", extra={"deleted": n})
    return n
