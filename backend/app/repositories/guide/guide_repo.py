"""guide 도메인 리포지토리 — psycopg raw SQL.

===============================================================================
원본 대비 주요 변경
===============================================================================
원본 (`cgr/api/routes/guide.py`)
- 라우터 안에서 `_query_all(sql, params)` 로 SQLite raw SQL 직접 실행.

v2
- SQL 은 이 리포지토리에서만.
- psycopg 3 + dict_row → cur.fetchone() / fetchall() 이 dict 반환.
- 반환은 반드시 Pydantic Out DTO.
- 스키마 명시: cgr_master.<table>

원본 → v2 라우트 매핑
- GET /guide/items           → list_guide_items
- GET /guide/items/{code}    → get_guide_item
- GET /guide/glossary        → list_glossary
- GET /guide/by-size/{...}   → list_size_threshold_duties
- GET /guide/by-stage/{...}  → list_by_stage
- GET /guide/timeline        → list_timeline
- GET /guide/forms           → list_forms
- GET /guide/forms/{code}    → get_form_row (라우터에서 로컬 파일 확인)
- GET /guide/wage-calc       → list_wage_calc
- GET /guide/orgs            → list_orgs
- GET /guide/audit           → list_audit_guide
- GET /guide/required-docs   → list_required_docs
- GET /guide/lifecycle       → list_lifecycle
- GET /guide/recruit         → list_recruit
- GET /guide/overview        → overview
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.repositories.base import BaseRepo
from app.schemas.guide.responses import (
    FormOut,
    GlossaryItemOut,
    GlossaryListOut,
    GuideItemOut,
    GuideOverviewOut,
    ObligationTimelineOut,
    SizeThresholdDutyOut,
)


class GuideRepo(BaseRepo):
    """가이드 도메인 SELECT-heavy 리포지토리."""

    # ─── guide_item ────────────────────────────
    def list_guide_items(
        self, *, audience: str | None = None, category: str | None = None
    ) -> list[GuideItemOut]:
        # 동적 필터 — 조건 있는 것만 WHERE 절에 추가
        where = ["excluded_from_service = FALSE"]
        params: list[Any] = []
        if audience:
            where.append("audience = %s")
            params.append(audience)
        if category:
            where.append("category = %s")
            params.append(category)
        sql = f"""
            SELECT code, audience, category, title,
                   worker_reason, employer_reason, key_points, related_laws,
                   priority, applies_under_5, note
              FROM cgr_master.guide_item
             WHERE {" AND ".join(where)}
             ORDER BY priority NULLS LAST, id
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [GuideItemOut(**r) for r in rows]

    def get_guide_item(self, code: str) -> GuideItemOut | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT code, audience, category, title,
                       worker_reason, employer_reason, key_points, related_laws,
                       priority, applies_under_5, note
                  FROM cgr_master.guide_item
                 WHERE code = %s
                """,
                (code,),
            )
            row = cur.fetchone()
        return GuideItemOut(**row) if row else None

    # ─── guide_glossary ────────────────────────
    def list_glossary(self) -> GlossaryListOut:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT code, term, short_def, full_def, confusable_with, legal_basis
                  FROM cgr_master.guide_glossary
                 ORDER BY term
                """
            )
            rows = cur.fetchall()
        return GlossaryListOut(items=[GlossaryItemOut(**r) for r in rows])

    # ─── size_threshold_duty ───────────────────
    def list_size_threshold_duties(self) -> list[SizeThresholdDutyOut]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT code, min_size, duty, description, related_docs, legal_basis, note
                  FROM cgr_master.size_threshold_duty
                 ORDER BY id
                """
            )
            rows = cur.fetchall()
        return [SizeThresholdDutyOut(**r) for r in rows]

    # ─── obligation_timeline ───────────────────
    def list_timeline(self) -> list[ObligationTimelineOut]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT code, stage, duty, description, deadline,
                       legal_basis, priority, penalty
                  FROM cgr_master.obligation_timeline
                 ORDER BY id
                """
            )
            rows = cur.fetchall()
        return [ObligationTimelineOut(**r) for r in rows]

    def list_by_stage(self, stage: str) -> list[ObligationTimelineOut]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT code, stage, duty, description, deadline,
                       legal_basis, priority, penalty
                  FROM cgr_master.obligation_timeline
                 WHERE stage ILIKE %s
                 ORDER BY id
                """,
                (f"%{stage}%",),
            )
            rows = cur.fetchall()
        return [ObligationTimelineOut(**r) for r in rows]

    # ─── form_template ─────────────────────────
    def list_forms(
        self, *, category: str | None = None, audience: str | None = None
    ) -> list[FormOut]:
        where = ["excluded_from_service = FALSE"]
        params: list[Any] = []
        if category:
            where.append("category = %s")
            params.append(category)
        if audience:
            where.append("audience = %s")
            params.append(audience)
        sql = f"""
            SELECT code, form_name, category, purpose, submitter, submit_to,
                   submit_method, deadline, legal_basis, audience,
                   download_url, local_filename, local_mime
              FROM cgr_master.form_template
             WHERE {" AND ".join(where)}
             ORDER BY id
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [_to_form_out(r) for r in rows]

    def get_form_row(self, code: str) -> dict | None:
        """라우터에서 파일 다운로드용으로 사용 — dict 그대로 반환 (예외적)."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT code, form_name, local_filename, local_mime, download_url
                  FROM cgr_master.form_template
                 WHERE code = %s
                """,
                (code,),
            )
            return cur.fetchone()

    # ─── wage_calc_formula ─────────────────────
    def list_wage_calc(self, *, violation_code: str | None = None) -> list[dict]:
        # 이 응답은 라우터에서 dict list 로 그대로 노출 (스키마 확정 전)
        where = ["1=1"]
        params: list[Any] = []
        if violation_code:
            where.append("related_violation_code = %s")
            params.append(violation_code)
        sql = f"""
            SELECT code, category, calc_name, formula, conditions,
                   limits, legal_basis, note, related_violation_code
              FROM cgr_master.wage_calc_formula
             WHERE {" AND ".join(where)}
             ORDER BY id
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    # ─── gov_org ───────────────────────────────
    def list_orgs(self) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT code, org_class, org_name, duties, common_cases,
                       phone, online_channel, jurisdiction, note
                  FROM cgr_master.gov_org
                 WHERE excluded_from_service = FALSE
                 ORDER BY id
                """
            )
            return cur.fetchall()

    # ─── audit_guide ───────────────────────────
    def list_audit_guide(self) -> dict[str, list[dict]]:
        """kind=type / procedure 로 나눠 반환."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT kind, code, name, step_no, timing, description,
                       period_covered, legal_basis
                  FROM cgr_master.audit_guide
                 ORDER BY step_no
                """
            )
            rows = cur.fetchall()
        types, procedure = [], []
        for r in rows:
            item = {k: v for k, v in r.items() if k != "kind"}
            (types if r["kind"] == "type" else procedure).append(item)
        return {"types": types, "procedure": procedure}

    # ─── required_document ─────────────────────
    def list_required_docs(self) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT code, classification, doc_name, description,
                       prep_time, retention_period, legal_basis, penalty
                  FROM cgr_master.required_document
                 ORDER BY id
                """
            )
            return cur.fetchall()

    # ─── employment_lifecycle ─────────────────
    def list_lifecycle(self) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT code, phase, sub_topic, requirement, related_docs,
                       timing, legal_basis, note
                  FROM cgr_master.employment_lifecycle
                 ORDER BY id
                """
            )
            return cur.fetchall()

    # ─── recruit_compliance ────────────────────
    def list_recruit(self) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT code, stage, duty, description, violation_examples,
                       penalty, applies_to, legal_basis, checkpoint
                  FROM cgr_master.recruit_compliance
                 ORDER BY id
                """
            )
            return cur.fetchall()

    # ─── overview (카운트) ────────────────────
    def overview(self) -> GuideOverviewOut:
        # 8개 테이블 COUNT — 한 번의 UNION ALL 로 왕복 1회
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT 'n_guide_items'    AS label, COUNT(*) AS cnt FROM cgr_master.guide_item
                UNION ALL SELECT 'n_timeline',      COUNT(*) FROM cgr_master.obligation_timeline
                UNION ALL SELECT 'n_wage_calc',     COUNT(*) FROM cgr_master.wage_calc_formula
                UNION ALL SELECT 'n_glossary',      COUNT(*) FROM cgr_master.guide_glossary
                UNION ALL SELECT 'n_forms',         COUNT(*) FROM cgr_master.form_template
                UNION ALL SELECT 'n_orgs',          COUNT(*) FROM cgr_master.gov_org
                UNION ALL SELECT 'n_required_docs', COUNT(*) FROM cgr_master.required_document
                UNION ALL SELECT 'n_lifecycle',     COUNT(*) FROM cgr_master.employment_lifecycle
                """
            )
            rows = cur.fetchall()
        counts = {r["label"]: int(r["cnt"]) for r in rows}
        return GuideOverviewOut(**counts)


# ─────────────────────────────────────────────────────────────
# 내부 매핑
# ─────────────────────────────────────────────────────────────
def _to_form_out(r: dict) -> FormOut:
    """form_template row → FormOut (has_local 계산)."""
    has_local = False
    local_filename = r.get("local_filename")
    if local_filename:
        fp = get_settings().data.data_dir / "forms" / local_filename
        has_local = fp.exists()
    return FormOut(
        code=r["code"],
        form_name=r["form_name"],
        category=r.get("category"),
        purpose=r.get("purpose"),
        submitter=r.get("submitter"),
        submit_to=r.get("submit_to"),
        submit_method=r.get("submit_method"),
        deadline=r.get("deadline"),
        legal_basis=r.get("legal_basis"),
        audience=r.get("audience") or "employer",
        has_local=has_local,
        download_url=r.get("download_url"),
    )
