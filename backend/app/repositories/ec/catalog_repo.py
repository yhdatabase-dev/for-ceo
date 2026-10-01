"""EC 슬롯 카탈로그 리포지토리 — psycopg raw SQL.

원본 `cgr/ec/catalog.py:_load_from_sql` 이관.
검색 대상: cgr_master.check_item + 서브 테이블들 (WHERE document_type.code = 'employment_contract').
"""
from __future__ import annotations

from app.repositories.base import BaseRepo
from app.schemas.ec.values import EcCatalogVO, EcSlotVO


class EcCatalogRepo(BaseRepo):
    def load(self) -> EcCatalogVO:
        """EC 슬롯 카탈로그 전체 로드.

        1) check_item + risk + applicability 조회 (LEFT JOIN)
        2) 각 슬롯마다 laws / topic_meta 서브 조회 (N+1 이지만 마스터 데이터라 캐시로 우회 가능)
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT ci.id, ci.code, ci.name, ci.category,
                       ci.required_content, ci.purpose,
                       cir.missing_severity, cir.violation_severity, cir.fix_example,
                       cia.business_size, cia.worker_types, cia.written_duty
                  FROM cgr_master.check_item ci
                  JOIN cgr_master.document_type dt ON dt.id = ci.document_type_id
                  LEFT JOIN cgr_master.check_item_risk cir
                         ON cir.check_item_id = ci.id
                  LEFT JOIN cgr_master.check_item_applicability cia
                         ON cia.check_item_id = ci.id
                 WHERE dt.code = 'employment_contract'
                 ORDER BY ci.display_order, ci.id
                """
            )
            items = cur.fetchall()

        slots: list[EcSlotVO] = []
        for ci in items:
            slots.append(
                EcSlotVO(
                    slot_id=ci["code"],
                    field=ci["name"],
                    section=ci.get("category") or "",
                    required=True,
                    missing_severity=ci.get("missing_severity") or "MEDIUM",
                    violation_severity=ci.get("violation_severity") or "MEDIUM",
                    keywords=[],
                    required_content=ci.get("required_content") or "",
                    purpose=ci.get("purpose") or "",
                    fix_example=ci.get("fix_example") or "",
                    laws=self._fetch_laws(ci["id"]),
                    topic_meta=self._fetch_topic_meta(ci["id"]),
                    applicability={
                        "business_size": ci.get("business_size") or "any",
                        "worker_types": ci.get("worker_types") or [],
                        "written_duty": ci.get("written_duty") or "",
                    },
                )
            )
        return EcCatalogVO(slots=slots)

    def _fetch_laws(self, check_item_id: int) -> list[str]:
        """슬롯이 참조하는 법령 조문 라벨 목록."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT l.code, la.article_no, la.paragraph_no, la.item_no
                  FROM cgr_master.check_item_law cil
                  JOIN cgr_master.law_article la ON la.id = cil.law_article_id
                  JOIN cgr_master.law l          ON l.id  = la.law_id
                 WHERE cil.check_item_id = %s
                """,
                (check_item_id,),
            )
            rows = cur.fetchall()

        labels: list[str] = []
        for r in rows:
            parts = [r["code"], r["article_no"]]
            if r.get("paragraph_no"):
                parts.append(f"제{r['paragraph_no']}항")
            if r.get("item_no"):
                parts.append(f"제{r['item_no']}호")
            labels.append(" ".join(parts))
        return labels

    def _fetch_topic_meta(self, check_item_id: int) -> list[str]:
        """슬롯이 참조하는 주제:섹션 라벨 목록."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.name AS topic, ts.section_no AS section
                  FROM cgr_master.check_item_topic cit
                  JOIN cgr_master.topic_section ts ON ts.id = cit.topic_section_id
                  JOIN cgr_master.topic t          ON t.id  = ts.topic_id
                 WHERE cit.check_item_id = %s
                 ORDER BY cit.weight DESC
                """,
                (check_item_id,),
            )
            rows = cur.fetchall()
        return [f"{r['topic']}:{r['section']}" for r in rows]
