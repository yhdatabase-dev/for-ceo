"""근로계약서 항목 → 관련 주제 DB 섹션 lookup.

**우선순위**
  1. 마스터 SQLite DB (`mvp/data/master.db`) — check_item_topic 조인.
  2. (fallback) ANALYSIS_PROMPT 의 매핑 테이블 파싱 + topic_corpus.json
     — DB 가 없거나 비어있는 환경에서도 동작 보장.

마스터 DB 는 `mvp/scripts/seed_master_db.py` 가 채워둔다.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.ai.ec import prompts

_CORPUS_PATH = Path(__file__).resolve().parents[4] / "data" / "topic_corpus.json"

# 한 항목당 LLM 에 보낼 주제 섹션 최대 수 (token 폭주 방지)
MAX_SECTIONS_PER_ITEM = 4
# 한 섹션 본문 글자수 상한
MAX_BODY_CHARS = 600


@lru_cache(maxsize=1)
def _load_corpus() -> dict[str, dict[str, dict[str, str]]]:
    if not _CORPUS_PATH.exists():
        return {}
    try:
        return json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


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
    """본문(원문/풀이)이 있는 (주제명|섹션번호) 집합 — master.db 기준.

    빈 섹션(예: '임금 3.3' — body 둘 다 공란)을 참고자료에서 거르는 데 쓴다.
    DB 접근 실패 시 빈 집합 → 필터하지 않음(보수적)."""
    try:
        from app.repositories import base as _db

        with _db.connect() as c:
            rows = c.execute(
                "SELECT t.name, ts.section_no FROM topic_section ts "
                "JOIN topic t ON t.id = ts.topic_id "
                "WHERE COALESCE(ts.body_original,'') <> '' "
                "   OR COALESCE(ts.body_friendly,'') <> ''"
            ).fetchall()
        return frozenset(f"{r[0]}|{r[1]}" for r in rows)
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


# ─── 코퍼스 lookup ────────────────────────────────────────────────


def _topic_name_to_db_key(topic_name: str) -> str:
    """주제명 → 코퍼스 DB 키 (예: '근로시간' → 'DB_근로시간')."""
    return f"DB_{topic_name.strip()}"


def fetch_sections(
    refs: list[tuple[str, str]],
    *,
    max_sections: int = MAX_SECTIONS_PER_ITEM,
    max_chars: int = MAX_BODY_CHARS,
) -> list[dict[str, str]]:
    """주제·섹션 ref 리스트 → 코퍼스에서 본문 추출.

    body_friendly (paraphrased) 우선, 없으면 body (원문). 너무 길면 잘림.
    """
    corpus = _load_corpus()
    if not corpus:
        return []
    picked: list[dict[str, str]] = []
    seen: set[str] = set()
    for topic, section in refs[: max_sections * 2]:
        key = f"{topic}|{section}"
        if key in seen:
            continue
        seen.add(key)
        db_key = _topic_name_to_db_key(topic)
        sections = corpus.get(db_key)
        if not sections:
            # 코퍼스 키 변형 시도 — "휴일-휴일대체" 같은 하이픈 케이스
            for k in corpus.keys():
                if k.replace("DB_", "") == topic:
                    sections = corpus[k]
                    break
        if not sections:
            continue
        entry = sections.get(section)
        if not entry:
            continue
        body = entry.get("body_friendly") or entry.get("body") or ""
        if not body:
            continue
        picked.append(
            {
                "topic": topic,
                "section": section,
                "title": entry.get("title", ""),
                "body": body[:max_chars],
            }
        )
        if len(picked) >= max_sections:
            break
    return picked


def build_related_topics_block(item_name: str | None) -> str:
    """챗봇 user prompt 에 첨부할 관련 주제 블록.

    SQL DB 우선. 없거나 매핑 없으면 JSON fallback. 둘 다 비면 빈 문자열.
    """
    if not item_name:
        return ""
    sections = _fetch_via_sql(item_name)
    if not sections:
        # JSON fallback
        refs = topics_for_item(item_name)
        if refs:
            sections = fetch_sections(refs)
    if not sections:
        return ""
    lines: list[str] = [
        f"[「{item_name}」 관련 노무사회 자료 — 답변 시 적극 활용]",
    ]
    for s in sections:
        lines.append(
            f"\n• {s['topic']} §{s['section']}\n  {s['body']}".strip()
        )
    return "\n".join(lines)


def _fetch_via_sql(item_name: str) -> list[dict[str, str]]:
    """마스터 DB 의 check_item_topic 조인 — 한 항목의 관련 주제 섹션 본문.

    EC 문서 한정. body_friendly 우선, 없으면 body_original.
    """
    try:
        from app.repositories import base as _db
    except Exception:
        return []
    try:
        with _db.connect() as conn:
            cur = conn.execute(
                """
                SELECT t.name AS topic, ts.section_no AS section,
                       ts.title AS title,
                       COALESCE(NULLIF(ts.body_friendly, ''), ts.body_original) AS body
                FROM check_item ci
                JOIN document_type dt ON dt.id = ci.document_type_id
                JOIN check_item_topic cit ON cit.check_item_id = ci.id
                JOIN topic_section ts     ON ts.id = cit.topic_section_id
                JOIN topic t              ON t.id = ts.topic_id
                WHERE dt.code = 'employment_contract'
                  AND ci.name = ?
                  AND COALESCE(NULLIF(ts.body_friendly, ''),
                              NULLIF(ts.body_original, '')) IS NOT NULL
                ORDER BY cit.weight DESC, ts.section_no
                LIMIT ?
                """,
                (item_name, MAX_SECTIONS_PER_ITEM),
            )
            rows = cur.fetchall()
        out: list[dict[str, str]] = []
        for r in rows:
            body = (r["body"] or "")[:MAX_BODY_CHARS]
            if not body:
                continue
            out.append(
                {
                    "topic": r["topic"],
                    "section": r["section"],
                    "title": r["title"] or "",
                    "body": body,
                }
            )
        return out
    except Exception:
        # DB 없거나 쿼리 실패 — JSON fallback 으로 진행
        return []
