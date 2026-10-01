"""근로계약서 항목 → 관련 주제 DB 섹션 lookup — 원본 `cgr/ec/topic_lookup.py` v2 이관.

===============================================================================
원본 이관
===============================================================================
원본은 2-tier fallback:
  1) SQLite master.db (check_item_topic 조인) 우선
  2) ANALYSIS_PROMPT 매핑 테이블 파싱 + `data/topic_corpus.json` fallback

v2 는 외부 PG 로 통합됨 — JSON 코퍼스는 `cgr_master.topic_section` 으로 이관되었다고
가정하고 DB 조회만 유지. 매핑 테이블 파싱은 빈 매핑 대비 최소 fallback.

변경점
- `cgr.db.connect()` (SQLite) → `psycopg.Connection` (PG) 인자 주입
- `SELECT ... ? ...` (SQLite) → `%s` (psycopg)
- 스키마 접두사 `cgr_master.` 추가
- `topic_corpus.json` 파싱 제거 — 대체 코퍼스 없음
- 매핑 테이블 정규식·상수 (`_ITEM_ROW_RE`, `_TOPIC_REF_RE`, `MAX_SECTIONS_PER_ITEM`,
  `MAX_BODY_CHARS`) 원본 그대로

호출 주체
- `analyze_service._topics_for_item(field)` — `<meta>` 태그 교체용
- `prompt_builders.build_chat_user_prompt` — `focused_item` 관련 자료 첨부용
  (optional import 로 시도 → 실패 시 조용히 스킵)

호출 규약
- 이 모듈은 `psycopg.Connection` 이 필요하지만, 원본은 커넥션을 자체 해결.
  v2 에서 해당 호출부(`analyze_service` 등)가 `db` 를 인자로 넘겨줘야 함.
  안 넘어오면 DB 조회 함수들이 조용히 빈 리스트/문자열 반환.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.core.logging import get_logger

if TYPE_CHECKING:
    import psycopg

log = get_logger(__name__)

MAX_SECTIONS_PER_ITEM = 4
MAX_BODY_CHARS = 600


# ─────────────────────────────────────────────────────────────
# ANALYSIS_PROMPT 매핑 테이블 파서 (DB 조회 실패 시 fallback)
# ─────────────────────────────────────────────────────────────
_ITEM_ROW_RE = re.compile(
    r"^\|\s*([^|]+?)\s*\|"      # 항목
    r"[^|]*\|"                  # 기재내용
    r"[^|]*\|"                  # 서면명시의무
    r"\s*([^|]+?)\s*\|"         # 연관주제
    r"\s*([^|]+?)\s*\|"         # 관련법령
    r"\s*$",
    re.MULTILINE,
)
_TOPIC_REF_RE = re.compile(r"([가-힣\w·\-]+?)\s*(\d+(?:\.\d+)+)")


def parse_item_topics(analysis_prompt: str) -> dict[str, list[tuple[str, str]]]:
    """ANALYSIS_PROMPT 매핑 테이블 → {항목: [(주제명, 섹션번호), ...]}.

    원본 `_build_item_to_topics` 이관. 캐싱은 호출자가 담당 (v2 는 커넥션별
    사용 패턴이라 module-level lru_cache 는 부적합).
    """
    out: dict[str, list[tuple[str, str]]] = {}
    for m in _ITEM_ROW_RE.finditer(analysis_prompt or ""):
        item = m.group(1).strip()
        topics_cell = m.group(2).strip()
        if item in ("항목", "") or item.startswith("---"):
            continue
        refs: list[tuple[str, str]] = []
        for tm in _TOPIC_REF_RE.finditer(topics_cell):
            topic = tm.group(1).strip()
            section = tm.group(2).strip()
            if topic and section:
                refs.append((topic, section))
        if refs:
            existing = out.get(item, [])
            for ref in refs:
                if ref not in existing:
                    existing.append(ref)
            out[item] = existing
    return out


# ─────────────────────────────────────────────────────────────
# DB 조회 (PG · cgr_master 스키마)
# ─────────────────────────────────────────────────────────────
def topics_for_item(
    item_name: str, *, conn: "psycopg.Connection | None" = None
) -> list[tuple[str, str]]:
    """항목명 → [(주제명, 섹션번호), ...] · 본문 있는 섹션만.

    conn 미제공 시 빈 리스트 (호출자 optional 사용 대응).
    원본 `topics_for_item` + `_content_sections` 통합.
    """
    if not item_name or conn is None:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.name AS topic, ts.section_no AS section
                  FROM cgr_master.check_item ci
                  JOIN cgr_master.document_type dt ON dt.id = ci.document_type_id
                  JOIN cgr_master.check_item_topic cit ON cit.check_item_id = ci.id
                  JOIN cgr_master.topic_section ts     ON ts.id = cit.topic_section_id
                  JOIN cgr_master.topic t              ON t.id = ts.topic_id
                 WHERE dt.code = 'employment_contract'
                   AND ci.name = %s
                   AND COALESCE(NULLIF(ts.body_friendly, ''),
                                NULLIF(ts.body_original, '')) IS NOT NULL
                 ORDER BY cit.weight DESC, ts.section_no
                 LIMIT %s
                """,
                (item_name.strip(), MAX_SECTIONS_PER_ITEM),
            )
            rows = cur.fetchall()
        return [(r["topic"], r["section"]) for r in rows]
    except Exception as e:  # noqa: BLE001
        log.warning("ec.topics_for_item 조회 실패 (%s): %s", item_name, e)
        return []


