"""평문(.txt) 파서."""
from __future__ import annotations
from pathlib import Path


def parse_plain(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")
