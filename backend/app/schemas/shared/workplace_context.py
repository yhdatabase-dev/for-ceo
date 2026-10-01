"""사업장 컨텍스트 — 검토 시 슬롯 SKIP 판단용 (WR·EC 공용).

원본 `cgr/models.py:WorkplaceContext` 를 그대로 이관.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class WorkplaceContextIn(BaseModel):
    """사업장 정보 입력.

    필드가 None 이면 "모름" → 판정에서 슬롯 SKIP 하지 않음 (안전 default).
    sh
    """

    shift_work_used: bool | None = Field(
        default=None, description="교대근로 도입 여부"
    )
    osha_applicable: bool | None = Field(
        default=True, description="산업안전보건법 적용 업종"
    )
    chemical_handling: bool | None = Field(
        default=None, description="화학물질 취급"
    )
    workenv_measurement: bool | None = Field(
        default=None, description="작업환경측정 대상"
    )
    business_size: str = Field(default="", description="5인이상 / 5인미만 / (빈 문자열)")
    worker_types: list[str] = Field(
        default_factory=list, description="정규직/기간제/단시간/일용직/연소자/외국인"
    )
