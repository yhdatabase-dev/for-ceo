"""스캔본(PNG·JPG 등) → 텍스트 OCR (Vision LLM).

===============================================================================
원본 이관
===============================================================================
원본: `cgr/parsers/image.py` (183줄) → v2 로 이관.

변경점
- `OpenAI(...)` 직접 인스턴스화 → `get_llm_client().chat(...)`
  · 어댑터가 캐시/재시도/오류 표준화 흡수
  · 멀티모달 content (list[dict]) 는 어댑터의 PII 마스킹이 str 만 대상이라 그대로 통과
- `cgr.llm_cache` → `app.integrations.llm.cache.make_cache_key`
- `cgr.config.get_llm_model/get_api_key` → 어댑터가 default_model 관리
- 프롬프트는 하드코딩 대신 `resolve_prompt(conn, "ocr_image")` 로 조회
  · dispatcher 호출부에서 conn 없어 호출자가 conn 을 주입해야 함
  · 미주입 시 default 프롬프트로 fallback (dispatcher 하위 호환)
- 파일 읽기·TIFF/BMP → PNG 변환·MIME 판정·크기 상한은 원본과 100% 동일

설계 원칙 (원본 그대로)
- **결정성**: 같은 이미지 → 같은 텍스트. 파일 바이트 해시 + 프롬프트 + 모델 캐시 키.
- **저비용 결정 분리**: OCR 자체는 temperature=0 한 번 호출.
- **포맷 보존**: 줄바꿈·들여쓰기·표 칸을 가능한 한 원문 그대로.
"""
from __future__ import annotations

import base64
import hashlib
import mimetypes
from pathlib import Path

import psycopg

from app.core.exceptions import LLMError, ParseError
from app.integrations.llm.cache import make_cache_key
from app.integrations.llm.client import get_llm_client
from app.integrations.llm.prompts import resolve_prompt
from app.integrations.llm.prompts.review import _OCR_PROMPT as _DEFAULT_OCR_PROMPT

_MAX_BYTES = 20 * 1024 * 1024

SUPPORTED_IMAGE_EXTS: tuple[str, ...] = (
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp",
)


def _mime_for(ext: str) -> str:
    ext = ext.lower()
    mapping = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
    }
    return mapping.get(ext, mimetypes.guess_type("x" + ext)[0] or "image/png")


def _read_image_bytes(path: Path) -> tuple[bytes, str]:
    """파일 → (bytes, mime). TIFF·BMP 는 호환성을 위해 PNG 로 변환."""
    raw = path.read_bytes()
    if len(raw) > _MAX_BYTES:
        raise ParseError(
            f"이미지 용량이 너무 큽니다 ({len(raw)//1024//1024}MB). "
            f"OCR 은 파일당 {_MAX_BYTES//1024//1024}MB 이하만 지원.",
            meta={"path": str(path)},
        )

    ext = path.suffix.lower()
    if ext in (".tif", ".tiff", ".bmp"):
        try:
            from io import BytesIO
            from PIL import Image  # type: ignore

            img = Image.open(BytesIO(raw))
            buf = BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            return buf.getvalue(), "image/png"
        except Exception as e:  # noqa: BLE001
            raise ParseError(
                f"{ext} 이미지 변환 실패: {e}. PNG 또는 JPG 로 업로드해 주세요.",
                meta={"path": str(path)},
            ) from e

    return raw, _mime_for(ext)


def _image_to_data_url(img_bytes: bytes, mime: str) -> str:
    b64 = base64.b64encode(img_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"


def parse(path: Path, *, conn: psycopg.Connection | None = None) -> str:
    """이미지 한 장 → OCR 텍스트 (dispatcher 진입점).

    conn 은 프롬프트 override 조회용. dispatcher 가 넘겨주지 않는 경우
    내장 default 프롬프트 사용.
    """
    img_bytes, mime = _read_image_bytes(path)
    return ocr_image_bytes(img_bytes, mime, conn=conn)


def ocr_image_bytes(
    img_bytes: bytes,
    mime: str = "image/png",
    *,
    conn: psycopg.Connection | None = None,
) -> str:
    """이미지 바이트 → OCR 텍스트.

    캐시 키는 바이트 해시 기반이라 파일 유무와 무관하게 결정적.
    스캔 PDF 폴백(pdf_parser)이 페이지별 렌더 PNG 로 직접 호출한다.
    """
    if len(img_bytes) > _MAX_BYTES:
        raise ParseError(
            f"이미지 용량이 너무 큽니다 ({len(img_bytes)//1024//1024}MB). "
            f"OCR 은 페이지당 {_MAX_BYTES//1024//1024}MB 이하만 지원.",
        )

    # 프롬프트 — DB override 있으면 사용, 없으면 default
    if conn is not None:
        try:
            system = resolve_prompt(conn, "ocr_image")
        except Exception:  # noqa: BLE001
            system = _DEFAULT_OCR_PROMPT
    else:
        system = _DEFAULT_OCR_PROMPT

    img_hash = hashlib.sha256(img_bytes).hexdigest()
    # 캐시 키 — 이미지 해시 + 프롬프트 + kind (모델은 어댑터 default 이므로 별도 반영 X)
    cache_key = make_cache_key("ocr_image", system, img_hash)

    data_url = _image_to_data_url(img_bytes, mime)
    client = get_llm_client()
    try:
        result = client.chat(
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "이 이미지의 모든 텍스트를 원문 그대로 옮겨주세요.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                },
            ],
            temperature=0.0,
            cache_key=cache_key,
        )
    except LLMError:
        raise
    except Exception as e:  # noqa: BLE001
        raise LLMError(f"OCR 호출 실패: {e}") from e

    text = (result.get("content") or "").strip()
    if not text:
        raise LLMError("OCR 결과가 비어 있습니다.")
    return text
