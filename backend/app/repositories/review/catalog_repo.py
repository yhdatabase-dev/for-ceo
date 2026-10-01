"""WR 슬롯 카탈로그 리포지토리 — psycopg raw SQL.

원본 매핑
- Excel `취업규칙 마스터 db (2026).xlsx` + YAML `atomic_slots_v0.yaml` 이 시드됐다고 가정.
- 여기서는 PG check_item + 서브 테이블에서 조회.

document_type.code='work_rules' 기준.
"""
from __future__ import annotations

import re
from typing import Any, TypedDict

from app.core.logging import get_logger
from app.repositories.base import BaseRepo
from app.schemas.review.values import MasterValueVO, SlotDefVO

log = get_logger(__name__)


class ArticleMeta(TypedDict, total=False):
    """조 단위 메타데이터 (article_prefilter · optional_display · reporter 공용).

    필드는 optional_display.OptionalArticleSpec 과 호환 (super-set).
    """

    article: int
    title: str
    body: str
    guide: str
    note: str
    scope: str
    required: bool


class WrCatalogRepo(BaseRepo):
    def load_all(self) -> list[SlotDefVO]:
        """WR 슬롯 전체 로드.

        원본 SlotDef 는 조번호(article) · comparator · master_value · severity 등을 담음.
        v2 PG 는:
        - check_item.master_value (JSONB) 에 원본 slot YAML 의 master_value 구조를 그대로 저장
        - check_item_risk 에서 severity·fix_example 조회
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT ci.id, ci.code, ci.name, ci.comparator,
                       ci.extract_target, ci.master_value,
                       cir.missing_severity, cir.violation_severity, cir.fix_example
                  FROM cgr_master.check_item ci
                  JOIN cgr_master.document_type dt ON dt.id = ci.document_type_id
                  LEFT JOIN cgr_master.check_item_risk cir
                         ON cir.check_item_id = ci.id
                 WHERE dt.code = 'work_rules'
                 ORDER BY ci.display_order, ci.id
                """
            )
            rows = cur.fetchall()

        slots: list[SlotDefVO] = []
        for r in rows:
            master_val = r.get("master_value")
            slots.append(
                SlotDefVO(
                    slot_id=r["code"],
                    article=_extract_article(r["code"], master_val),
                    comparator=r.get("comparator") or "presence",
                    violation_severity=r.get("violation_severity"),
                    missing_severity=r.get("missing_severity"),
                    extract_target=r.get("extract_target"),
                    master_value=_build_master_value_vo(master_val),
                    fix_example=r.get("fix_example"),
                    # penalty · search_phrases · topic_meta 는 아래 헬퍼로 별도 조회 (TODO 최적화)
                )
            )
        return slots

    def load_articles_meta(self) -> list[ArticleMeta]:
        """WR 조 단위 메타데이터 (제목/본문/작성착안/참고/scope/필수여부).

        원본 `cgr/master_db.py` 의 xlsx 로더를 대체.
        v2 실제 DB 는 정부 표준용어사전 명명의 `ai.tb_empm_rul_master` +
        `ai.tb_empm_rul_ref` (참고사항) 조합에 같은 xlsx 데이터를 담아둠.

        원본 xlsx 컬럼 ↔ tb_empm_rul_master 컬럼 매핑:
          A 번호  → artcl_no       (VARCHAR)
          B 제목  → artcl_nm
          C 필수  → esntl_yn 'Y'/'N'  → scope 파생 ('필수'|'선택'), required (bool)
          D 본문  → empm_rul_cn
          E 착안  → cnsdr_cn
          F 참고  → tb_empm_rul_ref.ref_mttr (1:N 관계 — 첫 행만 표기)

        실패 시 빈 리스트 반환 (파이프라인은 우아하게 fallback).
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT m.artcl_no        AS article_no,
                           m.artcl_nm        AS title,
                           m.empm_rul_cn     AS body,
                           m.cnsdr_cn        AS guide,
                           (SELECT r.ref_mttr
                              FROM ai.tb_empm_rul_ref r
                             WHERE r.artcl_no = m.artcl_no
                             ORDER BY r.mng_sn
                             LIMIT 1)        AS note,
                           CASE WHEN m.esntl_yn = 'Y' THEN '필수' ELSE '선택' END AS scope,
                           (m.esntl_yn = 'Y') AS required
                      FROM ai.tb_empm_rul_master m
                     ORDER BY m.artcl_no::int
                    """
                )
                rows = cur.fetchall()
        except Exception as e:  # noqa: BLE001
            log.warning(
                "catalog.load_articles_meta 실패 — 빈 메타로 진행 (사전필터·선택조 SKIP): %s",
                e,
            )
            return []

        out: list[ArticleMeta] = []
        for r in rows:
            out.append(
                ArticleMeta(
                    article=int(r["article_no"]),
                    title=r.get("title") or "",
                    body=r.get("body") or "",
                    guide=r.get("guide") or "",
                    note=r.get("note") or "",
                    scope=r.get("scope") or "",
                    required=bool(r.get("required", True)),
                )
            )
        return out


# ─────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────
def _extract_article(code: str, master_value: dict | None) -> int:
    """슬롯 코드에서 조번호 추출.

    - master_value 에 article 이 있으면 우선
    - 아니면 코드에서 숫자 추출 (예: SLOT_WR_03_... → 3)
    """
    if isinstance(master_value, dict) and isinstance(master_value.get("article"), int):
        return master_value["article"]
    m = re.search(r"_(\d{1,3})", code)
    return int(m.group(1)) if m else 0


def _build_master_value_vo(mv: dict | None) -> MasterValueVO | None:
    """PG JSONB master_value → MasterValueVO."""
    if not mv or not isinstance(mv, dict):
        return None
    return MasterValueVO(
        op=mv.get("op", "presence"),
        value=mv.get("value"),
        keys=mv.get("keys", {}),
    )
