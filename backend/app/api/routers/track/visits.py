"""익명 방문 핑."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.security import require_api_key
from app.core.upload import anon_visitor
from app.repositories.shared import analytics
from app.schemas.track.request import TrackIn

router = APIRouter(tags=["track"])


@router.post("/visits", summary="익명 방문 핑", dependencies=[Depends(require_api_key)])
async def post_track(body: TrackIn, request: Request) -> dict:
    visitor = (body.visitor or "").strip()[:64] or anon_visitor(request)
    analytics.log_visit(visitor, body.page, body.service)
    return {"ok": True}
