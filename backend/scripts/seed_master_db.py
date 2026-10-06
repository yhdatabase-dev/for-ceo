"""기존 분산 자산을 통합 마스터 DB(SQLite)에 import.

원천 → 테이블:
  data/topic_corpus.json                   → topic / topic_section
  cgr/ec/prompts.py::ANALYSIS_PROMPT       → law / law_article / check_item_topic / check_item_law
  data/slots/atomic_slots_ec.yaml          → check_item / applicability / risk (EC 35개)
  data/slots/atomic_slots_v0.yaml          → check_item / applicability / risk (WR 115개)
  cgr/ec/prompts.py(33-매핑 행)            → check_item / category / check_item_topic / check_item_law

실행:
    cd mvp && python scripts/seed_master_db.py

옵션: `--drop-first` 면 기존 DB 비우고 새로.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

import master_sqlite as db  # noqa: E402
from app.services.ec import prompts  # noqa: E402

CORPUS_PATH = ROOT / "data" / "topic_corpus.json"
EC_SLOTS_PATH = ROOT / "data" / "slots" / "atomic_slots_ec.yaml"
WR_SLOTS_PATH = ROOT / "data" / "slots" / "atomic_slots_v0.yaml"


# ════════════════════════════════════════════════════════════════
# 1. document_type
# ════════════════════════════════════════════════════════════════
DOCUMENT_TYPES = [
    ("employment_contract", "근로계약서", 3),
    ("work_rules", "취업규칙", 5),
]


def seed_document_types(conn) -> dict[str, int]:
    """code → id."""
    out: dict[str, int] = {}
    for code, name, bucket_count in DOCUMENT_TYPES:
        cur = conn.execute(
            "INSERT OR REPLACE INTO document_type (code, name, bucket_count) "
            "VALUES (?, ?, ?) RETURNING id",
            (code, name, bucket_count),
        )
        out[code] = cur.fetchone()["id"]
    return out


# ════════════════════════════════════════════════════════════════
# 2. topic + topic_section (코퍼스)
# ════════════════════════════════════════════════════════════════
def seed_topics_and_sections(conn) -> dict[str, int]:
    """topic.code → id."""
    if not CORPUS_PATH.exists():
        raise FileNotFoundError(CORPUS_PATH)
    corpus: dict[str, dict[str, dict[str, str]]] = json.loads(
        CORPUS_PATH.read_text(encoding="utf-8")
    )
    topic_id_by_code: dict[str, int] = {}
    n_sections = 0
    for db_code, sections in corpus.items():
        name = db_code.replace("DB_", "")
        # 파일명에 데이터 표기 붙은 경우 (예: 임금대장-임금명세서_울_250730) 처리
        clean_name = name.split("_")[0]
        cur = conn.execute(
            "INSERT INTO topic (code, name, source) VALUES (?, ?, ?) "
            "ON CONFLICT(code) DO UPDATE SET name = excluded.name "
            "RETURNING id",
            (db_code, clean_name, "노무사회 obsidian 02_주제_노하우"),
        )
        topic_id = cur.fetchone()["id"]
        topic_id_by_code[db_code] = topic_id
        for sec_no, entry in sections.items():
            conn.execute(
                "INSERT OR REPLACE INTO topic_section "
                "(topic_id, section_no, title, body_original, body_friendly) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    topic_id,
                    sec_no,
                    entry.get("title", ""),
                    entry.get("body", ""),
                    entry.get("body_friendly"),
                ),
            )
            n_sections += 1
    print(f"  topics: {len(topic_id_by_code)}, sections: {n_sections}")
    return topic_id_by_code


# ════════════════════════════════════════════════════════════════
# 3. law + law_article (33-매핑의 관련법령 칼럼 + lawExcerpts 매핑)
# ════════════════════════════════════════════════════════════════
_LAW_ARTICLE_RE = re.compile(
    # 법령명 — "근로기준법", "근로기준법 시행령", "…보호등에관한법률"
    r"(.+?(?:법률|법|시행령|시행규칙))\s*"
    # 제N조 (+ 선택 "의M")
    r"제(\d+)조(?:의(\d+))?"
    # 선택 항·호
    r"(?:\s*제(\d+)항)?"
    r"(?:\s*제(\d+)호)?"
)


def parse_law_refs(cell: str) -> list[tuple[str, str, str, str]]:
    """관련법령 셀 → [(법령명, 제N조[의M], 제N항, 제N호), …] (항·호는 빈 문자열 가능).

    시행령·시행규칙도 별도 법령으로 추출 ("근로기준법 시행령" → law.code "근로기준법시행령").
    "제27조의2" 같은 분지 조항은 article 부분에 "의2" 가 붙어 보존.
    """
    if not cell:
        return []
    out: list[tuple[str, str, str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    # 콤마/슬래시로 분리
    for part in re.split(r"[,;／]\s*|\s+/\s+", cell):
        part = part.strip()
        if not part:
            continue
        m = _LAW_ARTICLE_RE.match(part)
        if m:
            law_nm = m.group(1).strip().replace(" ", "")
            article = f"제{m.group(2)}조"
            if m.group(3):
                article += f"의{m.group(3)}"
            paragraph = f"제{m.group(4)}항" if m.group(4) else ""
            item = f"제{m.group(5)}호" if m.group(5) else ""
            ref = (law_nm, article, paragraph, item)
            if ref not in seen:
                seen.add(ref)
                out.append(ref)
        else:
            # 법령명 only (예: "국민연금법", "외국인근로자의고용등에관한법률") — 조 없음
            if part.endswith(("법", "법률", "시행령", "시행규칙")):
                ref = (part.replace(" ", ""), "", "", "")
                if ref not in seen:
                    seen.add(ref)
                    out.append(ref)
    return out


def ensure_law(conn, code: str) -> int:
    cur = conn.execute(
        "INSERT INTO law (code, full_name, external_base) VALUES (?, ?, ?) "
        "ON CONFLICT(code) DO UPDATE SET code = excluded.code "
        "RETURNING id",
        (code, code, f"https://www.law.go.kr/법령/{code}"),
    )
    return cur.fetchone()["id"]


def ensure_law_article(
    conn,
    law_id: int,
    article: str,
    paragraph: str,
    item: str,
) -> int:
    # external_url 생성
    article_path = article
    if paragraph:
        article_path += " " + paragraph
    if item:
        article_path += " " + item
    # 법령명은 law 테이블에서
    cur = conn.execute("SELECT code FROM law WHERE id = ?", (law_id,))
    law_code = cur.fetchone()["code"]
    external_url = (
        f"https://www.law.go.kr/법령/{law_code}/{article}"
        if article
        else f"https://www.law.go.kr/법령/{law_code}"
    )
    cur = conn.execute(
        "INSERT INTO law_article (law_id, article_no, paragraph_no, item_no, external_url) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(law_id, article_no, paragraph_no, item_no) "
        "DO UPDATE SET external_url = excluded.external_url "
        "RETURNING id",
        (law_id, article, paragraph or None, item or None, external_url),
    )
    return cur.fetchone()["id"]


# ════════════════════════════════════════════════════════════════
# 4. check_item (slot yaml + 33-매핑 행)
# ════════════════════════════════════════════════════════════════
def seed_check_items_from_yaml(
    conn, doc_type_id: int, yaml_path: Path
) -> dict[str, int]:
    """슬롯 yaml → check_item / applicability / risk. code → id."""
    if not yaml_path.exists():
        print(f"  (skip) {yaml_path} not found")
        return {}
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    slots = data.get("slots", [])
    code_to_id: dict[str, int] = {}
    for order, slot in enumerate(slots):
        code = slot.get("slot_id") or slot.get("code")
        name = slot.get("field") or slot.get("name") or code
        applic = slot.get("applicability") or {}
        bs = applic.get("business_size") or "any"
        wts = applic.get("worker_types") or "any"
        if isinstance(wts, str):
            wts = [wts]
        cur = conn.execute(
            "INSERT INTO check_item "
            "(document_type_id, code, name, required_content, purpose, category, comparator, display_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(document_type_id, code) DO UPDATE SET name = excluded.name "
            "RETURNING id",
            (
                doc_type_id,
                code,
                name,
                slot.get("required_content") or "",
                slot.get("purpose") or "",
                None,  # category 는 33-매핑 패스에서 채움
                slot.get("comparator") or "presence",
                order,
            ),
        )
        item_id = cur.fetchone()["id"]
        code_to_id[code] = item_id
        # applicability
        conn.execute(
            "INSERT INTO check_item_applicability "
            "(check_item_id, business_size, worker_types) "
            "VALUES (?, ?, ?)",
            (item_id, bs, json.dumps(wts, ensure_ascii=False)),
        )
        # risk
        conn.execute(
            "INSERT OR REPLACE INTO check_item_risk "
            "(check_item_id, missing_severity, violation_severity, fix_example) "
            "VALUES (?, ?, ?, ?)",
            (
                item_id,
                slot.get("missing_severity"),
                slot.get("violation_severity"),
                slot.get("fix_example"),
            ),
        )
    print(f"  check_item from {yaml_path.name}: {len(code_to_id)}")
    return code_to_id


# ════════════════════════════════════════════════════════════════
# 4-b. YAML 의 topic_meta / laws 필드 → check_item_topic / check_item_law
#       (33-매핑 prose 가 없는 문서용 — 임금명세서가 대표 사례)
# ════════════════════════════════════════════════════════════════
def seed_topic_law_links_from_yaml_meta(
    conn,
    yaml_path: Path,
    code_to_id: dict[str, int],
    topic_id_by_code: dict[str, int],
) -> None:
    """슬롯 yaml 의 topic_meta + laws → 매핑 테이블.

    topic_meta 항목 예: "임금 3.4"
    laws 항목 예: "근로기준법 시행령 제27조의2 제3호"
    """
    if not yaml_path.exists():
        return
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    n_topic_links = 0
    n_law_links = 0
    for slot in data.get("slots", []) or []:
        code = slot.get("slot_id") or slot.get("code")
        check_item_id = code_to_id.get(code)
        if not check_item_id:
            continue
        # ─── topic_meta ───
        for ref in slot.get("topic_meta") or []:
            tm = _TOPIC_REF_RE.search(ref)
            if not tm:
                continue
            topic_name = tm.group(1).strip()
            sec_no = tm.group(2).strip()
            topic_code = f"DB_{topic_name}"
            topic_id = topic_id_by_code.get(topic_code)
            if not topic_id:
                cur = conn.execute(
                    "INSERT INTO topic (code, name, source) VALUES (?, ?, ?) "
                    "ON CONFLICT(code) DO UPDATE SET code = excluded.code "
                    "RETURNING id",
                    (topic_code, topic_name, "YAML topic_meta"),
                )
                topic_id = cur.fetchone()["id"]
                topic_id_by_code[topic_code] = topic_id
            cur = conn.execute(
                "INSERT INTO topic_section (topic_id, section_no, title) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(topic_id, section_no) "
                "DO UPDATE SET section_no = excluded.section_no RETURNING id",
                (topic_id, sec_no, ""),
            )
            sec_id = cur.fetchone()["id"]
            conn.execute(
                "INSERT OR IGNORE INTO check_item_topic "
                "(check_item_id, topic_section_id) VALUES (?, ?)",
                (check_item_id, sec_id),
            )
            n_topic_links += 1
        # ─── laws ───
        for ref in slot.get("laws") or []:
            for law_nm, article, paragraph, item in parse_law_refs(ref):
                law_id = ensure_law(conn, law_nm)
                article_id = ensure_law_article(
                    conn, law_id, article, paragraph, item
                )
                conn.execute(
                    "INSERT OR IGNORE INTO check_item_law "
                    "(check_item_id, law_article_id) VALUES (?, ?)",
                    (check_item_id, article_id),
                )
                n_law_links += 1
    print(
        f"  {yaml_path.name} meta links — topic: {n_topic_links}, law: {n_law_links}"
    )


# ════════════════════════════════════════════════════════════════
# 5. ANALYSIS_PROMPT 의 33-매핑 행 파싱 → check_item / topic / law 연결
# ════════════════════════════════════════════════════════════════
# 카테고리 헤더 — "### [공통 필수항목]", "### [5인 이상 사업장 추가항목]" 등
_CATEGORY_HEADER_RE = re.compile(r"^###\s*\[(.+?)\]")
# 매핑 행 — | 항목 | 기재내용 | 서면명시의무 | 연관주제 | 관련법령 |
_MAPPING_ROW_RE = re.compile(
    r"^\|\s*([^|]+?)\s*\|"  # 항목
    r"\s*([^|]+?)\s*\|"      # 기재내용
    r"\s*([^|]+?)\s*\|"      # 서면명시의무
    r"\s*([^|]+?)\s*\|"      # 연관주제
    r"\s*([^|]+?)\s*\|"      # 관련법령
    r"\s*$"
)
_TOPIC_REF_RE = re.compile(r"([가-힣\w·\-]+?)\s*(\d+(?:\.\d+)+)")

# 카테고리명 정규화 — yaml category 컬럼과 일관
_CATEGORY_NORM = {
    "공통 필수항목": "공통",
    "5인 이상 사업장 추가항목": "5인이상",
    "기간제 근로자 추가항목": "기간제",
    "단시간 근로자 추가항목": "단시간",
    "일용직 근로자 추가항목": "일용직",
    "연소자(18세 미만) 추가항목": "연소자",
    "외국인 근로자 추가항목": "외국인",
    "외국인(농축어업) 추가항목": "외국인-농축어업",
}


def seed_mapping_from_analysis_prompt(
    conn,
    doc_type_id_ec: int,
    ec_code_to_id: dict[str, int],
    topic_id_by_code: dict[str, int],
) -> None:
    """ANALYSIS_PROMPT 의 매핑 행 파싱 → check_item.category 갱신 + check_item_topic / check_item_law."""
    text = prompts.get_analysis_prompt()
    cur_category: str | None = None
    n_topic_links = 0
    n_law_links = 0
    for line in text.splitlines():
        m_cat = _CATEGORY_HEADER_RE.match(line.strip())
        if m_cat:
            raw = m_cat.group(1).strip()
            cur_category = _CATEGORY_NORM.get(raw, raw)
            continue
        m_row = _MAPPING_ROW_RE.match(line)
        if not m_row or not cur_category:
            continue
        item_name = m_row.group(1).strip()
        # 헤더 행·separator 행 skip
        if item_name in ("항목", "") or item_name.startswith("---"):
            continue
        # required_content 는 m_row.group(2) — 이미 yaml 에 있을 가능성, skip
        written_duty = m_row.group(3).strip()
        topic_cell = m_row.group(4).strip()
        law_cell = m_row.group(5).strip()

        # 항목 매칭 — yaml 의 EC 슬롯에서 name 으로 검색
        # 'name' 컬럼이 정확히 일치하는 행. 없으면 새로 생성.
        cur = conn.execute(
            "SELECT id FROM check_item WHERE document_type_id = ? AND name = ?",
            (doc_type_id_ec, item_name),
        )
        row = cur.fetchone()
        if row:
            check_item_id = row["id"]
        else:
            # 매핑 행에만 있고 슬롯엔 없는 항목 → 새로 추가
            cur = conn.execute(
                "INSERT INTO check_item "
                "(document_type_id, code, name, required_content, category) "
                "VALUES (?, ?, ?, ?, ?) RETURNING id",
                (
                    doc_type_id_ec,
                    f"SLOT_EC_{cur_category}_{item_name.replace(' ', '_')}",
                    item_name,
                    m_row.group(2).strip(),
                    cur_category,
                ),
            )
            check_item_id = cur.fetchone()["id"]

        # category 갱신 (yaml 에서는 비었음)
        conn.execute(
            "UPDATE check_item SET category = ? WHERE id = ?",
            (cur_category, check_item_id),
        )
        # written_duty → applicability 의 written_duty 컬럼
        conn.execute(
            "UPDATE check_item_applicability SET written_duty = ? "
            "WHERE check_item_id = ?",
            (written_duty, check_item_id),
        )

        # 주제 매핑
        for tm in _TOPIC_REF_RE.finditer(topic_cell):
            topic_name = tm.group(1).strip()
            sec_no = tm.group(2).strip()
            topic_code = f"DB_{topic_name}"
            topic_id = topic_id_by_code.get(topic_code)
            if not topic_id:
                # 코퍼스에 없는 주제 — 새로 추가 (참고용)
                cur = conn.execute(
                    "INSERT INTO topic (code, name, source) VALUES (?, ?, ?) "
                    "ON CONFLICT(code) DO UPDATE SET code = excluded.code "
                    "RETURNING id",
                    (topic_code, topic_name, "ANALYSIS_PROMPT 매핑에서 인용"),
                )
                topic_id = cur.fetchone()["id"]
                topic_id_by_code[topic_code] = topic_id
            # 섹션도 placeholder 로 추가 (코퍼스에 본문 없을 수 있음)
            cur = conn.execute(
                "INSERT INTO topic_section (topic_id, section_no, title) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(topic_id, section_no) DO UPDATE SET section_no = excluded.section_no "
                "RETURNING id",
                (topic_id, sec_no, ""),
            )
            sec_id = cur.fetchone()["id"]
            conn.execute(
                "INSERT OR IGNORE INTO check_item_topic "
                "(check_item_id, topic_section_id) VALUES (?, ?)",
                (check_item_id, sec_id),
            )
            n_topic_links += 1

        # 법령 매핑
        for law_nm, article, paragraph, item in parse_law_refs(law_cell):
            law_id = ensure_law(conn, law_nm)
            article_id = ensure_law_article(
                conn, law_id, article, paragraph, item
            )
            conn.execute(
                "INSERT OR IGNORE INTO check_item_law "
                "(check_item_id, law_article_id) VALUES (?, ?)",
                (check_item_id, article_id),
            )
            n_law_links += 1
    print(
        f"  mapping links — topic: {n_topic_links}, law: {n_law_links}"
    )


# ════════════════════════════════════════════════════════════════
# main
# ════════════════════════════════════════════════════════════════
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drop-first", action="store_true")
    args = parser.parse_args()

    print("[1/6] schema")
    db.init_schema(drop_first=args.drop_first)

    with db.connect() as conn:
        print("[2/6] document_type")
        doc_ids = seed_document_types(conn)
        print(f"  {doc_ids}")

        print("[3/6] topic + topic_section (corpus)")
        topic_id_by_code = seed_topics_and_sections(conn)

        print("[4/6] check_item from slot YAML")
        ec_codes = seed_check_items_from_yaml(
            conn, doc_ids["employment_contract"], EC_SLOTS_PATH
        )
        seed_check_items_from_yaml(
            conn, doc_ids["work_rules"], WR_SLOTS_PATH
        )

        print("[5/6] 33-mapping (category / topic / law links - EC)")
        seed_mapping_from_analysis_prompt(
            conn,
            doc_ids["employment_contract"],
            ec_codes,
            topic_id_by_code,
        )

        # 근로계약서 프롬프트가 v_minimum_wage_current 를 읽으므로 최저임금만 시드.
        # 임금명세서 전용(임금항목·위반유형·권고안)·노무제공자 슬롯은 제외.
        print("[6/6] minimum wage master")
        from scripts.seed_wage_masters import seed_minimum_wage

        n_mw = seed_minimum_wage(conn)
        print(f"  minimum_wage: {n_mw}")

    print()
    print("=== final counts ===")
    for t, n in db.table_counts().items():
        print(f"  {t}: {n}")


if __name__ == "__main__":
    main()
