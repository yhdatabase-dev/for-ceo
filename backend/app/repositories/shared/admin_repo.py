"""cgr_admin.settings / prompt 리포지토리 — psycopg raw SQL.

편집 이력 (settings_history / prompt_history) 은 upsert 시 append-only 로 남김.
"""
from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from app.repositories.base import BaseRepo


class SettingRepo(BaseRepo):
    def get(self, key: str) -> Any | None:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT value FROM cgr_admin.settings WHERE key = %s",
                (key,),
            )
            row = cur.fetchone()
        return row["value"] if row else None

    def load_all(self) -> dict[str, Any]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT key, value FROM cgr_admin.settings")
            rows = cur.fetchall()
        return {r["key"]: r["value"] for r in rows}

    def update(self, key: str, value: Any, *, edited_by: str | None = None) -> None:
        """Upsert + 이력 append (트랜잭션 안에서 실행됨)."""
        with self.conn.cursor() as cur:
            # 이전 값 조회
            cur.execute(
                "SELECT value FROM cgr_admin.settings WHERE key = %s",
                (key,),
            )
            prev = cur.fetchone()

            # 이력 append
            cur.execute(
                """
                INSERT INTO cgr_admin.settings_history (key, prev_value, new_value, edited_by)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    key,
                    Jsonb(prev["value"]) if prev else None,
                    Jsonb(value),
                    edited_by,
                ),
            )

            # UPSERT
            cur.execute(
                """
                INSERT INTO cgr_admin.settings (key, value, updated_by, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (key) DO UPDATE
                   SET value = EXCLUDED.value,
                       updated_by = EXCLUDED.updated_by,
                       updated_at = NOW()
                """,
                (key, Jsonb(value), edited_by),
            )

    def bulk_update(self, patch: dict[str, Any], *, edited_by: str | None = None) -> None:
        for k, v in patch.items():
            self.update(k, v, edited_by=edited_by)


class PromptRepo(BaseRepo):
    def get(self, key: str) -> dict | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT key, label, category, content, is_override,
                       updated_by, updated_at
                  FROM cgr_admin.prompt
                 WHERE key = %s
                """,
                (key,),
            )
            return cur.fetchone()

    def list_all(self) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT key, label, category, content, is_override,
                       updated_by, updated_at
                  FROM cgr_admin.prompt
                 ORDER BY key
                """
            )
            return cur.fetchall()

    def save(
        self,
        *,
        key: str,
        content: str,
        label: str | None = None,
        category: str | None = None,
        edited_by: str | None = None,
    ) -> None:
        with self.conn.cursor() as cur:
            # 이전 내용 조회
            cur.execute(
                "SELECT content FROM cgr_admin.prompt WHERE key = %s",
                (key,),
            )
            prev = cur.fetchone()

            # 이력 append
            cur.execute(
                """
                INSERT INTO cgr_admin.prompt_history
                    (key, prev_content, new_content, edited_by)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    key,
                    prev["content"] if prev else None,
                    content,
                    edited_by,
                ),
            )

            # UPSERT (신규는 label 필수 → 없으면 key 재사용)
            cur.execute(
                """
                INSERT INTO cgr_admin.prompt
                    (key, label, category, content, is_override, updated_by, updated_at)
                VALUES (%s, %s, %s, %s, TRUE, %s, NOW())
                ON CONFLICT (key) DO UPDATE
                   SET content = EXCLUDED.content,
                       is_override = TRUE,
                       label = COALESCE(EXCLUDED.label, cgr_admin.prompt.label),
                       category = COALESCE(EXCLUDED.category, cgr_admin.prompt.category),
                       updated_by = EXCLUDED.updated_by,
                       updated_at = NOW()
                """,
                (key, label or key, category, content, edited_by),
            )

    def reset(self, key: str, *, edited_by: str | None = None) -> None:
        """is_override=FALSE 로 → resolver 가 코드 default 로 폴백."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT content FROM cgr_admin.prompt WHERE key = %s",
                (key,),
            )
            prev = cur.fetchone()
            if not prev:
                return

            cur.execute(
                """
                INSERT INTO cgr_admin.prompt_history
                    (key, prev_content, new_content, edited_by)
                VALUES (%s, %s, NULL, %s)
                """,
                (key, prev["content"], edited_by),
            )
            cur.execute(
                "UPDATE cgr_admin.prompt SET is_override = FALSE, updated_at = NOW() WHERE key = %s",
                (key,),
            )
