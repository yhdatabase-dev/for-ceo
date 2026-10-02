"""스캔 PDF(텍스트 레이어 없음) → Vision OCR 폴백 검증.

실제 사고 사례: 취업규칙(제이씨리소시즈)-신고.pdf — 25페이지 전체가 스캔 이미지,
pdfplumber 텍스트 0자 → 검토가 빈 텍스트로 실패하던 버그의 회귀 방지.

OCR 자체(LLM Vision)는 mock — 여기서 검증하는 것은
  1) 텍스트 레이어 부재 감지 → 폴백 진입
  2) 페이지 순서 보존 (병렬 OCR 이어도)
  3) 페이지 수 상한 가드
  4) 디지털 PDF 는 폴백을 타지 않음
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.integrations.parsers import pdf as pdf_parser


def _make_scanned_pdf(path: Path, n_pages: int) -> None:
    """PIL 로 이미지-전용(텍스트 레이어 없는) 멀티페이지 PDF 생성."""
    pages = []
    for i in range(n_pages):
        img = Image.new("RGB", (120, 160), "white")
        d = ImageDraw.Draw(img)
        d.rectangle([10, 10 + i * 5, 60, 40 + i * 5], outline="black")
        pages.append(img)
    pages[0].save(path, format="PDF", save_all=True, append_images=pages[1:])


def test_scanned_pdf_triggers_ocr_fallback_in_page_order(tmp_path, monkeypatch):
    p = tmp_path / "scan.pdf"
    _make_scanned_pdf(p, 3)

    calls: list[bytes] = []

    def fake_ocr(img_bytes: bytes, mime: str = "image/png") -> str:
        calls.append(img_bytes)
        return f"PAGE_{len(calls)}"

    monkeypatch.setattr("app.integrations.parsers.image.ocr_image_bytes", fake_ocr)

    out = pdf_parser.parse_pdf(p)

    assert len(calls) == 3, "페이지 수만큼 OCR 이 호출되어야 함"
    assert all(b.startswith(b"\x89PNG") for b in calls), "렌더 결과는 PNG 바이트"
    # ThreadPoolExecutor.map 은 순서 보존 — 결과는 페이지 순서대로 조인
    assert out == "PAGE_1\n\nPAGE_2\n\nPAGE_3"


def test_scanned_pdf_over_page_cap_rejected(tmp_path, monkeypatch):
    p = tmp_path / "big.pdf"
    _make_scanned_pdf(p, 3)
    monkeypatch.setattr(pdf_parser, "_MAX_OCR_PAGES", 2)
    monkeypatch.setattr(
        "app.integrations.parsers.image.ocr_image_bytes",
        lambda *a, **k: pytest.fail("상한 초과 시 OCR 이 호출되면 안 됨"),
    )
    with pytest.raises(ValueError, match="페이지 이하만"):
        pdf_parser.parse_pdf(p)


def test_digital_pdf_does_not_hit_ocr(tmp_path, monkeypatch):
    """텍스트 레이어가 있으면 기존 경로 그대로 — OCR 호출 0회."""
    import pdfplumber  # noqa: F401 — 환경 확인용

    # fpdf 류 의존성 없이 텍스트 PDF 를 만들기 어려우므로,
    # extract_text 가 충분한 텍스트를 반환하는 상황을 pdfplumber mock 으로 구성.
    class _FakePage:
        page_number = 1

        def extract_text(self):
            return "제1조(목적) 이 규칙은 근로조건을 정함을 목적으로 한다." * 3

    class _FakePdf:
        pages = [_FakePage()]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("pdfplumber.open", lambda _p: _FakePdf())
    monkeypatch.setattr(
        "app.integrations.parsers.image.ocr_image_bytes",
        lambda *a, **k: pytest.fail("디지털 PDF 에서 OCR 이 호출되면 안 됨"),
    )
    out = pdf_parser.parse_pdf(tmp_path / "any.pdf")
    assert "제1조" in out
