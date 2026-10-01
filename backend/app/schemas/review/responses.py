"""review 도메인 응답 DTO — WR 5-Bucket."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FindingOut(BaseModel):
    """슬롯 1건 판정 결과 (5-Bucket)."""

    slot_id: str
    article: int
    bucket: str  # 누락/위반/주의/검토필요/적정
    status: str  # OK/VIOLATION/MISSING/AMBIGUOUS/ERROR
    severity: str
    comparator: str
    reason: str
    user_reason: str | None = None
    quote: str = ""
    extracted_value: Any = None
    penalty_omission: list[str] = Field(default_factory=list)
    penalty_violation: list[str] = Field(default_factory=list)
    fix_example: str | None = None


class ArticleResultOut(BaseModel):
    """조(article) 단위 결과 묶음."""

    article: int
    title: str
    findings: list[FindingOut]


class ReviewSummaryOut(BaseModel):
    """검토 결과 요약."""

    case_id: str
    filename: str
    overall_label: str  # 적정/부적정/검토불가
    summary: dict[str, int]
    n_findings: int
    elapsed_sec: float
    llm_model: str = ""


class ReviewFullOut(ReviewSummaryOut):
    """검토 전체 결과 (상세 finding 포함)."""

    article_results: list[ArticleResultOut]


class GenerateOut(BaseModel):
    """수정본 생성 응답."""

    revised_text: str
    elapsed_sec: float
    model: str


class WrClassifyOut(BaseModel):
    """취업규칙 근로환경 판별 응답."""

    shift_work_used: bool | None = None
    osha_applicable: bool | None = None
    chemical_handling: bool | None = None
    workenv_measurement: bool | None = None
    doc_kind: str = ""
    reason: str = ""
