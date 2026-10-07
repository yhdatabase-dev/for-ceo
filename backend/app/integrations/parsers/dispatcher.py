#
# 확장자 기반 파서 라우팅.
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
"""확장자 기반 파서 라우팅."""
from __future__ import annotations

from pathlib import Path

from app.integrations.parsers.docx import parse_docx
from app.integrations.parsers.hwp import parse_hwp
from app.integrations.parsers.hwpx import parse_hwpx
from app.integrations.parsers.image import SUPPORTED_IMAGE_EXTS, parse_image
from app.integrations.parsers.pdf import parse_pdf
from app.integrations.parsers.plain import parse_plain


def parse_to_text(path: str | Path) -> str:
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".docx":
        return parse_docx(p)
    if ext == ".hwp":
        return parse_hwp(p)
    if ext == ".hwpx":
        return parse_hwpx(p)
    if ext == ".pdf":
        return parse_pdf(p)
    if ext in (".txt", ".md", ""):
        return parse_plain(p)
    if ext in SUPPORTED_IMAGE_EXTS:
        # 스캔본(PNG·JPG 등) — Vision OCR 로 텍스트화한 뒤 동일 파이프라인.
        return parse_image(p)
    raise ValueError(f"지원하지 않는 형식: {ext} ({p})")
