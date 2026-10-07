#
# 프롬프트 override 조회 — datadir.prompts_dir()/<key>.txt 가 있으면 그 내용, 없으면 코드 기본값.
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.10.02      이시영      최초 생성 (구조 이행 — 기존 backend/cgr 코드를 분리·이동)
#
# Author: 이시영
# Since: 2026.10.02
#
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
