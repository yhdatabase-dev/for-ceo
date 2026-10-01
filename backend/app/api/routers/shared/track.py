"""익명 방문 트래킹 — 원본 `cgr/api/routes/track.py` 이관."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
import psycopg

from app.api.deps import get_db, get_visitor, require_user
from app.core.exceptions import CgrError
from app.core.logging import get_logger
from app.repositories.shared import VisitRepo

log = get_logger(__name__)

# 라우터 전체에 인증 적용 (원본도 익명 방문 트래킹에 API 키 요구)
router = APIRouter(
    prefix="/track",
    tags=["track"],
    dependencies=[Depends(require_user)],
)


class TrackIn(BaseModel):
    page: str = ""
    service: str = ""


@router.post("", summary="익명 방문 로그 기록")
def track(
    body: TrackIn,
    request: Request,
    db: psycopg.Connection = Depends(get_db),
) -> dict:
    visitor = get_visitor(request)
    try:
        VisitRepo(db).log(visitor=visitor, page=body.page, service=body.service)
    except CgrError:
        raise
    except Exception as e:
        # 트래킹 실패는 사용자 흐름에 영향 없이 성공 응답 (로그만 남김)
        log.warning("track.visit 로그 실패 (무시): %s", e)
        return {"ok": False}
    return {"ok": True}
