"""공통 응답 스키마."""
from __future__ import annotations

from pydantic import BaseModel, Field


# ─── 공통 ────────────────────────────────────
class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    services: dict[str, str] = Field(default_factory=dict)
