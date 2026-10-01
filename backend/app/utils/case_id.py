"""case_id / file_hash 생성 유틸.

원본
- cgr/run.py:_case_id(file_path)  → 파일 해시 12자 + stem
- cgr/ec/run.py:_make_case_id(fp) → "ec-" + 해시 12자
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def file_sha256_short(file_path: Path, *, n: int = 12) -> str:
    """파일 SHA-256 앞 n 글자."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:n]


def make_wr_case_id(file_path: Path) -> str:
    """취업규칙 case_id — 원본 `cgr/run.py:_case_id`."""
    return f"{file_sha256_short(file_path)}-{file_path.stem}"


def make_ec_case_id(file_path: Path) -> str:
    """근로계약서 case_id — 원본 `cgr/ec/run.py:_make_case_id`."""
    return f"ec-{file_sha256_short(file_path)}"
