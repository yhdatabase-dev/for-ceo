"""review_history 리포지토리 — psycopg raw SQL.

원본 매핑
- append_history()   → append()
- read_history(limit) → list(limit, offset)
- stats()             → stats()
"""
from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from app.repositories.base import BaseRepo


class HistoryRepo(BaseRepo):
    def append(
        self,
        *,
        case_id: int | None,
        case_uid: str,
        filename: str | None,
        overall_label: str | None,
        llm_model: str | None,
        n_findings: int,
        by_status: dict[str, Any],
        by_severity: dict[str, Any],
        by_bucket: dict[str, Any],
        top_violations: list[Any],
        report_path: str | None,
    ) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cgr_txn.review_history
                    (case_id, case_uid, filename, overall_label, llm_model,
                     n_findings, by_status, by_severity, by_bucket, top_violations,
                     report_path)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    case_id, case_uid, filename, overall_label, llm_model,
                    n_findings,
                    Jsonb(by_status), Jsonb(by_severity),
                    Jsonb(by_bucket), Jsonb(top_violations),
                    report_path,
                ),
            )
            row = cur.fetchone()
        return int(row["id"])

    def list(self, *, limit: int = 20, offset: int = 0) -> tuple[int, list[dict]]:
        """(total, rows) 반환."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM cgr_txn.review_history")
            total = int(cur.fetchone()["cnt"])

            cur.execute(
                """
                SELECT id, case_id, case_uid, filename, overall_label, llm_model,
                       n_findings, by_status, by_severity, by_bucket, top_violations,
                       report_path, created_at
                  FROM cgr_txn.review_history
                 ORDER BY created_at DESC
                 LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            rows = cur.fetchall()
        return total, rows

    def stats(self) -> dict[str, Any]:
        """전체·최근 30일 카운트."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM cgr_txn.review_history) AS n_total,
                    (SELECT COUNT(*) FROM cgr_txn.review_history
                      WHERE created_at >= NOW() - INTERVAL '30 days') AS n_recent_30d
                """
            )
            row = cur.fetchone()
        return {
            "n_total": int(row["n_total"] or 0),
            "n_recent_30d": int(row["n_recent_30d"] or 0),
        }

    def get_by_case_uid(self, case_uid: str) -> dict | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, case_id, case_uid, filename, overall_label, llm_model,
                       n_findings, by_status, by_severity, by_bucket, top_violations,
                       report_path, created_at
                  FROM cgr_txn.review_history
                 WHERE case_uid = %s
                """,
                (case_uid,),
            )
            return cur.fetchone()
