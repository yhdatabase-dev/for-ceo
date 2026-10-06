"""통합 DB — PostgreSQL 연결 helper.

스키마는 DE10 테이블정의서 기준 (ai · app). 접속 정보는 app.core.config.get_db_conninfo.

- 모든 쿼리는 `with connect() as conn:` 컨텍스트 매니저로 — 자동 commit/rollback
- 행은 dict 로 반환 → 컬럼명으로 접근 (row['name'])
- 값은 바인딩 파라미터(%s)로만 전달한다 (DE03 4.6)
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from app.core.config import get_db_conninfo

CONNECT_TIMEOUT_SEC = 5


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """PostgreSQL 연결 컨텍스트 — 자동 commit / rollback."""
    conn = psycopg.connect(
        **get_db_conninfo(), row_factory=dict_row, connect_timeout=CONNECT_TIMEOUT_SEC
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