def _fetch_sections(
    conn: "psycopg.Connection", item_name: str
) -> list[dict[str, str]]:
    """항목명 → 관련 섹션 본문 (title + body). DB 전용."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.name AS topic, ts.section_no AS section,
                       ts.title AS title,
                       COALESCE(NULLIF(ts.body_friendly, ''), ts.body_original) AS body
                  FROM cgr_master.check_item ci
                  JOIN cgr_master.document_type dt ON dt.id = ci.document_type_id
                  JOIN cgr_master.check_item_topic cit ON cit.check_item_id = ci.id
                  JOIN cgr_master.topic_section ts     ON ts.id = cit.topic_section_id
                  JOIN cgr_master.topic t              ON t.id = ts.topic_id
                 WHERE dt.code = 'employment_contract'
                   AND ci.name = %s
                   AND COALESCE(NULLIF(ts.body_friendly, ''),
                                NULLIF(ts.body_original, '')) IS NOT NULL
                 ORDER BY cit.weight DESC, ts.section_no
                 LIMIT %s
                """,
                (item_name.strip(), MAX_SECTIONS_PER_ITEM),
            )
            rows = cur.fetchall()
    except Exception as e:  # noqa: BLE001
        log.warning("ec.fetch_sections 조회 실패 (%s): %s", item_name, e)
        return []

    out: list[dict[str, str]] = []
    for r in rows:
        body = (r.get("body") or "")[:MAX_BODY_CHARS]
        if not body:
            continue
        out.append(
            {
                "topic": r["topic"],
                "section": r["section"],
                "title": r.get("title") or "",
                "body": body,
            }
        )
    return out


def build_related_topics_block(
    item_name: str | None,
    *,
    conn: "psycopg.Connection | None" = None,
) -> str:
    """챗봇 user prompt 에 첨부할 관련 주제 블록.

    conn 미제공 시 빈 문자열 (원본 JSON fallback 은 v2 미이관 — DB 로 통합).
    """
    if not item_name or conn is None:
        return ""
    sections = _fetch_sections(conn, item_name)
    if not sections:
        return ""
    lines: list[str] = [
        f"[「{item_name}」 관련 노무사회 자료 — 답변 시 적극 활용]",
    ]
    for s in sections:
        lines.append(f"\n• {s['topic']} §{s['section']}\n  {s['body']}".strip())
    return "\n".join(lines)
