"""Repository 공통 베이스 — psycopg 3 Connection 기반.

사용:
    from app.repositories.base import BaseRepo

    class GuideRepo(BaseRepo):
        def list_items(self, audience: str | None) -> list[GuideItemOut]:
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT code, audience, ... FROM cgr_master.guide_item WHERE ...",
                    (audience,),
                )
                rows = cur.fetchall()   # list[dict] (dict_row 덕분)
            return [GuideItemOut(**r) for r in rows]

Rule:
- Connection 은 repository 밖으로 새어나가면 안 됨 (규칙 §2).
- 반환은 반드시 Pydantic DTO (dict/tuple 직접 반환 금지).
"""
from __future__ import annotations

import psycopg


class BaseRepo:
    """모든 리포지토리의 부모."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn
