"""방문 추적(track) 요청 스키마."""
from __future__ import annotations

from pydantic import BaseModel


class TrackIn(BaseModel):
    visitor: str | None = None
    page: str | None = None
    service: str | None = None
