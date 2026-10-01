"""파일 확장자 → 파서 dispatch.

원본 `cgr/parsers/dispatcher.py:14 parse_to_text(path)` 을 이관.
- 확장자별로 개별 파서 함수 호출.
- 예외를 `ParseError` 로 통일.

지원 확장자
- .docx     : python-docx
- .hwp      : (자체 구현 필요 — 원본 cgr/parsers/hwp.py 참고)
- .hwpx     : (동상 — 원본 cgr/parsers/hwpx.py 참고)
- .pdf      : pypdf
- .txt      : plain
- .png/.jpg/.jpeg/.gif/.bmp/.tiff/.webp/.heic/.heif : Vision OCR (LLM)
"""
from __future__ import annotations

from pathlib import Path

from app.core.exceptions import ParseError
from app.core.logging import get_logger

log = get_logger(__name__)


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp", ".heic", ".heif"}


def parse_document(path: Path) -> str:
    """확장자 → 파서 라우팅. 반환: 추출된 텍스트."""
    ext = path.suffix.lower()
    try:
        if ext == ".docx":
            from .docx_parser import parse
            return parse(path)
        if ext == ".pdf":
            from .pdf_parser import parse
            return parse(path)
        if ext == ".txt":
            return path.read_text(encoding="utf-8", errors="ignore")
        if ext == ".hwp":
            from .hwp_parser import parse
            return parse(path)
        if ext == ".hwpx":
            from .hwpx_parser import parse
            return parse(path)
        if ext in _IMAGE_EXTS:
            from .image_ocr import parse
            return parse(path)
        raise ParseError(
            f"지원하지 않는 파일 형식: {ext}",
            meta={"path": str(path), "ext": ext},
        )
    except ParseError:
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("parser.failed", extra={"path": str(path), "ext": ext})
        raise ParseError(f"파일 파싱 실패: {e}", meta={"path": str(path)}) from e
