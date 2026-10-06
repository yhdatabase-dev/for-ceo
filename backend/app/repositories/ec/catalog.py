"""근로계약서 슬롯 카탈로그 로더.

**우선순위**
  1. PostgreSQL — tb_chck_item_slot + apcbt(적용조건) + risk(위험도) 조인
  2. (fallback) `data/slots/atomic_slots_ec.yaml`

DB 에 있으면 그것을, 접속 실패·빈 결과면 yaml 을 그대로 사용.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class EcApplicability(BaseModel):
    """슬롯 적용 조건."""

    business_size: Literal["any", "5+", "5-"] = "any"
    worker_types: list[str] | Literal["any"] = "any"
    """'any' 면 모든 worker type 에 적용. 배열이면 해당 type 만."""


class EcSlot(BaseModel):
    """근로계약서 슬롯 — 필수 기재 항목 1건."""

    slot_id: str
    doc: Literal["employment_contract"]
    applicability: EcApplicability
    field: str
    """기재 항목명 (예: '사용자 정보', '임금', '근로개시일')."""

    required_content: str = ""
    """기재되어야 할 내용 (csv 기재내용)."""

    purpose: str = ""
    """기재 필요 이유 (csv 필요이유)."""

    topic_meta: list[str] = Field(default_factory=list)
    laws: list[str] = Field(default_factory=list)

    comparator: Literal["presence"] = "presence"
    """근로계약서는 모두 '기재 여부' 검증."""

    missing_severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    violation_severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    fix_example: str = ""

    def applies_to(self, business_size: str | None, worker_types: list[str]) -> bool:
        """사업장 컨텍스트에 이 슬롯이 적용되는지."""
        # business_size 검사
        bs = self.applicability.business_size
        if bs != "any":
            # 슬롯이 '5+' 요구인데 사용자가 '5-' 또는 None 이면 SKIP
            if bs == "5+" and business_size not in ("5+", None, "any"):
                # business_size 가 명시적으로 '5-' 면 skip
                if business_size == "5-":
                    return False
            if bs == "5-" and business_size == "5+":
                return False
        # worker_types 검사
        wt = self.applicability.worker_types
        if wt != "any":
            user_types = set(worker_types or ["정규직"])  # 빈 배열이면 정규직 가정
            slot_types = set(wt)
            if not (user_types & slot_types):
                return False
        return True


class EcCatalog(BaseModel):
    version: str
    doc: str
    description: str = ""
    slots: list[EcSlot]


_DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "slots" / "atomic_slots_ec.yaml"


@lru_cache(maxsize=4)
def load_ec_catalog(path: Path | None = None) -> EcCatalog:
    """근로계약서 슬롯 카탈로그 로드 (캐시).

    SQL DB 우선, 없으면 yaml fallback.
    """
    # 1) SQL 시도
    sql_catalog = _load_from_sql()
    if sql_catalog and sql_catalog.slots:
        return sql_catalog
    # 2) yaml fallback
    p = path or _DEFAULT_PATH
    if not p.exists():
        raise FileNotFoundError(f"EC catalog not found in DB or yaml: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    return EcCatalog(**raw)


def _load_from_sql() -> EcCatalog | None:
    """DB 에서 EC 슬롯 35개 + 적용조건 + 위험도를 한 번에 조회.

    DB 가 없거나 빈 결과면 None 반환 → 호출자가 yaml fallback.
    """
    try:
        from app.repositories import base as _db
    except Exception:
        return None
    try:
        with _db.connect() as conn:
            cur = conn.execute(
                """
                SELECT
                  ci.slot_id_nm AS code, ci.trgt_artcl_nm AS name,
                  ci.req_cn AS required_content, ci.req_prps_cn AS purpose,
                  ci.jgmt_cmpr_mth AS comparator, ci.indct_seq AS display_order,
                  cia.bplc_scl_cn AS business_size, cia.wrkr_type_cn AS worker_types,
                  cir.omsn_svrt AS missing_severity, cir.cn_impr_svrt AS violation_severity,
                  cir.crc_exm_cn AS fix_example
                FROM ai.tb_chck_item_slot ci
                JOIN ai.tb_doc_knd dt ON dt.doc_sn = ci.doc_sn
                LEFT JOIN ai.tb_chck_item_apcbt cia
                  ON cia.mng_sn = ci.mng_sn
                LEFT JOIN ai.tb_chck_item_risk cir
                  ON cir.mng_sn = ci.mng_sn
                WHERE dt.doc_eng_nm = 'employment_contract'
                ORDER BY ci.indct_seq, ci.mng_sn
                """
            )
            rows = cur.fetchall()
            if not rows:
                return None

            # 한 슬롯의 연관 주제·법령은 같은 connection 안에서 별도 join.
            # 본 fallback 단계에서는 EcSlot 의 topic_meta / laws 만 채워줌 (장식용).
            slots: list[EcSlot] = []
            for r in rows:
                # worker_types JSON → list 또는 "any"
                wt_raw = r["worker_types"]
                if wt_raw:
                    try:
                        wt_parsed = json.loads(wt_raw)
                    except Exception:
                        wt_parsed = ["any"]
                else:
                    wt_parsed = "any"
                # ["any"] / ["all"] / 빈 배열 → "any" 로 통일
                if isinstance(wt_parsed, list) and (
                    not wt_parsed or wt_parsed == ["any"]
                ):
                    wt_parsed = "any"

                bs = r["business_size"] or "any"
                if bs not in ("any", "5+", "5-"):
                    bs = "any"

                # 연관 주제·법령 — 동일 conn 으로 join
                topic_meta = _fetch_topic_meta(conn, r["code"])
                laws = _fetch_laws(conn, r["code"])

                missing_sev = r["missing_severity"] or "MEDIUM"
                violation_sev = r["violation_severity"] or "MEDIUM"
                # severity 유효성
                if missing_sev not in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
                    missing_sev = "MEDIUM"
                if violation_sev not in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
                    violation_sev = "MEDIUM"

                slots.append(
                    EcSlot(
                        slot_id=r["code"],
                        doc="employment_contract",
                        applicability=EcApplicability(
                            business_size=bs,  # type: ignore[arg-type]
                            worker_types=wt_parsed,
                        ),
                        field=r["name"],
                        required_content=r["required_content"] or "",
                        purpose=r["purpose"] or "",
                        topic_meta=topic_meta,
                        laws=laws,
                        comparator="presence",
                        missing_severity=missing_sev,  # type: ignore[arg-type]
                        violation_severity=violation_sev,  # type: ignore[arg-type]
                        fix_example=r["fix_example"] or "",
                    )
                )
        return EcCatalog(
            version="sql-v1",
            doc="employment_contract",
            description="loaded from PostgreSQL",
            slots=slots,
        )
    except Exception:
        return None


def _fetch_topic_meta(conn, slot_code: str) -> list[str]:
    """슬롯 code → ['주제명 N.N.N', …]."""
    cur = conn.execute(
        """
        SELECT t.tpc_nm AS topic, ts.sctn_no AS sec
        FROM ai.tb_chck_item_slot ci
        JOIN ai.tb_chck_item_ref_tpc cit ON cit.mng_sn = ci.mng_sn
        JOIN ai.tb_tpc_sctn ts           ON ts.sctn_sn = cit.sctn_sn
        JOIN ai.tb_tpc_mstr t            ON t.tpc_sn = ts.tpc_sn
        WHERE ci.slot_id_nm = %s
        ORDER BY t.tpc_nm, ts.sctn_no
        """,
        (slot_code,),
    )
    return [f"{r['topic']} {r['sec']}" for r in cur.fetchall()]


def _fetch_laws(conn, slot_code: str) -> list[str]:
    """슬롯 code → ['근로기준법 제17조 제1항 제1호', …]."""
    cur = conn.execute(
        """
        SELECT l.stt_cd_nm AS law, la.claus_no AS art,
               la.para_no AS para, la.subpara_no AS item
        FROM ai.tb_chck_item_slot ci
        JOIN ai.tb_chck_item_stt cil ON cil.mng_sn = ci.mng_sn
        JOIN ai.tb_stt_artcl la      ON la.lprvs_sn = cil.lprvs_sn
        JOIN ai.tb_stt_mstr l        ON l.stt_sn = la.stt_sn
        WHERE ci.slot_id_nm = %s
        ORDER BY l.stt_cd_nm, la.claus_no
        """,
        (slot_code,),
    )
    out: list[str] = []
    for r in cur.fetchall():
        parts = [r["law"]]
        if r["art"]:
            parts.append(r["art"])
        if r["para"]:
            parts.append(r["para"])
        if r["item"]:
            parts.append(r["item"])
        out.append(" ".join(parts))
    return out
