"""docx → plaintext.

본문 paragraph + 테이블 cell 모두 줄바꿈 보존하며 추출.
"""
from __future__ import annotations

from pathlib import Path

from docx import Document


def parse_docx(path: str | Path) -> str:
    doc = Document(str(path))
    parts: list[str] = []

    for el in doc.element.body.iter():
        tag = el.tag.split("}")[-1]
        if tag == "p":
            text = "".join(t.text or "" for t in el.iter() if t.tag.endswith("}t"))
            parts.append(text.rstrip())
        elif tag == "tbl":
            # 테이블은 행 단위로 셀 텍스트 추출
            for tr in el.iter():
                if tr.tag.endswith("}tr"):
                    row_cells = []
                    for tc in tr.iter():
                        if tc.tag.endswith("}tc"):
                            cell_txt = "".join(
                                t.text or ""
                                for t in tc.iter()
                                if t.tag.endswith("}t")
                            )
                            row_cells.append(cell_txt.strip())
                    if row_cells:
                        parts.append(" | ".join(row_cells))
    return "\n".join(parts)
