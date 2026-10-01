"""audit_case / audit_finding 리포지토리 — psycopg raw SQL.

WR/EC 검토 결과 저장.
"""
from __future__ import annotations

import json
from typing import Any

from psycopg.types.json import Jsonb

from app.repositories.base import BaseRepo


class AuditRepo(BaseRepo):
    def create_case(
        self,
        *,
        case_uid: str,
        document_type_id: int | None,
        filename: str | None,
        business_size: str | None,
        worker_types: list[str],
        overall_label: str | None,
        overall_status: str | None,
        risk_level: str | None,
        elapsed_sec: float | None,
        llm_model: str | None,
        source_upload_id: int | None,
        report_json: dict[str, Any] | None,
    ) -> int:
        """audit_case INSERT — 반환: 생성된 id."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cgr_txn.audit_case
                    (case_uid, document_type_id, filename, business_size,
                     worker_types, overall_label, overall_status, risk_level,
                     elapsed_sec, llm_model, source_upload_id, report_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    case_uid, document_type_id, filename, business_size,
                    Jsonb(worker_types), overall_label, overall_status, risk_level,
                    elapsed_sec, llm_model, source_upload_id,
                    Jsonb(report_json) if report_json else None,
                ),
            )
            row = cur.fetchone()
        return int(row["id"])

    def add_findings(self, case_id: int, findings: list[dict[str, Any]]) -> int:
        """audit_finding 벌크 INSERT — 반환: 삽입 개수."""
        if not findings:
            return 0
        with self.conn.cursor() as cur:
            # executemany 대신 UNNEST 로 한 번에 (성능 우위)
            cur.executemany(
                """
                INSERT INTO cgr_txn.audit_finding
                    (case_id, check_item_id, slot_id, bucket, status, severity,
                     found_text, extracted_value, reason, recommendation)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        case_id,
                        f.get("check_item_id"),
                        f.get("slot_id"),
                        f.get("bucket"),
                        f.get("status"),
                        f.get("severity"),
                        f.get("found_text"),
                        Jsonb(f.get("extracted_value")) if f.get("extracted_value") is not None else None,
                        f.get("reason"),
                        f.get("recommendation"),
                    )
                    for f in findings
                ],
            )
        return len(findings)

    def get_case_by_uid(self, case_uid: str) -> dict | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, case_uid, document_type_id, filename, business_size,
                       worker_types, overall_label, overall_status, risk_level,
                       elapsed_sec, llm_model, source_upload_id,
                       report_md_path, created_at
                  FROM cgr_txn.audit_case
                 WHERE case_uid = %s
                """,
                (case_uid,),
            )
            return cur.fetchone()
