"""ec 도메인 응답 DTO — 프론트 계약."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ExtractOut(BaseModel):
    """OCR/파일 추출 응답."""

    extracted_text: str
    filename: str
    elapsed_sec: float
    model: str


class ClassifyOut(BaseModel):
    """근로자 유형 AI 판별 결과."""

    worker_types: list[str]
    doc_kind: str = ""
    reason: str = ""
    elapsed_sec: float = 0.0
    model: str = ""


class StructureOut(BaseModel):
    """8섹션 구조화 응답."""

    structured_data: dict[str, Any] = Field(
        ...,
        description="기본정보/계약사항/근로시간/휴일휴가/임금/퇴직급여/사회보험/계약체결 + 기타사항",
    )
    elapsed_sec: float
    model: str


class AnalyzeOut(BaseModel):
    """33-매핑 위반 분석 응답."""

    analysis_result: dict[str, Any] = Field(
        ...,
        description="{riskLevel, overallStatus, overallOpinion, results[], finalRecommendations}",
    )
    elapsed_sec: float
    model: str


class ValidateFieldOut(BaseModel):
    """단일 칸 재검토 결과."""

    적절성: str = Field(..., description="적절 | 보완필요 | 부적정")
    이유: str = ""
    작성예시: str = ""


class GenerateOut(BaseModel):
    """표준 계약서 텍스트 생성 응답."""

    contract_text: str
    elapsed_sec: float
    model: str


class ChatOut(BaseModel):
    answer: str
    elapsed_sec: float
    model: str


# ─── 3-Bucket 검토 응답 (legacy `/review` 진입점용) ─────────
class EcFindingOut(BaseModel):
    """근로계약서 검토 결과 1건 — 3-Bucket."""

    slot_id: str
    field: str
    bucket: str          # 적절 | 보완필요 | 부적절
    severity: str        # CRITICAL/HIGH/MEDIUM/LOW
    present: bool
    extracted: str = ""
    reason: str = ""
    required_content: str = ""
    purpose: str = ""
    laws: list[str] = Field(default_factory=list)
    topic_meta: list[str] = Field(default_factory=list)
    fix_example: str = ""


class EcReviewOut(BaseModel):
    """`/review` 에서 EC 파일로 들어왔을 때 반환 형태."""

    case_id: str
    filename: str
    doc: str = "employment_contract"
    overall_label: str
    summary: dict[str, int]
    n_findings: int
    skipped: int = 0
    elapsed_sec: float
    findings: list[EcFindingOut] = Field(default_factory=list)
