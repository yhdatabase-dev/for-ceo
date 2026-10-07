#
# 업로드 입력 검증 테스트 — 크기·확장자·매직바이트(내용 일치).
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.07.08      kimzion77   최초 생성
# 2026.10.02      이시영      구조 이행 (backend/cgr → backend/app)
#
# Author: kimzion77
# Since: 2026.07.08
#
"""업로드 입력 검증 테스트 — 크기·확장자·매직바이트(내용 일치)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.upload import MAX_UPLOAD_BYTES, validate_upload

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"x" * 64
ZIP = b"PK\x03\x04" + b"\x00" * 64      # docx·hwpx
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64  # hwp·doc


def err(filename: str, content: bytes) -> HTTPException:
    with pytest.raises(HTTPException) as ei:
        validate_upload(filename, content)
    return ei.value


# ─── 기본 거부 ───
def test_empty_rejected():
    assert err("a.png", b"").status_code == 400

def test_oversize_rejected():
    assert err("a.txt", b"x" * (MAX_UPLOAD_BYTES + 1)).status_code == 413

def test_disallowed_ext_rejected():
    assert err("malware.exe", b"MZ....").status_code == 400
    assert err("script.js", b"alert(1)").status_code == 400


# ─── 정상 통과 (기능 보존 — 지원 형식 전부) ───
@pytest.mark.parametrize("name,content", [
    ("scan.png", PNG),
    ("photo.jpg", JPG),
    ("photo.jpeg", JPG),
    ("doc.pdf", PDF),
    ("contract.docx", ZIP),
    ("rules.hwpx", ZIP),
    ("rules.hwp", OLE),
    ("old.doc", OLE),
    ("memo.txt", "아무 텍스트나".encode("utf-8")),
    ("확장자없음", b"plain content"),  # 확장자 없으면 형식 검사 생략 (기존 동작 유지)
])
def test_supported_formats_pass(name, content):
    validate_upload(name, content)  # 예외 없으면 통과


# ─── 위장 파일 차단 (매직바이트 불일치) ───
def test_exe_disguised_as_png_rejected():
    assert err("cute.png", b"MZ\x90\x00" + b"\x00" * 64).status_code == 400

def test_html_disguised_as_pdf_rejected():
    assert err("doc.pdf", b"<html><script>alert(1)</script>").status_code == 400

def test_jpg_bytes_with_png_ext_rejected():
    assert err("photo.png", JPG).status_code == 400

def test_heic_requires_ftyp():
    ok = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32
    validate_upload("live.heic", ok)
    assert err("live.heic", b"notaheic" + b"\x00" * 32).status_code == 400
