#
# pdf → plaintext.
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
"""pdf → plaintext.

1차: pdfplumber 텍스트 레이어 추출 (디지털 PDF).
2차: 추출 텍스트가 사실상 없으면(스캔본) 페이지별 PNG 렌더 → Vision OCR 폴백.
     - 렌더: pdfplumber `page.to_image()` (pypdfium2 백엔드) — PyMuPDF(AGPL) 회피.
     - OCR: `image.ocr_image_bytes` 재사용 — 페이지 이미지 바이트 해시로 캐시되므로
       같은 PDF → 같은 텍스트 (결정성 유지). 병렬 호출해도 순서는 페이지 순서 보존.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

# 전체 추출 텍스트가 이 길이 미만이면 텍스트 레이어가 없는 스캔본으로 간주.
# (디지털 PDF 는 표지 한 장만 있어도 수백 자가 나온다.)
_SCANNED_TEXT_MIN = 30
_MAX_OCR_PAGES = 60          # 폭주 방지 — 취업규칙 실물 기준 여유치
_OCR_RENDER_DPI = 150        # A4 기준 ~1240×1754px, 페이지당 PNG 수백 KB
_OCR_WORKERS = 4


def parse_pdf(path: str | Path) -> str:
    try:
        import pdfplumber
    except ImportError as e:
        raise RuntimeError(
            "pdfplumber 미설치. 'pip install pdfplumber' 로 설치하세요."
        ) from e
    parts: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            parts.append(text)
    joined = "\n".join(parts)
    if len(joined.strip()) >= _SCANNED_TEXT_MIN:
        return joined
    return _ocr_scanned_pdf(path)


def _ocr_scanned_pdf(path: str | Path) -> str:
    """텍스트 레이어 없는 PDF → 페이지별 렌더 + Vision OCR."""
    import pdfplumber

    from app.integrations.parsers.image import ocr_image_bytes

    page_pngs: list[bytes] = []
    with pdfplumber.open(str(path)) as pdf:
        n_pages = len(pdf.pages)
        if n_pages == 0:
            raise ValueError("PDF 에 페이지가 없습니다.")
        if n_pages > _MAX_OCR_PAGES:
            raise ValueError(
                f"스캔 PDF OCR 은 {_MAX_OCR_PAGES}페이지 이하만 지원합니다 "
                f"(업로드 파일: {n_pages}페이지). 문서를 나눠 올려주세요."
            )
        # 렌더는 순차 (pdfplumber 페이지 객체는 스레드 안전 보장이 없음)
        for page in pdf.pages:
            try:
                pil = page.to_image(resolution=_OCR_RENDER_DPI).original
            except Exception as e:
                raise RuntimeError(
                    f"스캔 PDF 렌더 실패 (p.{page.page_number}): {e}. "
                    "pypdfium2 설치 여부를 확인하세요."
                ) from e
            buf = BytesIO()
            pil.convert("RGB").save(buf, format="PNG")
            page_pngs.append(buf.getvalue())

    # OCR 은 페이지별 독립 → 병렬. ex.map 이 입력 순서를 보존한다.
    with ThreadPoolExecutor(max_workers=_OCR_WORKERS) as ex:
        texts = list(ex.map(ocr_image_bytes, page_pngs))
    return "\n\n".join(texts)
