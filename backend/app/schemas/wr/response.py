"""취업규칙(wr) 응답 스키마."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FindingOut(BaseModel):
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
    article: int
    title: str
    findings: list[FindingOut]

class ReviewSummaryOut(BaseModel):
    """검토 결과 요약."""

    case_id: str
    filename: str
    overall_label: str  # 적정/부적정/검토불가
    summary: dict[str, int]  # 5-bucket 카운트
    n_findings: int
    elapsed_sec: float
    llm_model: str = ""

class ReviewFullOut(ReviewSummaryOut):
    """검토 전체 결과 (상세 finding 포함)."""

    article_results: list[ArticleResultOut]

# ─────────────────────────────────────────────
# 비동기 검토 — 게이트웨이 타임아웃 우회 (start + poll)
#
#   POST /api/cgr/wr/reviews         → {job_id} 즉시 반환, 백그라운드 검토
#   GET  /api/cgr/wr/reviews/{job_id}→ {status, result, ...} 폴링
#
# 취업규칙 검토는 Excel 로드 + 전 조항 LLM 검토를 한 번에 하므로 가장 느림.
# 동기 POST /review 는 하위호환·로컬용으로 유지하고, 프론트는 start+poll 사용.
# ─────────────────────────────────────────────
class ReviewJobStartOut(BaseModel):
    job_id: str
    # 프로그램명세서 AI-P03-001: 검토 건 식별자(서버 생성 UUID)를 접수 응답에도 돌려준다 (기존: job_id 만 반환)
    case_id: str = ""

class ReviewJobResultOut(BaseModel):
    status: str = Field(..., description="pending | done | error")
    result: dict | None = None
    error: str | None = None
    elapsed_sec: float = 0.0

class GenerateResultOut(BaseModel):
    status: str = Field(..., description="pending | done | error")
    revised_text: str | None = None
    error: str | None = None
    elapsed_sec: float = 0.0
    model: str = ""

class JobStartOut(BaseModel):
    job_id: str = Field(..., description="폴링에 사용할 작업 ID")

class WrClassifyResultOut(BaseModel):
    status: str = Field(..., description="pending | done | error")
    shift_work_used: bool | None = None
    osha_applicable: bool | None = None
    chemical_handling: bool | None = None
    workenv_measurement: bool | None = None
    doc_kind: str | None = None
    reason: str | None = None
    error: str | None = None
    elapsed_sec: float = 0.0
