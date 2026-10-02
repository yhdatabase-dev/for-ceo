"""원자 슬롯 카탈로그 YAML 로더 + 마스터 DB enrichment."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from app.repositories.wr.master import MasterDB
from app.schemas.wr.values import Catalog, SlotDef


def load_catalog(yaml_path: str | Path) -> Catalog:
    p = Path(yaml_path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    return Catalog.model_validate(raw)


def slots_by_article(catalog: Catalog) -> dict[int, list]:
    """조 번호로 슬롯 그룹화."""
    out: dict[int, list] = {}
    for s in catalog.slots:
        out.setdefault(s.article, []).append(s)
    return out


def _split_topics(raw: str) -> list[str]:
    return [t.strip() for t in (raw or "").split("\n") if t.strip()]


def _split_penalty(raw: str) -> list[str]:
    """벌칙조항 문자열을 줄단위로 분리."""
    return [t.strip() for t in (raw or "").split("\n") if t.strip()]


def enrich_with_master_db(catalog: Catalog, db: MasterDB) -> Catalog:
    """슬롯 정의를 마스터 DB(xlsx) 데이터로 보강.

    - master_db_ref 의 빈 필드(D/F/N) 자동 채움
    - slot.topic_meta 비어있으면 H열에서 채움
    - slot.penalty 비어있으면 I열에서 채움 (조 단위 — 슬롯 단위 더 구체적이면 YAML 우선)
    YAML 우선순위 보존 — YAML 명시값은 덮어쓰지 않음.
    """
    for slot in catalog.slots:
        art = db.article(slot.article)
        if not art:
            continue

        # master_db_ref 보강 (YAML 미지정 시만)
        ref = dict(slot.master_db_ref or {})
        if not ref.get("D") and art.get("body"):
            ref["D"] = str(art["body"]).strip()
        if not ref.get("F") and art.get("note"):
            ref["F"] = str(art["note"]).strip()
        if not ref.get("N") and art.get("freq_issue"):
            ref["N"] = str(art["freq_issue"]).strip()
        if not ref.get("K") and art.get("amend_new"):
            ref["K"] = str(art["amend_new"]).strip()
        if not ref.get("L") and art.get("amend_old"):
            ref["L"] = str(art["amend_old"]).strip()
        slot.master_db_ref = ref

        # topic_meta — YAML 비어있으면 H열 사용
        if not slot.topic_meta:
            slot.topic_meta = _split_topics(str(art.get("topic") or ""))

        # penalty — YAML 비어있으면 I열 사용 (조 단위 일반 벌칙)
        if not slot.penalty:
            slot.penalty = _split_penalty(str(art.get("penalty") or ""))
    return catalog


@lru_cache(maxsize=4)
def _load_cached(yaml_path_str: str, mtime: float) -> Catalog:
    """yaml_path + mtime 으로 캐싱 — yaml 변경 감지 시 자동 무효화.

    Streamlit 세션이 살아있는 동안 catalog 1회만 파싱·enrich.
    """
    catalog = load_catalog(yaml_path_str)
    from app.repositories.wr.master import get_master_db

    db = get_master_db()
    return enrich_with_master_db(catalog, db)


def load_catalog_with_master_db(
    yaml_path: str | Path, db: MasterDB | None = None
) -> Catalog:
    """YAML 로드 + 마스터 DB 자동 enrich. mtime 기반 캐싱.

    db 명시 시 캐시 우회 (테스트용 분기).
    """
    if db is not None:
        catalog = load_catalog(yaml_path)
        return enrich_with_master_db(catalog, db)
    p = Path(yaml_path).resolve()
    mtime = p.stat().st_mtime if p.exists() else 0.0
    return _load_cached(str(p), mtime)
