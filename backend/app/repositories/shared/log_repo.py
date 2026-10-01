"""로그 리포지토리 — cgr_log.* 테이블 (psycopg raw SQL).

원본 매핑
- log_visit                          → VisitRepo.log
- add_upload / list_uploads / get    → UploadRepo.create / list / get
- log_interaction / list / get       → InteractionLogRepo.log / list / get
- access_log.log_event / read        → AccessLogRepo.log / list

⚠️ InteractionLog 는 저장 전 PII 마스킹 강제 (서비스에서 이미 마스킹돼도 방어적 재마스킹).
"""
from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from app.core.security import mask_pii_text
from app.repositories.base import BaseRepo


class VisitRepo(BaseRepo):
    def log(self, *, visitor: str, page: str, service: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cgr_log.visit_event (visitor, page, service)
                VALUES (%s, %s, %s)
                """,
                (visitor, page, service),
            )


class UploadRepo(BaseRepo):
    def create(
        self,
        *,
        service: str,
        filename: str,
        size_bytes: int,
        mime: str | None,
        ext: str | None,
        visitor: str | None,
        case_uid: str | None,
        storage_url: str | None,
    ) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cgr_log.upload_record
                    (service, filename, size_bytes, mime, ext, visitor, case_uid, storage_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (service, filename, size_bytes, mime, ext, visitor, case_uid, storage_url),
            )
            row = cur.fetchone()
        return int(row["id"])

    def list(
        self, *, limit: int = 20, offset: int = 0, service: str | None = None
    ) -> tuple[int, list[dict]]:
        params: list[Any] = []
        where = "1=1"
        if service:
            where = "service = %s"
            params.append(service)

        with self.conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) AS cnt FROM cgr_log.upload_record WHERE {where}",
                params,
            )
            total = int(cur.fetchone()["cnt"])

            cur.execute(
                f"""
                SELECT id, ts, service, filename, size_bytes, mime, ext,
                       visitor, case_uid, storage_url, retention_until
                  FROM cgr_log.upload_record
                 WHERE {where}
                 ORDER BY ts DESC
                 LIMIT %s OFFSET %s
                """,
                [*params, limit, offset],
            )
            rows = cur.fetchall()
        return total, rows

    def get(self, upload_id: int) -> dict | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, ts, service, filename, size_bytes, mime, ext,
                       visitor, case_uid, storage_url, retention_until
                  FROM cgr_log.upload_record
                 WHERE id = %s
                """,
                (upload_id,),
            )
            return cur.fetchone()


class InteractionLogRepo(BaseRepo):
    def log(
        self,
        *,
        kind: str,
        model: str,
        input_text: str,
        output_text: str,
        visitor: str | None = None,
        case_uid: str | None = None,
        upload_id: int | None = None,
    ) -> int:
        """LLM 상호작용 저장 — PII 마스킹 방어적 재적용."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cgr_log.interaction_log
                    (kind, model, input_text, output_text, visitor, case_uid, upload_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    kind, model,
                    mask_pii_text(input_text or ""),
                    mask_pii_text(output_text or ""),
                    visitor, case_uid, upload_id,
                ),
            )
            row = cur.fetchone()
        return int(row["id"])

    def list(
        self, *, limit: int = 20, offset: int = 0, kind: str | None = None
    ) -> tuple[int, list[dict]]:
        params: list[Any] = []
        where = "1=1"
        if kind:
            where = "kind = %s"
            params.append(kind)

        with self.conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) AS cnt FROM cgr_log.interaction_log WHERE {where}",
                params,
            )
            total = int(cur.fetchone()["cnt"])

            cur.execute(
                f"""
                SELECT id, ts, kind, model, input_text, output_text,
                       visitor, case_uid, upload_id
                  FROM cgr_log.interaction_log
                 WHERE {where}
                 ORDER BY ts DESC
                 LIMIT %s OFFSET %s
                """,
                [*params, limit, offset],
            )
            rows = cur.fetchall()
        return total, rows

    def get(self, log_id: int) -> dict | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, ts, kind, model, input_text, output_text,
                       visitor, case_uid, upload_id
                  FROM cgr_log.interaction_log
                 WHERE id = %s
                """,
                (log_id,),
            )
            return cur.fetchone()


class AccessLogRepo(BaseRepo):
    def log(
        self,
        *,
        service: str,
        action: str,
        session_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cgr_log.access_event (service, action, session_id, meta)
                VALUES (%s, %s, %s, %s)
                """,
                (service, action, session_id, Jsonb(meta) if meta is not None else None),
            )

    def list(self, *, limit: int = 100) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, ts, service, action, session_id, meta
                  FROM cgr_log.access_event
                 ORDER BY ts DESC
                 LIMIT %s
                """,
                (limit,),
            )
            return cur.fetchall()
