"""문서 파서 어댑터.

===============================================================================
원본 대비 주요 변경
===============================================================================
원본 (`cgr/parsers/`)
- 각 확장자별 파일 (docx.py, hwp.py, hwpx.py, pdf.py, plain.py, image.py).
- `dispatcher.py:parse_to_text(path)` 가 확장자 → 각 파서 위임.

v2
- 인터페이스 통일: `parse_document(path) -> str`.
- 각 파서를 어댑터로 다시 감쌈 (예외를 `ParseError` 로 변환).
- image 는 별도 (Vision OCR — LLM 클라이언트 사용, 대구센터 온프렘 이관 대상).
"""
from __future__ import annotations

from .dispatcher import parse_document

__all__ = ["parse_document"]
