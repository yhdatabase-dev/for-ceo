"""ec 도메인 내부 VO — 파이프라인 전용, 프론트 무영향.

원본에서는 dict 를 그대로 흘렸으나, v2 는 명시적 VO 로 계층 사이 데이터 shape 를 잡음.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EcSlotVO(BaseModel):
    """EC 슬롯 정의 (repository 가 로드해 서비스로 전달).

    원본 `cgr/ec/catalog.py:EcSlot` 을 그대로 이관.
    """

    slot_id: str
    field: str
    section: str
    required: bool = True
    missing_severity: str = "MEDIUM"
    violation_severity: str = "MEDIUM"
    keywords: list[str] = Field(default_factory=list)
    required_content: str = ""
    purpose: str = ""
    fix_example: str = ""
    laws: list[str] = Field(default_factory=list)
    topic_meta: list[str] = Field(default_factory=list)
    applicability: dict[str, Any] = Field(default_factory=dict)


class EcCatalogVO(BaseModel):
    """전체 EC 슬롯 카탈로그."""

    version: str = "1.0"
    doc: str = "employment_contract"
    slots: list[EcSlotVO] = Field(default_factory=list)


class EcFindingVO(BaseModel):
    """EC 검토 결과 1건 (서비스 내부 표현)."""

    slot_id: str
    field: str
    bucket: str          # 적절 | 보완필요 | 부적절
    severity: str
    present: bool
    extracted: str = ""
    reason: str = ""
    laws: list[str] = Field(default_factory=list)
    topic_meta: list[str] = Field(default_factory=list)
    fix_example: str = ""


class EcReportVO(BaseModel):
    """EC 검토 전체 결과 (서비스 내부)."""

    case_id: str
    filename: str
    overall_label: str
    summary: dict[str, int]
    findings: list[EcFindingVO] = Field(default_factory=list)
    skipped: int = 0
    elapsed_sec: float = 0.0
    llm_model: str = ""
