"""노무 가이드 DB 조회 공용 함수·서식 파일 경로."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.repositories import base as _db

# 양식 파일 저장소 — `cgr.db.get_db_path` 와 같은 ROOT 기준
_FORMS_DIR = Path(__file__).resolve().parents[3] / "data" / "forms"

def _query_all(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with _db.connect() as conn:
        cur = conn.execute(sql, params)
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, list(r))) for r in cur.fetchall()]
