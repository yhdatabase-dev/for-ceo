#
# 평문(.txt) 파서.
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.05.28      kimzion77   최초 생성
# 2026.10.02      이시영      구조 이행 (backend/cgr → backend/app)
#
# Author: kimzion77
# Since: 2026.05.28
#
"""평문(.txt) 파서."""
from __future__ import annotations
from pathlib import Path


def parse_plain(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")
