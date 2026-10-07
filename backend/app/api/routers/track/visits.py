"""익명 방문 핑."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.security import require_api_key
from app.core.upload import anon_visitor
from app.repositories.shared import analytics
from app.schemas.track.request import TrackIn

# 개발표준정의서 API 엔드포인트: /api/cgr/<도메인>/<리소스> — 복수형 케밥, 동사·버전 금지
#   POST /api/cgr/track/visits (기존: /api/v1/track)
router = APIRouter(tags=["track"])


@router.post("/visits", summary="익명 방문 핑", dependencies=[Depends(require_api_key)])
async def post_track(body: TrackIn, request: Request) -> dict:
    visitor = (body.visitor or "").strip()[:64] or anon_visitor(request)
    analytics.log_visit(visitor, body.page, body.service)
    return {"ok": True}
