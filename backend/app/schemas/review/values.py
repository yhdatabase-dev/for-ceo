"""review 도메인 내부 VO — 판정 파이프라인 전용.

원본 `cgr/models.py:{SlotDef, Extraction, Finding, Report, MasterValue}` 를
도메인 격리 원칙에 따라 여기로 이관 (다른 도메인이 참조 안 함).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MasterValueVO(BaseModel):
    """마스터 기준값 — object_match 지원."""

    op: str = "presence"       # presence/numeric_gte/numeric_lte/eq/object_match
    value: Any = None
    keys: dict[str, Any] = Field(default_factory=dict)


class SlotDefVO(BaseModel):
    """WR 슬롯 정의 (repository 가 로드해 서비스로 전달).

    원본 `cgr/models.py:SlotDef` 이관.
    """

    slot_id: str
    article: int
    parent_clause: str | None = None
    required: bool = True
    comparator: str = "presence"
    violation_severity: str | None = None
    missing_severity: str | None = None
    extract_target: str | None = None
    search_phrases: list[str] = Field(default_factory=list)
    master_value: MasterValueVO | None = None
    threshold_ok: float | None = None
    threshold_violation: float | None = None
    fix_example: str | None = None
    penalty: list[str] = Field(default_factory=list)
    topic_meta: list[str] = Field(default_factory=list)
    # comparator='interpret' 슬롯 전용 — LLM 에게 적정/부적정 판단 기준 제공
    interpret_criteria: str | None = None
    # extractor 전용 — LLM 함수 스키마의 extracted_value 타입 힌트 (원본 cgr SlotDef.extract_schema)
    extract_schema: dict[str, Any] = Field(default_factory=dict)
    # extractor 프롬프트에 보여줄 적정 표현 예시 (원본 cgr SlotDef.example_compliant)
    example_compliant: str | None = None


class ExtractionVO(BaseModel):
    """LLM 슬롯 추출 결과 1건."""

    slot_id: str
    found: bool = False
    quote: str = ""
    extracted_value: Any = None
    error: str | None = None
    skipped: bool = False
    skip_reason: str | None = None
    # interpret / embed_match comparator 전용 (원본 cgr/models.py:Extraction 이관)
    confidence: float | None = None
    verdict: str | None = None            # "OK" | "VIOLATION" | "AMBIGUOUS" | None
    verdict_reason: str | None = None


class FindingVO(BaseModel):
    """룰 평가 후 결과 1건."""

    slot_id: str
    article: int
    status: str            # OK/VIOLATION/MISSING/AMBIGUOUS/ERROR
    severity: str = "MEDIUM"
    comparator: str = "presence"
    reason: str = ""
    user_reason: str | None = None
    quote: str = ""
    extracted_value: Any = None
    penalty_omission: list[str] = Field(default_factory=list)
    penalty_violation: list[str] = Field(default_factory=list)
    fix_example: str | None = None


class OptionalDisplayVO(BaseModel):
    """선택 조 참고 표시 (검사 안 함) — 원본 `cgr/models.py:OptionalDisplay` 이관."""

    article: int
    title: str
    scope: str = "선택"
    master_body: str = ""
    master_guide: str = ""
    master_note: str = ""
    user_quote: str | None = None
    user_present: bool = False


class ReportVO(BaseModel):
    """검토 전체 결과 (서비스 내부)."""

    case_id: str
    filename: str
    overall_label: str = ""
    summary: dict[str, int] = Field(default_factory=dict)
    findings: list[FindingVO] = Field(default_factory=list)
    optional_displays: list[OptionalDisplayVO] = Field(default_factory=list)
    # article 번호 → 표시용 조 제목 (reporter 렌더링용 lookup 캐시)
    article_titles: dict[int, str] = Field(default_factory=dict)
    source_file: str = ""
    generated_at: str = ""
    elapsed_sec: float = 0.0
    llm_model: str = ""
