"""근로계약서 항목 → 관련 주제 DB 섹션 lookup.

**우선순위**
  1. PostgreSQL — tb_chck_item_ref_tpc(점검항목_참조주제) 조인.
  2. (fallback) ANALYSIS_PROMPT 의 매핑 테이블 파싱
     — DB 가 없거나 비어있는 환경에서도 동작 보장.
"""
from __future__ import annotations

import re
from functools import lru_cache

from app.services.ec import prompts


# ─── 항목 → (주제명, 섹션번호) 리스트 매핑 빌더 ────────────────────────
_ITEM_ROW_RE = re.compile(
    # | 항목 | 기재내용 | 서면명시의무 | 연관주제 | 관련법령 |
    r"^\|\s*([^|]+?)\s*\|"  # 항목
    r"[^|]*\|"  # 기재내용
    r"[^|]*\|"  # 서면명시의무
    r"\s*([^|]+?)\s*\|"  # 연관주제
    r"\s*([^|]+?)\s*\|"  # 관련법령
    r"\s*$",
    re.MULTILINE,
)

# 연관주제 셀 안 "주제명 N.N.N" 패턴
_TOPIC_REF_RE = re.compile(r"([가-힣\w·\-]+?)\s*(\d+(?:\.\d+)+)")


@lru_cache(maxsize=1)
def _build_item_to_topics() -> dict[str, list[tuple[str, str]]]:
    """항목명 → [(주제명, 섹션번호), …] 매핑."""
    analysis_prompt = prompts.get_analysis_prompt()
    out: dict[str, list[tuple[str, str]]] = {}
    for m in _ITEM_ROW_RE.finditer(analysis_prompt):
        item = m.group(1).strip()
        topics_cell = m.group(2).strip()
        # 헤더 행 (| 항목 |) 또는 separator 행 (|---|) 건너뜀
        if item in ("항목", "") or item.startswith("---"):
            continue
        refs: list[tuple[str, str]] = []
        for tm in _TOPIC_REF_RE.finditer(topics_cell):
            topic = tm.group(1).strip()
            section = tm.group(2).strip()
            if topic and section:
                refs.append((topic, section))
        if refs:
            # 같은 항목명이 여러 카테고리(공통/5인이상/연소자 등)에 나오면 머지
            existing = out.get(item, [])
            for ref in refs:
                if ref not in existing:
                    existing.append(ref)
            out[item] = existing
    return out


@lru_cache(maxsize=1)
def _content_sections() -> frozenset[str]:
    """본문(원문/풀이)이 있는 (주제명|섹션번호) 집합 — DB(tb_tpc_mstr·tb_tpc_sctn) 기준.

    빈 섹션(예: '임금 3.3' — body 둘 다 공란)을 참고자료에서 거르는 데 쓴다.
    DB 접근 실패 시 빈 집합 → 필터하지 않음(보수적)."""
    try:
        from app.repositories import base as _db

        with _db.connect() as c:
            rows = c.execute(
                "SELECT t.tpc_nm AS name, ts.sctn_no AS section_no FROM ai.tb_tpc_sctn ts "
                "JOIN ai.tb_tpc_mstr t ON t.tpc_sn = ts.tpc_sn "
                "WHERE COALESCE(ts.mtxt_cn,'') <> '' "
                "   OR COALESCE(ts.frd_mtxt_cn,'') <> ''"
            ).fetchall()
        return frozenset(f"{r['name']}|{r['section_no']}" for r in rows)
    except Exception:
        return frozenset()


def topics_for_item(item_name: str) -> list[tuple[str, str]]:
    """항목명에 매핑된 (주제명, 섹션번호) 리스트. 본문 없는 섹션은 제외. 없으면 빈 리스트."""
    if not item_name:
        return []
    refs = _build_item_to_topics().get(item_name.strip(), [])
    have = _content_sections()
    if not have:
        return refs  # DB 접근 불가 시 거르지 않음
    return [(t, s) for (t, s) in refs if f"{t}|{s}" in have]
