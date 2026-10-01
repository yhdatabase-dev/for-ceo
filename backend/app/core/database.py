"""PostgreSQL 커넥션 풀 — psycopg 3 + psycopg_pool (SQLAlchemy 미사용).

===============================================================================
설계
===============================================================================
- 프로세스 싱글턴 커넥션 풀 (psycopg_pool.ConnectionPool).
- uvicorn 워커 수를 감안한 풀 크기 자동 계산 → PG max_connections 초과 방지.
- row_factory=dict_row → 커서 결과가 dict → 리포지토리에서 그대로 Pydantic 변환.
- placeholder 는 `%s` (psycopg 표준).
- 트랜잭션: 라우트 종료 시 자동 commit / 예외 시 rollback (deps.get_db 에서).

DB 는 외부에서 이미 프로비저닝 되어있다 (테이블·인덱스 포함).
- 이 앱은 스키마 CREATE 안 함.
- Alembic·models 없음.
"""
from __future__ import annotations

from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

_POOL: ConnectionPool | None = None


# ─────────────────────────────────────────────────────────────
# 풀 크기 계산 — 워커 수 감안
# ─────────────────────────────────────────────────────────────
def _calc_pool_size() -> tuple[int, int]:
    """워커 수 감안 (min, max) 계산.

    총 커넥션 = workers × max_per_worker → PG max_connections 이하로 유지.
    """
    s = get_settings()
    workers = max(1, s.server.workers)
    max_per_worker = max(1, s.db.total_max_conn // workers)
    min_per_worker = max(1, s.db.pool_min_per_worker)
    min_per_worker = min(min_per_worker, max_per_worker)
    log.info(
        "db_pool.sizing",
        extra={
            "workers": workers,
            "min_per_worker": min_per_worker,
            "max_per_worker": max_per_worker,
        },
    )
    return min_per_worker, max_per_worker


# ─────────────────────────────────────────────────────────────
# 풀 lifecycle
# ─────────────────────────────────────────────────────────────
def get_pool() -> ConnectionPool:
    """싱글턴 커넥션 풀 (lazy 초기화)."""
    global _POOL
    if _POOL is None:
        s = get_settings()
        dsn = s.db.dsn.get_secret_value()
        if not dsn:
            raise RuntimeError(
                "CGR_PG_DSN 이 설정되지 않았습니다. "
                ".env 또는 셸 환경변수로 지정하세요."
            )
        min_size, max_size = _calc_pool_size()
        _POOL = ConnectionPool(
            conninfo=dsn,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row},
            open=True,
        )
        log.info("db_pool.opened", extra={"max_size": max_size})
    return _POOL


def close_pool() -> None:
    """앱 종료 시 호출 (main.lifespan shutdown)."""
    global _POOL
    if _POOL is not None:
        try:
            _POOL.close()
        except Exception:  # noqa: BLE001
            log.exception("db_pool.close_failed")
        _POOL = None
        log.info("db_pool.closed")


def reset_pool() -> None:
    """죽은 풀 재생성 — DB 재기동 등으로 풀 전체 무효화 시."""
    close_pool()
    get_pool()
    log.warning("db_pool.reset")


# ─────────────────────────────────────────────────────────────
# 요청 스코프 커넥션 (deps.get_db 가 이걸 wrap)
# ─────────────────────────────────────────────────────────────
def yield_connection() -> Iterator[psycopg.Connection]:
    """요청 하나당 커넥션 하나 — 자동 commit/rollback/반환.

    - 예외 발생 시 rollback
    - 정상 종료 시 commit
    - 마지막에 커넥션은 풀로 자동 반환 (psycopg_pool 이 처리)
    """
    pool = get_pool()
    with pool.connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                log.exception("db.rollback_failed")
            raise
