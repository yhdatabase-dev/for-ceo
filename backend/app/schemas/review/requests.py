"""review 도메인 요청 DTO.

원본 매핑 (cgr/api/routes/review.py + wr_classify.py)
- POST /review (Form + File)         → 스키마 없음 (라우터에서 Form params + UploadFile)
- POST /review/generate              → GenerateIn
- POST /review/generate-docx         → GenerateDocxIn
- POST /review/comparison-docx       → ComparisonDocxIn
- POST /review/classify/start        → WrClassifyIn
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CorrectionIn(BaseModel):
    """수정본 생성 시 사용자가 지정한 항목별 교정 지시."""

    name: str = Field(..., description="슬롯명·조 명·항목명")
    now: str = Field(..., description="현재(원문) 표현")
    fix: str = Field(..., description="변경 요청 표현")


class GenerateIn(BaseModel):
    """수정본 생성 요청 (`/review/generate/start`)."""

    original_text: str
    corrections: list[CorrectionIn] = Field(default_factory=list)


class GenerateDocxIn(BaseModel):
    """수정본 텍스트를 .docx 로 다운로드."""

    contract_text: str
    filename: str = "수정_취업규칙.docx"


class ComparisonDocxIn(BaseModel):
    """조별 대비표 .docx 다운로드."""

    rows: list[dict[str, Any]] = Field(..., description="[{조번호, 원문, 수정본, 근거}, ...]")
    effective_date: str = ""
    filename: str = "취업규칙_대비표.docx"


class WrClassifyIn(BaseModel):
    """취업규칙 근로환경 1차 분류 요청."""

    extracted_text: str
