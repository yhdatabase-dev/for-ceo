"""검토 이력 조회·통계."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query

from app.core.security import require_api_key
from app.repositories.shared import review_history as history
from app.schemas.history.response import (
    HistoryEntryOut,
    HistoryListOut,
    HistoryStatsOut,
)

router = APIRouter(tags=["history"])


@router.get(
    "",
    response_model=HistoryListOut,
    summary="검토 이력 목록",
    dependencies=[Depends(require_api_key)],
)
async def get_history(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: str | None = Query(default=None, description="서비스 필터 (취업규칙/근로계약서 등)"),
    days: int | None = Query(default=None, description="최근 N일만"),
) -> HistoryListOut:
    rows = history.read_history()
    if service:
        rows = [r for r in rows if r.get("service") == service]
    if days:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = [r for r in rows if (r.get("ts") or "") >= cutoff]
    total = len(rows)
    # 최신순
    rows = list(reversed(rows))
    chunk = rows[offset : offset + limit]
    out_entries = [
        HistoryEntryOut(
            ts=r.get("ts", ""),
            case_id=r.get("case_id", ""),
            filename=r.get("filename", ""),
            overall_label=r.get("overall_label", ""),
            llm_model=r.get("llm_model", ""),
            by_bucket=r.get("by_bucket") or {},
            top_violations=r.get("top_violations") or [],
        )
        for r in chunk
    ]
    return HistoryListOut(total=total, entries=out_entries)

@router.get(
    "/stats",
    response_model=HistoryStatsOut,
    summary="검토 이력 요약 통계",
    dependencies=[Depends(require_api_key)],
)
async def get_history_stats() -> HistoryStatsOut:
    s = history.stats()
    return HistoryStatsOut(
        n_total=s.get("n_total", 0),
        n_recent_30d=s.get("n_recent_30d", 0),
        avg_violation=s.get("avg_violation", 0.0),
        avg_missing=s.get("avg_missing", 0.0),
        top_slots=s.get("top_slots", []),
    )
