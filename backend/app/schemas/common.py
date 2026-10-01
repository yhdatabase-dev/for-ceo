"""공통 스키마 — 업무 개념 없는 응답 형태."""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "2.0.0"
    services: dict[str, str] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """도메인 예외의 공통 응답 shape (핸들러가 자동 생성)."""

    error: str
    detail: str


class PagedResponse(BaseModel, Generic[T]):
    """페이지네이션 공용 응답."""

    total: int
    items: list[T]
    limit: int = 20
    offset: int = 0


class JobStartResponse(BaseModel):
    """비동기 잡 시작 응답 (start + poll 패턴)."""

    job_id: str


class JobResultResponse(BaseModel, Generic[T]):
    """비동기 잡 결과 조회 응답."""

    status: str = Field(..., description="pending | done | error")
    result: T | None = None
    error: str | None = None
    elapsed_sec: float = 0.0
