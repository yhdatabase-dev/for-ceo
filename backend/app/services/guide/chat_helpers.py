"""guide 챗봇 헬퍼 4종.

===============================================================================
원본 이관
===============================================================================
원본: `cgr/api/routes/guide.py:{_search_guide_context, _detect_related_forms,
                                _extract_followups, _sanitize_sanctions}`

변경점
- SQLite `?` 플레이스홀더 → psycopg 3 `%s`
- `_query_all(sql, params)` → 파라미터로 `psycopg.Connection` 을 받아 직접 cursor 사용
- `RelatedFormHint` 는 v2 `app.schemas.guide.responses` 위치
- `_TOPIC_TO_FORMS`, `_FORM_INTENT_RE` 는 원본 그대로 이관
- 정규식·조사 보정·family clarify 문구는 100% 동일
"""
from __future__ import annotations

import re
from typing import Any

import psycopg

from app.core.logging import get_logger
from app.schemas.guide.responses import RelatedFormHint

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────
# 서식 매핑 테이블 (원본 그대로)
# ─────────────────────────────────────────────────────────────
# (regex, form_codes, family_or_None, is_doc_topic)
_TOPIC_TO_FORMS: list[tuple[str, list[str], str | None, bool]] = [
    (r"근로계약서|근로\s*계약", ["FRM001", "FRM002", "FRM003", "FRM004", "FRM005", "FRM030"], "근로계약서", True),
    (r"취업규칙", ["FRM029", "FRM033"], None, True),
    (r"임금명세서|임금\s*명세|임금대장", ["FRM031", "FRM032"], None, True),
    (r"4\s*대\s*보험|사회보험|국민연금|건강보험|고용보험|산재보험", ["FRM006", "FRM007", "FRM008"], None, False),
    (r"출산전후휴가|출산\s*휴가", ["FRM009"], None, False),
    (r"육아휴직|육아\s*휴직", ["FRM010", "FRM011"], None, False),
    (r"육아기\s*근로시간\s*단축", ["FRM012"], None, False),
    (r"배우자\s*출산", ["FRM013"], None, False),
    (r"고용안정장려금|출산육아기\s*고용안정", ["FRM014"], None, False),
    (r"실업급여|수급자격", ["FRM015", "FRM017"], None, False),
    (r"이직확인서|이직\s*확인", ["FRM016"], None, True),
    (r"퇴직금|퇴직\s*급여", ["FRM018"], None, False),
    (r"퇴직연금|db\s*형|dc\s*형|확정급여형|확정기여형", ["FRM019", "FRM034"], "퇴직연금", False),
    (r"산재|업무상\s*재해|요양급여|휴업급여|장해급여", ["FRM025", "FRM026", "FRM027", "FRM028"], "산재", False),
    (r"외국인", ["FRM030"], None, False),
]

_FORM_INTENT_RE = (
    r"서식|양식|신청|신고|확인서|증명서|규약|서류|"
    r"작성|제출|다운로드|받고\s*싶|받을\s*수|받아\s*보|어디서\s*받"
)


