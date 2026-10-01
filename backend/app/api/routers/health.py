"""헬스체크 라우터 — 도메인 없음.

원본 `cgr/api/main.py` 의 `/health` 를 별도 라우터로 분리.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.core.database import get_pool

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """앱·DB 살아있는지 확인."""
    services: dict[str, str] = {"api": "ok"}
    # PG 살아있는지 SELECT 1 로 확인 (풀에서 커넥션 하나 대여)
    try:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        services["db"] = "ok"
    except Exception as e:  # noqa: BLE001
        services["db"] = f"error: {e.__class__.__name__}"
    return {"status": "ok", "version": "2.0.0", "services": services}
