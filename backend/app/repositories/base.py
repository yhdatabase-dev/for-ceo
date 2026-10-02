"""통합 마스터 DB — SQLite 연결·세션 helper.

기본 경로: `mvp/data/master.db`. env `CGR_MASTER_DB` 로 override 가능.

설계 원칙
- read-heavy + 단일 사용자(MVP) → SQLite 한 파일로 충분
- 추후 Postgres 전환 시 동일 SQL 대부분 호환 (DDL 만 일부 수정)
- 모든 쿼리는 `with connect() as conn:` 컨텍스트 매니저로 — 자동 commit/rollback
- 읽기 전용 쿼리도 connect() 사용. SQLite 는 부담 작음
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "master.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_db_path() -> Path:
    env = os.environ.get("CGR_MASTER_DB")
    if env:
        return Path(env)
    return DEFAULT_DB_PATH


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """SQLite 연결 컨텍스트 — 자동 commit / rollback.

    Row factory: sqlite3.Row → 컬럼명으로 접근 (row['name']).
    Foreign key: PRAGMA 로 강제.
    """
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(*, drop_first: bool = False) -> None:
    """스키마 생성(또는 재생성). seed 스크립트가 호출."""
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"schema.sql not found: {SCHEMA_PATH}")
    with connect() as conn:
        if drop_first:
            # FK 의존성 무시하고 drop — 재생성 직전에만 잠시 OFF
            conn.execute("PRAGMA foreign_keys = OFF")
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='view'"
            )
            for row in cur.fetchall():
                conn.execute(f"DROP VIEW IF EXISTS {row['name']}")
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            )
            for row in cur.fetchall():
                conn.execute(f"DROP TABLE IF EXISTS {row['name']}")
            conn.execute("PRAGMA foreign_keys = ON")
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        conn.executescript(sql)


def table_counts() -> dict[str, int]:
    """각 테이블의 행 수 — 검증·디버그용."""
    out: dict[str, int] = {}
    with connect() as conn:
        cur = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tables = [row["name"] for row in cur.fetchall()]
        for t in tables:
            c = conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()
            out[t] = c["n"]
    return out
