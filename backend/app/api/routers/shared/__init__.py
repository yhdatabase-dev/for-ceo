"""shared 라우터 — 2개 이상 도메인 공용 엔드포인트."""
from __future__ import annotations

from fastapi import APIRouter

from .history import router as history_router
from .track import router as track_router

router = APIRouter()
router.include_router(history_router)
router.include_router(track_router)

__all__ = ["router"]