# ─────────────────────────────────────────────────────────────
# 1. 관련 서식 감지
# ─────────────────────────────────────────────────────────────
def detect_related_forms(
    conn: psycopg.Connection,
    question: str,
    answer: str,
) -> tuple[list[RelatedFormHint], str | None]:
    """질문 텍스트를 스캔해 관련 서식 코드를 수집.

    답변 텍스트는 보지 않는다 — 노무 답변에는 '근로계약'·'고용보험' 같은
    주제어가 거의 항상 등장하기 때문. 문서 이름 주제(doc_topic)는 질문 등장만으로,
    제도 주제는 질문에 서식·신청 intent 가 함께 있을 때만 노출.

    같은 family 안에서 2개 이상 매칭되면 clarify 질문 생성.
    """
    del answer  # 의도적 미사용
    text = question.lower().replace(" ", "")
    intent_re = _FORM_INTENT_RE.replace(r"\s*", "")
    has_intent = bool(re.search(intent_re, text))

    matched_codes: list[str] = []
    for pat, codes, _family, doc_topic in _TOPIC_TO_FORMS:
        if not re.search(pat.replace(r"\s*", ""), text):
            continue
        if not (doc_topic or has_intent):
            continue
        for c in codes:
            if c not in matched_codes:
                matched_codes.append(c)

    if not matched_codes:
        return [], None

    # form_template 조회 — 사업주(employer) 또는 both 만
    placeholders = ",".join(["%s"] * len(matched_codes))
    sql = f"""
        SELECT code, form_name, category, audience, purpose,
               local_filename, download_url
          FROM cgr_master.form_template
         WHERE code IN ({placeholders})
           AND audience IN ('employer', 'both')
         ORDER BY code
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(matched_codes))
            rows = cur.fetchall()
    except Exception as e:  # noqa: BLE001
        log.warning("guide.detect_related_forms 조회 실패: %s", e)
        return [], None

    hints: list[RelatedFormHint] = []
    for r in rows:
        hints.append(
            RelatedFormHint(
                code=r["code"],
                form_name=r["form_name"],
                category=r["category"],
                audience=r["audience"],
                has_local=bool(r.get("local_filename")),
                purpose=(r.get("purpose") or "")[:100],
            )
        )

    # family clarify — 같은 family 2개 이상이면 사용자 재확인 요청
    clarify: str | None = None
    family_counts: dict[str, int] = {}
    for h in hints:
        for _pat, codes, family, _doc_topic in _TOPIC_TO_FORMS:
            if family and h.code in codes:
                family_counts[family] = family_counts.get(family, 0) + 1
    for family, cnt in family_counts.items():
        if cnt >= 2:
            if family == "근로계약서":
                clarify = "근로계약서는 근로자 유형별로 양식이 달라요. 어떤 유형인가요? 아래 버튼에서 골라 받으세요."
            elif family == "퇴직연금":
                clarify = "퇴직연금은 제도 유형(DB형/DC형)에 따라 표준규약이 달라요. 운영하시는 제도 기준으로 골라 받으세요."
            elif family == "산재":
                clarify = "산재 관련 서식은 신청 단계별로 양식이 달라요. 필요한 단계의 서식을 골라 받으세요."
            break

    return hints, clarify


# ─────────────────────────────────────────────────────────────
# 2. RAG 컨텍스트 조립
# ─────────────────────────────────────────────────────────────
_PARTICLES = set("은는이가을를에의도만과와로서시께란")
_MULTI_PARTICLES = ("에서", "으로", "에게", "이나", "라고", "부터", "까지")


def search_guide_context(
    conn: psycopg.Connection,
    query: str,
    *,
    per_table: int = 4,
) -> tuple[str, list[str]]:
    """가이드 DB LIKE 검색 → LLM 컨텍스트 텍스트 + 사용된 카테고리.

    각 테이블에서 상위 N건만 추려 토큰 절약. 원본 로직 그대로 이관하되
    - `?` → `%s` (psycopg)
    - 테이블 스키마 접두사 `cgr_master.` 추가
    """
    if not query:
        return "", []

    # 한국어 키워드 추출 — split + 2자 이상
    tokens = [
        t.strip() for t in query.replace("?", " ").split() if len(t.strip()) >= 2
    ]
    # 조사 변형 보정
    extra: list[str] = []
    for t in tokens:
        if len(t) >= 3 and t[-1] in _PARTICLES:
            extra.append(t[:-1])
        if len(t) >= 4 and t[-2:] in _MULTI_PARTICLES:
            extra.append(t[:-2])
    tokens = list(dict.fromkeys([*tokens, *extra]))
    if not tokens:
        return "", []

    sources: list[str] = []
    blocks: list[str] = []

    def _like_search(
        sql_select: str,
        text_cols: list[str],
        max_n: int = per_table,
    ) -> list[dict[str, Any]]:
        if not text_cols:
            return []
        like_clauses: list[str] = []
        params: list[Any] = []
        for tk in tokens:
            for col in text_cols:
                like_clauses.append(f"{col} LIKE %s")
                params.append(f"%{tk}%")
        where = " OR ".join(like_clauses)
        joiner = "AND" if " where " in sql_select.lower() else "WHERE"
        full_sql = f"{sql_select} {joiner} ({where}) LIMIT {max_n}"
        try:
            with conn.cursor() as cur:
                cur.execute(full_sql, tuple(params))
                return list(cur.fetchall())
        except Exception as e:  # noqa: BLE001
            log.warning("guide.search LIKE 실패 (%s): %s", full_sql[:80], e)
            return []

    # 1) 시기별 의무
    rows = _like_search(
        "SELECT stage, duty, description, deadline, legal_basis "
        "FROM cgr_master.obligation_timeline WHERE excluded_from_service = FALSE ",
        ["stage", "duty", "description", "legal_basis"],
    )
    if rows:
        sources.append("시기별 의무")
        lines = ["[시기별 의무]"]
        for r in rows:
            lines.append(
                f"- [{r['stage']}] {r['duty']}: {r.get('description', '')} "
                f"(근거 {r.get('legal_basis', '')}, 기한 {r.get('deadline', '')})"
            )
        blocks.append("\n".join(lines))

    # 2) 사업장 규모별 의무
    rows = _like_search(
        "SELECT min_size, duty, description, legal_basis "
        "FROM cgr_master.size_threshold_duty ",
        ["min_size", "duty", "description", "legal_basis"],
    )
    if rows:
        sources.append("규모별 의무")
        lines = ["[사업장 규모별 의무]"]
        for r in rows:
            lines.append(
                f"- [{r['min_size']}] {r['duty']}: {r.get('description', '')} "
                f"(근거 {r.get('legal_basis', '')})"
            )
        blocks.append("\n".join(lines))

    # 3) 용어 사전
    rows = _like_search(
        "SELECT term, short_def, full_def, confusable_with, legal_basis "
        "FROM cgr_master.guide_glossary ",
        ["term", "short_def", "full_def", "confusable_with"],
    )
    if rows:
        sources.append("용어 사전")
        lines = ["[용어 사전]"]
        for r in rows:
            extra_str = (
                f" 혼동: {r['confusable_with']}" if r.get("confusable_with") else ""
            )
            lines.append(
                f"- {r['term']}: {r.get('short_def', '')}. "
                f"{(r.get('full_def') or '')[:200]}{extra_str}"
            )
        blocks.append("\n".join(lines))

    # 4) 정부 기관
    rows = _like_search(
        "SELECT org_name, org_class, duties, common_cases, phone, online_channel "
        "FROM cgr_master.gov_org WHERE excluded_from_service = FALSE ",
        ["org_name", "duties", "common_cases", "org_class"],
    )
    if rows:
        sources.append("정부 기관")
        lines = ["[정부 기관·온라인 채널]"]
        for r in rows:
            ch = r.get("online_channel") or r.get("phone") or ""
            lines.append(
                f"- {r['org_name']} ({r['org_class']}): {r.get('duties', '')} · {ch}"
            )
        blocks.append("\n".join(lines))

    # 5) 비치 서류
    rows = _like_search(
        "SELECT doc_name, classification, description, retention_period, legal_basis "
        "FROM cgr_master.required_document ",
        ["doc_name", "description", "classification", "legal_basis"],
    )
    if rows:
        sources.append("비치 서류")
        lines = ["[비치·보존 서류]"]
        for r in rows:
            lines.append(
                f"- {r['doc_name']} ({r['classification']}): {r.get('description', '')} "
                f"보존 {r.get('retention_period', '')} (근거 {r.get('legal_basis', '')})"
            )
        blocks.append("\n".join(lines))

    # 6) 고용 생애주기
    rows = _like_search(
        "SELECT phase, sub_topic, requirement, related_docs, legal_basis "
        "FROM cgr_master.employment_lifecycle ",
        ["phase", "sub_topic", "requirement", "legal_basis"],
    )
    if rows:
        sources.append("고용 생애주기")
        lines = ["[고용 생애주기]"]
        for r in rows:
            lines.append(
                f"- [{r['phase']} / {r['sub_topic']}] {r['requirement']} "
                f"(서류 {r.get('related_docs', '')}, 근거 {r.get('legal_basis', '')})"
            )
        blocks.append("\n".join(lines))

    # 7) 채용 컴플라이언스
    rows = _like_search(
        "SELECT stage, duty, description, violation_examples, penalty, legal_basis "
        "FROM cgr_master.recruit_compliance ",
        ["stage", "duty", "description", "violation_examples"],
    )
    if rows:
        sources.append("채용 컴플라이언스")
        lines = ["[채용 단계 준수사항]"]
        for r in rows:
            lines.append(
                f"- [{r['stage']}] {r['duty']}: {r.get('description', '')} "
                f"위반사례 {r.get('violation_examples', '')} (벌칙 {r.get('penalty', '')})"
            )
        blocks.append("\n".join(lines))

    # 8) 가이드 FAQ
    rows = _like_search(
        "SELECT category, title, key_points, related_laws, note "
        "FROM cgr_master.guide_item WHERE excluded_from_service = FALSE ",
        ["category", "title", "key_points", "note"],
    )
    if rows:
        sources.append("가이드 FAQ")
        lines = ["[가이드 FAQ]"]
        for r in rows:
            lines.append(
                f"- [{r['category']}] {r['title']}: "
                f"{(r.get('key_points') or '')[:400]} "
                f"(근거 {r.get('related_laws', '')})"
            )
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks), sources


# ─────────────────────────────────────────────────────────────
# 3. 후속 추천 질문 추출
# ─────────────────────────────────────────────────────────────
_FOLLOWUP_BLOCK_RE = re.compile(
    r"\[추천질문\]\s*\n((?:\s*[-·●]\s*[^\n]+\n?)+)",
    flags=re.MULTILINE,
)


def extract_followups(answer: str) -> tuple[str, list[str]]:
    """LLM 응답에서 [추천질문] 블록 분리 — 본문은 그 라인 제거 후 반환.

    반환: (본문, [질문1, 질문2, 질문3])  — 최대 3개
    """
    m = _FOLLOWUP_BLOCK_RE.search(answer)
    if not m:
        return answer.strip(), []
    block = m.group(1)
    lines = [
        ln.strip().lstrip("-·● ").strip()
        for ln in block.split("\n")
        if ln.strip()
    ]
    items = [ln for ln in lines if len(ln) >= 4][:3]
    body = answer[: m.start()].rstrip()
    return body, items


# ─────────────────────────────────────────────────────────────
# 4. 제재 표현 정제
# ─────────────────────────────────────────────────────────────
def sanitize_sanctions(text: str) -> str:
    """'전과', '벌금=형사처벌(전과)' 같은 낙인적 표현 결정적 정제.

    LLM 준수에 의존하지 않도록 (a) 가이드 DB 컨텍스트, (b) 최종 답변 양쪽에
    적용. (같은 입력 → 같은 출력)
    """
    if not text:
        return text
    s = text
    for a, b in (
        ("벌금=형사처벌(전과)", "과태료·벌금 등 행정·형사 제재"),
        ("벌금 = 형사처벌(전과)", "과태료·벌금 등 행정·형사 제재"),
        ("형사처벌(전과)", "형사 제재"),
        ("벌금=형사처벌", "벌금 등 형사 제재"),
        ("벌금 = 형사처벌", "벌금 등 형사 제재"),
    ):
        s = s.replace(a, b)
    s = re.sub(r"\s*\(\s*전과[^)]*\)", "", s)
    s = re.sub(r"전과(가|는|을|를|로|기록)?", "", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"\s+([,.)])", r"\1", s)
    return s.strip()
