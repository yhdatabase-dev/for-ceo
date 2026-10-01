"""hwpx(zip + xml) → plaintext.

===============================================================================
원본 이관
===============================================================================
원본: `cgr/parsers/hwpx.py` → v2 로 그대로 이관.

hwpx 는 OOXML 유사 zip 패키지. Contents/section*.xml 의 <hp:p>·<hp:t> 텍스트 추출.

보안
- 사용자 업로드(hwpx)는 신뢰할 수 없는 XML → XXE/엔티티폭탄 방지로 `defusedxml` 사용.
- KISA 시큐어코딩 'XML 외부개체 참조', OWASP A05/A03.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree.ElementTree import ParseError as XmlParseError

import defusedxml.ElementTree as ET
from defusedxml.common import DefusedXmlException

from app.core.exceptions import ParseError


def parse(path: Path) -> str:
    """hwpx → 텍스트. 실패 시 ParseError."""
    parts: list[str] = []
    try:
        with zipfile.ZipFile(str(path)) as z:
            sections = sorted(
                n for n in z.namelist() if re.match(r"Contents/section\d+\.xml$", n)
            )
            for name in sections:
                with z.open(name) as f:
                    try:
                        tree = ET.parse(f)
                    except (XmlParseError, DefusedXmlException):
                        # 손상됐거나 DTD/외부엔티티 포함 악성 XML — 안전하게 건너뜀
                        continue
                for el in tree.getroot().iter():
                    tag = el.tag.split("}")[-1]
                    if tag in ("p", "para"):
                        text = "".join(
                            (t.text or "")
                            for t in el.iter()
                            if t.tag.split("}")[-1] in ("t", "char")
                        )
                        parts.append(text.rstrip())
    except zipfile.BadZipFile as e:
        raise ParseError(
            f"hwpx 파일이 유효한 zip 이 아닙니다: {e}",
            meta={"path": str(path)},
        ) from e
    return "\n".join(parts)
