"""시드용 SQLite 마스터 DB(`data/master.db`) helper.

슬롯 yaml·코퍼스·임금 마스터를 SQLite 로 모으는 seed 스크립트 전용이다.
서비스(app)는 PostgreSQL(DE10)을 쓰고, 이 파일은 PostgreSQL 적재 원천을 만드는 데만 쓴다.
env `CGR_MASTER_DB` 로 경로 override.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "master.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "master_schema.sql"


def get_db_path() -> Path:
    env = os.environ.get("CGR_MASTER_DB")
    return Path(env) if env else DEFAULT_DB_PATH


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """SQLite 연결 컨텍스트 — 자동 commit / rollback. Row factory: sqlite3.Row."""
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
    """스키마 생성(또는 재생성)."""
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"master_schema.sql not found: {SCHEMA_PATH}")
    with connect() as conn:
        if drop_first:
            # FK 의존성 무시하고 drop — 재생성 직전에만 잠시 OFF
            conn.execute("PRAGMA foreign_keys = OFF")
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall():
                conn.execute(f"DROP VIEW IF EXISTS {row['name']}")
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall():
                conn.execute(f"DROP TABLE IF EXISTS {row['name']}")
            conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def table_counts() -> dict[str, int]:
    """각 테이블의 행 수 — 검증·디버그용."""
    out: dict[str, int] = {}
    with connect() as conn:
        tables = [
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        for t in tables:
            out[t] = conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]
    return out
