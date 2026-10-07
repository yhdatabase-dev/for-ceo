#
# 스캔본(PNG·JPG 등) → 텍스트 OCR.
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
"""스캔본(PNG·JPG 등) → 텍스트 OCR.

영세사업장이 실제로 올리는 자료의 상당수는 종이를 스캔한 이미지다.
취업규칙·근로계약서·임금명세서 세 문서가 공통으로 이 파서를 거치고, 결과 텍스트는
기존 docx/hwp/pdf 와 동일한 후속 파이프라인(슬롯 추출 → 룰 판정)에 그대로 흘러간다.

설계 원칙
- **결정성**: 같은 이미지 → 같은 텍스트. 파일 바이트 해시 + 모델 + 프롬프트 키로 캐시.
- **저비용 결정 분리**: OCR 자체는 `temperature=0` 의 한 번 호출. 후속 슬롯 추출/판정과 분리.
- **포맷 보존**: 줄바꿈·들여쓰기·표 칸은 가능한 한 원문 그대로. 가공·요약·번역 금지.
- **여러 페이지**: 여기는 단일 이미지 파일 담당. 스캔 PDF 는 `pdf.py` 가 텍스트 레이어
  부재를 감지하면 페이지별 PNG 로 렌더해 `ocr_image_bytes()` 를 호출한다.

지원 확장자: .png .jpg .jpeg .gif .bmp .tif .tiff .webp
"""
from __future__ import annotations

import base64
import hashlib
import mimetypes
from pathlib import Path
from typing import Any

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from app.integrations.llm import cache as llm_cache
from app.core.config import get_api_key, get_llm_model


_OCR_PROMPT = """당신은 한국어 문서 OCR 보조자입니다.

[입력]
- 사용자가 업로드한 사업장 문서(취업규칙·근로계약서·임금명세서 중 하나)의 스캔 이미지

[출력 규칙 — 매우 중요]
1. 이미지 안의 모든 텍스트를 **원문 그대로** 옮긴다.
2. 한국어 맞춤법·띄어쓰기를 임의로 고치지 말 것. 본문에 있는 그대로.
3. 줄바꿈은 시각적 줄바꿈을 유지한다.
4. 조·항·호 번호(제1조, ①, 1., 가., 등), 표·칸 구분(│, ─ 또는 줄바꿈+탭)을 보존.
5. 추측·요약·해석 금지. 텍스트가 흐릿하거나 가려져서 읽을 수 없으면 그 부분만 `[판독불가]` 로 표시.
6. 답변에 설명·머리말·인사말 절대 넣지 말 것. **오직 옮긴 텍스트만**.
"""

_CALL_TIMEOUT = 90.0
_MAX_RETRIES = 3
_RETRY_BACKOFF = (2.0, 5.0, 10.0)
_MAX_BYTES = 20 * 1024 * 1024  # 20MB — Vision API 일반 상한선 기준

# Pillow 가 인식하는 확장자 중 본 파서가 받는 것.
SUPPORTED_IMAGE_EXTS: tuple[str, ...] = (
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp",
)


def _mime_for(ext: str) -> str:
    """Vision API 가 받는 image/* MIME 추정."""
    ext = ext.lower()
    # tif/tiff 는 OpenAI 가 직접 받지 않을 수 있어 png 로 다운컨버트 (Pillow 사용)
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
        raise ValueError(
            f"이미지 용량이 너무 큽니다 ({len(raw)//1024//1024}MB). "
            f"OCR 은 파일당 {_MAX_BYTES//1024//1024}MB 이하만 지원."
        )

    ext = path.suffix.lower()
    if ext in (".tif", ".tiff", ".bmp"):
        # Pillow 로 PNG 변환 — Vision API 호환성·결정성 ↑
        try:
            from io import BytesIO
            from PIL import Image  # type: ignore

            img = Image.open(BytesIO(raw))
            buf = BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            return buf.getvalue(), "image/png"
        except Exception as e:
            raise ValueError(
                f"{ext} 이미지 변환 실패: {e}. PNG 또는 JPG 로 업로드해 주세요."
            )

    return raw, _mime_for(ext)


def _image_to_data_url(img_bytes: bytes, mime: str) -> str:
    b64 = base64.b64encode(img_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"


def parse_image(path: str | Path) -> str:
    """이미지 한 장 → OCR 텍스트.

    `parsers/dispatcher.parse_to_text` 에서 image 확장자일 때 호출.
    실패 시 ValueError/RuntimeError 를 던지며, 호출자는 상위 try 에서 사용자 친화 메시지로 감싼다.
    """
    p = Path(path)
    img_bytes, mime = _read_image_bytes(p)
    return ocr_image_bytes(img_bytes, mime)


def ocr_image_bytes(img_bytes: bytes, mime: str = "image/png") -> str:
    """이미지 바이트 → OCR 텍스트. 캐시 키는 바이트 해시라 파일 유무와 무관하게 결정적.

    스캔 PDF 폴백(`pdf.py`)이 페이지별 렌더 PNG 로 직접 호출한다.
    """
    if len(img_bytes) > _MAX_BYTES:
        raise ValueError(
            f"이미지 용량이 너무 큽니다 ({len(img_bytes)//1024//1024}MB). "
            f"OCR 은 페이지당 {_MAX_BYTES//1024//1024}MB 이하만 지원."
        )

    model_name = get_llm_model()

    # 캐시 키 — 이미지 바이트 해시 + 프롬프트 + 모델 (페이지별 독립 캐시)
    img_hash = hashlib.sha256(img_bytes).hexdigest()
    cache_key = llm_cache.make_key(
        system=_OCR_PROMPT,
        user=f"image_sha256:{img_hash}",
        schema={"kind": "ocr"},
        model=model_name,
    )
    cached = llm_cache.get(cache_key)
    if cached is not None and isinstance(cached.get("text"), str):
        return cached["text"]

    data_url = _image_to_data_url(img_bytes, mime)
    client = OpenAI(api_key=get_api_key(), timeout=_CALL_TIMEOUT)

    last_err: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": _OCR_PROMPT},
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
                temperature=0,
                top_p=1,
            )
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                raise RuntimeError("OCR 결과가 비어 있습니다.")
            llm_cache.put(cache_key, {"text": text, "image_sha256": img_hash})
            return text
        except (APITimeoutError, APIConnectionError, RateLimitError) as e:
            last_err = e
            if attempt < _MAX_RETRIES - 1:
                import time
                time.sleep(_RETRY_BACKOFF[attempt])
                continue
            raise
        except Exception as e:
            last_err = e
            raise

    # unreachable — retries 다 실패하면 위 raise 가 먼저 떨어짐
    raise RuntimeError(f"OCR 실패: {last_err}")
