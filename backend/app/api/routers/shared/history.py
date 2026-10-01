"""검토 이력 조회 — 원본 `cgr/api/routes/history.py` 이관."""
from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends

from app.api.deps import Pagination, get_db, require_user
from app.core.exceptions import CgrError
from app.core.logging import get_logger
from app.repositories.shared import HistoryRepo

log = get_logger(__name__)

# 라우터 전체에 인증 적용
router = APIRouter(
    prefix="/history",
    tags=["history"],
    dependencies=[Depends(require_user)],
)


@router.get("", summary="검토 이력 페이지네이션 조회")
def list_history(
    p: Pagination = Depends(),
    db: psycopg.Connection = Depends(get_db),
) -> dict:
    try:
        total, rows = HistoryRepo(db).list(limit=p.limit, offset=p.offset)
    except CgrError:
        raise
    except Exception as e:
        raise CgrError(f"검토 이력 조회 실패: {type(e).__name__}: {e}") from e

    return {
        "total": total,
        "entries": [
            {
                "ts": r["created_at"].isoformat() if r.get("created_at") else None,
                "case_id": r.get("case_uid"),
                "filename": r.get("filename") or "",
                "overall_label": r.get("overall_label") or "",
                "llm_model": r.get("llm_model") or "",
                "by_bucket": r.get("by_bucket") or {},
                "top_violations": r.get("top_violations") or [],
            }
            for r in rows
        ],
    }


@router.get("/stats", summary="검토 이력 통계 (전체·최근 30일)")
def history_stats(db: psycopg.Connection = Depends(get_db)) -> dict:
    try:
        return HistoryRepo(db).stats()
    except CgrError:
        raise
    except Exception as e:
        raise CgrError(f"검토 통계 조회 실패: {type(e).__name__}: {e}") from e
