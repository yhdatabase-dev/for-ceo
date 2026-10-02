"""프롬프트 override 조회 — datadir.prompts_dir()/<key>.txt 가 있으면 그 내용, 없으면 코드 기본값."""
from __future__ import annotations

from app.core import datadir

# 인라인 프롬프트 텍스트 override 캐시 (key -> 내용)
_text_cache: dict[str, str] = {}

def _override_path(key: str):
    return datadir.prompts_dir() / f"{key}.txt"

def get_or_default(key: str, default: str) -> str:
    """인라인 프롬프트용 — override 파일 있으면 그 내용, 없으면 코드 기본값."""
    if key in _text_cache:
        return _text_cache[key]
    p = _override_path(key)
    if p.exists():
        try:
            txt = p.read_text(encoding="utf-8")
            _text_cache[key] = txt
            return txt
        except Exception:
            pass
    return default
