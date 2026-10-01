"""공통 의존성 — DB 커넥션·인증·페이지네이션·요청 컨텍스트.

DB 는 psycopg 3 커넥션 (SQLAlchemy Session 아님).
"""
from __future__ import annotations

from typing import Iterator

import psycopg
from fastapi import Query, Request

from app.core.database import yield_connection
from app.core.logging import bind_context, new_request_id
from app.core.security import anon_visitor, require_admin_key, require_api_key


# ─── DB 커넥션 ────────────────────────────────────
def get_db() -> Iterator[psycopg.Connection]:
    """요청 스코프 psycopg Connection.

    사용:
        from fastapi import Depends
        import psycopg
        from app.api.deps import get_db

        @router.get("/x")
        def handler(db: psycopg.Connection = Depends(get_db)):
            with db.cursor() as cur:
                cur.execute("SELECT ...")
                row = cur.fetchone()   # dict_row → row["col"] 접근
    """
    yield from yield_connection()


# ─── 인증·인가 ────────────────────────────────────
def require_user(request: Request) -> None:
    require_api_key(request)


def require_admin(request: Request) -> None:
    require_admin_key(request)


# ─── 요청 컨텍스트 ────────────────────────────────
def get_visitor(request: Request) -> str:
    """익명 방문자 해시 (IP+UA+날짜 SHA-256[:16])."""
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")
    return anon_visitor(ip, ua)


def bind_request_context(request: Request) -> str:
    rid = new_request_id()
    bind_context(request_id=rid, visitor=get_visitor(request))
    return rid


# ─── 페이지네이션 ─────────────────────────────────
class Pagination:
    def __init__(
        self,
        limit: int = Query(20, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> None:
        self.limit = limit
        self.offset = offset
