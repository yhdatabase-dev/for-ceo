"""hwp(OLE compound) → plaintext.

이미 검증된 알고리즘:
  olefile + zlib(-15) → BodyText/Section* 압축해제 →
  HWPTAG_PARA_TEXT(67) 레코드만 추출, UTF-16LE + 컨트롤 16바이트 스킵.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

import olefile


_CTRLS_WITH_DATA = {1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23}


def _decode_paragraph_body(body: bytes) -> str:
    chars: list[str] = []
    i = 0
    while i + 1 < len(body):
        c = body[i] | (body[i + 1] << 8)
        if c < 32:
            if c in _CTRLS_WITH_DATA:
                i += 16
                continue
            elif c == 10:
                chars.append("\n")
                i += 2
            else:
                i += 2
        else:
            chars.append(chr(c))
            i += 2
    return "".join(chars)


def _walk_section(stream_bytes: bytes) -> str:
    text = zlib.decompress(stream_bytes, -15)
    out: list[str] = []
    pos = 0
    while pos + 4 <= len(text):
        hdr = struct.unpack("<I", text[pos : pos + 4])[0]
        pos += 4
        tag = hdr & 0x3FF
        size = (hdr >> 20) & 0xFFF
        if size == 0xFFF:
            if pos + 4 > len(text):
                break
            size = struct.unpack("<I", text[pos : pos + 4])[0]
            pos += 4
        body = text[pos : pos + size]
        pos += size
        if tag == 67:
            out.append(_decode_paragraph_body(body))
    return "\n".join(out)


def parse_hwp(path: str | Path) -> str:
    ole = olefile.OleFileIO(str(path))
    streams = ole.listdir()
    sections = sorted(
        (s for s in streams if s and s[0] == "BodyText"),
        key=lambda s: s[-1],
    )
    parts: list[str] = []
    for s in sections:
        raw = ole.openstream("/".join(s)).read()
        try:
            parts.append(_walk_section(raw))
        except Exception:
            continue
    return "\n".join(parts)
