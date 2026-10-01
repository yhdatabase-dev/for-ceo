"""pdf 파서 — pypdf.

원본: `cgr/parsers/pdf.py:parse_pdf` 이관.
"""
from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


def parse(path: Path) -> str:
    """pdf → 텍스트."""
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text)
    return "\n".join(parts)
