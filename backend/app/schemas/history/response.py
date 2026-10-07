#
# 검토 이력(history) 응답 스키마.
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.10.02      이시영      최초 생성 (구조 이행 — 기존 backend/cgr 코드를 분리·이동)
#
# Author: 이시영
# Since: 2026.10.02
#
"""검토 이력(history) 응답 스키마."""
from __future__ import annotations

from pydantic import BaseModel, Field


# ─── 이력 ────────────────────────────────────
class HistoryEntryOut(BaseModel):
    ts: str
    case_id: str
    filename: str
    overall_label: str = ""
    llm_model: str = ""
    by_bucket: dict[str, int] = Field(default_factory=dict)
    top_violations: list[str] = Field(default_factory=list)

class HistoryListOut(BaseModel):
    total: int
    entries: list[HistoryEntryOut]

class HistoryStatsOut(BaseModel):
    n_total: int
    n_recent_30d: int = 0
    avg_violation: float = 0.0
    avg_missing: float = 0.0
    top_slots: list[tuple[str, int]] = Field(default_factory=list)
