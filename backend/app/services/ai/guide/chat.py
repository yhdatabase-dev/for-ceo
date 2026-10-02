"""노무 가이드 챗봇 — 컨텍스트 검색·관련 서식 탐지·응답 후처리."""
from __future__ import annotations

from typing import Any

from app.repositories.guide.content import _query_all
from app.schemas.guide.chat import RelatedFormHint

# ────────────────────────────────────────────────────────────
# 주제 → 서식 코드 매핑.
# 키는 정규식 (한국어 lowercase 비교). 값은 (form_codes, family_label, doc_topic)
# family_label 이 있으면 같은 family 안에서 여러 형이 매칭될 때 clarify 질문 생성.
# doc_topic=True 는 주제 자체가 '문서 이름'(근로계약서 등) — 질문에 등장하면
# 그 자체로 서식 수요로 본다. False 는 제도·급여 주제 — 질문에 서식·신청
# intent 가 함께 있을 때만 서식 chip 을 노출한다.
# ────────────────────────────────────────────────────────────
_TOPIC_TO_FORMS: list[tuple[str, list[str], str | None, bool]] = [
    # 근로계약서 family — 5종 변형 (정규/기간제/단시간/연소/건설일용) + 외국인
    (r"근로계약서|근로\s*계약", ["FRM001", "FRM002", "FRM003", "FRM004", "FRM005", "FRM030"], "근로계약서", True),
    # 취업규칙
    (r"취업규칙", ["FRM029", "FRM033"], None, True),
    # 임금명세서·임금대장
    (r"임금명세서|임금\s*명세|임금대장", ["FRM031", "FRM032"], None, True),
    # 4대보험
    (r"4\s*대\s*보험|사회보험|국민연금|건강보험|고용보험|산재보험", ["FRM006", "FRM007", "FRM008"], None, False),
    # 출산·육아·배우자 출산휴가
    (r"출산전후휴가|출산\s*휴가", ["FRM009"], None, False),
    (r"육아휴직|육아\s*휴직", ["FRM010", "FRM011"], None, False),
    (r"육아기\s*근로시간\s*단축", ["FRM012"], None, False),
    (r"배우자\s*출산", ["FRM013"], None, False),
    (r"고용안정장려금|출산육아기\s*고용안정", ["FRM014"], None, False),
    # 실업급여·이직
    (r"실업급여|수급자격", ["FRM015", "FRM017"], None, False),
    (r"이직확인서|이직\s*확인", ["FRM016"], None, True),
    # 퇴직금·퇴직연금
    (r"퇴직금|퇴직\s*급여", ["FRM018"], None, False),
    (r"퇴직연금|db\s*형|dc\s*형|확정급여형|확정기여형", ["FRM019", "FRM034"], "퇴직연금", False),
    # 산재
    (r"산재|업무상\s*재해|요양급여|휴업급여|장해급여", ["FRM025", "FRM026", "FRM027", "FRM028"], "산재", False),
    # 외국인
    (r"외국인", ["FRM030"], None, False),
]

# 질문에서 '서식이 필요하다'는 의도를 나타내는 표현 — 제도 주제(doc_topic=False)는
# 이 intent 가 질문에 함께 있을 때만 서식 chip 노출.
_FORM_INTENT_RE = (
    r"서식|양식|신청|신고|확인서|증명서|규약|서류|"
    r"작성|제출|다운로드|받고\s*싶|받을\s*수|받아\s*보|어디서\s*받"
)

def _detect_related_forms(question: str, answer: str) -> tuple[list[RelatedFormHint], str | None]:
    """질문 텍스트를 스캔해 관련 서식 코드를 수집.

    답변 텍스트는 보지 않는다 — 노무 답변에는 '근로계약'·'고용보험' 같은 주제어가
    거의 항상 등장해, 답변까지 스캔하면 사실상 모든 질문에 서식이 떴다.
    문서 이름 주제(doc_topic)는 질문 등장만으로, 제도 주제는 질문에 서식·신청
    intent 가 함께 있을 때만 노출한다.

    같은 family 안에서 2개 이상 매칭되면 clarify 질문 생성.
    """
    import re as _re

    del answer  # 의도적으로 미사용 — docstring 참조
    text = question.lower().replace(" ", "")
    has_intent = bool(_re.search(_FORM_INTENT_RE.replace(r"\s*", ""), text))
    matched_codes: list[str] = []
    matched_families: set[str] = set()
    for pat, codes, family, doc_topic in _TOPIC_TO_FORMS:
        # 패턴은 공백 제거된 텍스트에 매칭하기 위해 \s* 제거
        if not _re.search(pat.replace(r"\s*", ""), text):
            continue
        if not (doc_topic or has_intent):
            continue
        for c in codes:
            if c not in matched_codes:
                matched_codes.append(c)
        if family:
            matched_families.add(family)

    if not matched_codes:
        return [], None

    # 매칭된 코드로 form_template 조회 — 사업주(employer) 또는 both 만
    placeholders = ",".join(["?"] * len(matched_codes))
    rows = _query_all(
        f"SELECT code, form_name, category, audience, purpose, local_filename, download_url "
        f"FROM form_template "
        f"WHERE code IN ({placeholders}) AND audience IN ('employer', 'both') "
        f"ORDER BY code",
        tuple(matched_codes),
    )
    hints: list[RelatedFormHint] = []
    for r in rows:
        hints.append(RelatedFormHint(
            code=r["code"],
            form_name=r["form_name"],
            category=r["category"],
            audience=r["audience"],
            has_local=bool(r.get("local_filename")),
            purpose=(r.get("purpose") or "")[:100],
        ))

    # clarify: 같은 family 에서 2개 이상 매칭된 경우 사용자에게 한 번 더 묻기
    clarify: str | None = None
    family_counts: dict[str, int] = {}
    for h in hints:
        for pat, codes, family, _doc_topic in _TOPIC_TO_FORMS:
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

def _search_guide_context(query: str, *, per_table: int = 4) -> tuple[str, list[str]]:
    """사용자 질문 키워드로 가이드 DB 검색 → LLM 컨텍스트 텍스트 + 사용된 카테고리.

    각 테이블에서 LIKE 검색으로 상위 N건만 추려 토큰 절약.
    """
    if not query:
        return "", []
    # 한국어 키워드 추출 — 단순 split + 2자 이상
    tokens = [t.strip() for t in query.replace('?', ' ').split() if len(t.strip()) >= 2]
    # 조사 변형 보정 — "근로감독시"·"감독시" 처럼 끝에 조사가 붙으면 LIKE 매칭이
    # 안 돼 검색을 놓친다. 끝 1글자가 흔한 조사면 떼어낸 형태도 검색어에 추가.
    _PARTICLES = set("은는이가을를에의도만과와로서시께란")
    _extra: list[str] = []
    for t in tokens:
        if len(t) >= 3 and t[-1] in _PARTICLES:
            _extra.append(t[:-1])
        if len(t) >= 4 and t[-2:] in ("에서", "으로", "에게", "이나", "라고", "부터", "까지"):
            _extra.append(t[:-2])
    tokens = list(dict.fromkeys([*tokens, *_extra]))  # 순서 유지 dedupe
    if not tokens:
        return "", []
    sources: list[str] = []
    blocks: list[str] = []

    def _like_search(sql_select: str, text_cols: list[str], label: str, max_n: int = per_table):
        """주어진 SELECT 에 LIKE 조건 추가해 매칭 행 반환."""
        if not text_cols:
            return []
        # 모든 토큰을 OR 로 — 어느 컬럼이든 어느 토큰이든 매칭되면 hit
        like_clauses = []
        params: list[Any] = []
        for tk in tokens:
            for col in text_cols:
                like_clauses.append(f"{col} LIKE ?")
                params.append(f"%{tk}%")
        where = " OR ".join(like_clauses)
        # sql_select 에 이미 WHERE 가 있으면 AND 로 이어붙임 — 'WHERE … WHERE …'
        # SQL 오류로 해당 테이블 검색이 조용히 빈 결과가 되던 버그 수정.
        joiner = "AND" if " where " in sql_select.lower() else "WHERE"
        full_sql = f"{sql_select} {joiner} ({where}) LIMIT {max_n}"
        try:
            return _query_all(full_sql, tuple(params))
        except Exception:
            return []

    # 1) 시기별 의무
    rows = _like_search(
        "SELECT stage, duty, description, deadline, legal_basis "
        "FROM obligation_timeline WHERE excluded_from_service = 0 ",
        ["stage", "duty", "description", "legal_basis"],
        "obligation",
    )
    if rows:
        sources.append("시기별 의무")
        lines = ["[시기별 의무]"]
        for r in rows:
            lines.append(
                f"- [{r['stage']}] {r['duty']}: {r.get('description','')} "
                f"(근거 {r.get('legal_basis','')}, 기한 {r.get('deadline','')})"
            )
        blocks.append("\n".join(lines))

    # 2) 사업장 규모별 의무
    rows = _like_search(
        "SELECT min_size, duty, description, legal_basis "
        "FROM size_threshold_duty ",
        ["min_size", "duty", "description", "legal_basis"],
        "size",
    )
    if rows:
        sources.append("규모별 의무")
        lines = ["[사업장 규모별 의무]"]
        for r in rows:
            lines.append(
                f"- [{r['min_size']}] {r['duty']}: {r.get('description','')} "
                f"(근거 {r.get('legal_basis','')})"
            )
        blocks.append("\n".join(lines))

    # 3) 용어 사전
    rows = _like_search(
        "SELECT term, short_def, full_def, confusable_with, legal_basis "
        "FROM guide_glossary ",
        ["term", "short_def", "full_def", "confusable_with"],
        "glossary",
    )
    if rows:
        sources.append("용어 사전")
        lines = ["[용어 사전]"]
        for r in rows:
            extra = f" 혼동: {r['confusable_with']}" if r.get("confusable_with") else ""
            lines.append(
                f"- {r['term']}: {r.get('short_def','')}. {r.get('full_def','')[:200]}{extra}"
            )
        blocks.append("\n".join(lines))

    # 4) 기관
    rows = _like_search(
        "SELECT org_name, org_class, duties, common_cases, phone, online_channel "
        "FROM gov_org WHERE excluded_from_service = 0 ",
        ["org_name", "duties", "common_cases", "org_class"],
        "org",
    )
    if rows:
        sources.append("정부 기관")
        lines = ["[정부 기관·온라인 채널]"]
        for r in rows:
            ch = r.get("online_channel") or r.get("phone") or ""
            lines.append(f"- {r['org_name']} ({r['org_class']}): {r.get('duties','')} · {ch}")
        blocks.append("\n".join(lines))

    # 5) 비치 서류
    rows = _like_search(
        "SELECT doc_name, classification, description, retention_period, legal_basis "
        "FROM required_document ",
        ["doc_name", "description", "classification", "legal_basis"],
        "doc",
    )
    if rows:
        sources.append("비치 서류")
        lines = ["[비치·보존 서류]"]
        for r in rows:
            lines.append(
                f"- {r['doc_name']} ({r['classification']}): {r.get('description','')} "
                f"보존 {r.get('retention_period','')} (근거 {r.get('legal_basis','')})"
            )
        blocks.append("\n".join(lines))

    # 6) 라이프사이클
    rows = _like_search(
        "SELECT phase, sub_topic, requirement, related_docs, legal_basis "
        "FROM employment_lifecycle ",
        ["phase", "sub_topic", "requirement", "legal_basis"],
        "lifecycle",
    )
    if rows:
        sources.append("고용 생애주기")
        lines = ["[고용 생애주기]"]
        for r in rows:
            lines.append(
                f"- [{r['phase']} / {r['sub_topic']}] {r['requirement']} "
                f"(서류 {r.get('related_docs','')}, 근거 {r.get('legal_basis','')})"
            )
        blocks.append("\n".join(lines))

    # 7) 채용 컴플라이언스
    rows = _like_search(
        "SELECT stage, duty, description, violation_examples, penalty, legal_basis "
        "FROM recruit_compliance ",
        ["stage", "duty", "description", "violation_examples"],
        "recruit",
    )
    if rows:
        sources.append("채용 컴플라이언스")
        lines = ["[채용 단계 준수사항]"]
        for r in rows:
            lines.append(
                f"- [{r['stage']}] {r['duty']}: {r.get('description','')} "
                f"위반사례 {r.get('violation_examples','')} (벌칙 {r.get('penalty','')})"
            )
        blocks.append("\n".join(lines))

    # 8) 가이드 FAQ (guide_item) — 노무제공자 공통 표준계약서 등 주제별 안내
    rows = _like_search(
        "SELECT category, title, key_points, related_laws, note "
        "FROM guide_item WHERE excluded_from_service = 0 ",
        ["category", "title", "key_points", "note"],
        "guide_item",
    )
    if rows:
        sources.append("가이드 FAQ")
        lines = ["[가이드 FAQ]"]
        for r in rows:
            lines.append(
                f"- [{r['category']}] {r['title']}: {r.get('key_points','')[:400]} "
                f"(근거 {r.get('related_laws','')})"
            )
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks), sources

_GUIDE_CHAT_SYSTEM = (
    "너는 영세사업주를 위한 노동법 가이드 챗봇이다. 친근하고 명확한 톤으로 답하되,\n"
    "반드시 아래 [가이드 DB 컨텍스트] 의 정리된 자료를 1차 근거로 인용한다.\n\n"
    "원칙:\n"
    "1) 사업주가 알아야 할 의무·서식·절차·기관 정보 중심으로 답변. 분쟁·진정·구제는 안내 X.\n"
    "2) 답변 끝에 '관련 법령:' 한 줄로 근거 법령을 콤마로 묶어 표시.\n"
    "3) **공인노무사 상담 안내는 [정말 필요한 경우에만] 추가** — 매 답변마다 절대 붙이지 마라.\n"
    "   추가 조건 (이 중 하나라도 해당될 때만):\n"
    "   (a) 사실관계가 복잡하거나 판례가 갈리는 회색지대 (예: 정기상여금 통상임금성, 포괄임금제\n"
    "       유효성, 근로자성 판단, 부당해고 사유 정당성)\n"
    "   (b) 사업장 개별 사정에 따라 결론이 크게 달라지는 사안 (예: 단축근로 적용 범위, 취업규칙\n"
    "       불이익 변경 동의 요건)\n"
    "   (c) 가이드 DB 컨텍스트에 없는 영역이거나, LLM 일반지식만으로 답변한 경우\n"
    "   기본 의무·서식·신고 절차·기간·법령 인용 같은 명확한 사실 안내에는 노무사 권장 문구를\n"
    "   붙이지 마라. (관할 고용센터는 노무 상담 기관이 아님 — '고용센터 상담' 안내는 절대 금지.\n"
    "   단, 지원금·급여 신청 절차 안내는 고용센터 가능)\n"
    "4) 통상임금 판단은 2024.12.19 대법원 전원합의체 판결(2020다247190) 반영 — 고정성 요건 폐기,\n"
    "   소정근로 대가성·정기성·일률성 3요소만으로 판단.\n"
    "5) 답변은 2~5문장으로 간결. 필요하면 번호 목록 사용.\n"
    "6) 분쟁성 질문(진정·신고 등)이 들어오면 '본 서비스는 사업주 자율점검용입니다. 분쟁은\n"
    "   관할 지방고용노동청을 통해 진행해 주세요' 로 안내.\n"
    "7) **범위 밖 질문 거절** — 노동법·노무·사업장 운영(임금·근로시간·휴가·해고·보험·취업규칙·\n"
    "   근로계약서·임금명세서·노무제공자 계약·산재·출산육아·퇴직 등)과 무관한 질문은 답변하지\n"
    "   말고 다음 문구로 종결:\n"
    "     '죄송하지만 사업주 노무 관리 범위 밖 질문이라 답변드리기 어려워요. 노동법·근로조건·\n"
    "      보험·서식·계산 등 다른 노무 관련 질문이 있으시면 도와드릴게요.'\n"
    "   (예: '맛집 추천', '오늘 날씨', '주식 사는 법', '코딩 도와줘' 등 → 거절 문구만)\n"
    "   범위 밖이면 '관련 법령:' 줄과 [추천질문] 섹션 모두 출력 금지.\n"
    "8) **제재·처벌 표현 규칙(엄수)** — '전과', '벌금=형사처벌(전과)' 같은 표현은 절대 쓰지 마라.\n"
    "   위반 시 불이익은 반드시 '과태료·벌금 등 행정·형사 제재로 이어질 수 있습니다' 처럼\n"
    "   중립적으로 안내하고, 'A=B(전과)' 식 등식·낙인적 표현은 쓰지 않는다.\n\n"
    "[후속 추천 질문 — 반드시 출력]\n"
    "답변 본문 + '관련 법령' 표시 다음에 빈 줄 한 칸 후 정확히 다음 형식으로 추가:\n"
    "  [추천질문]\n"
    "  - <질문1>\n"
    "  - <질문2>\n"
    "  - <질문3>\n\n"
    "추천질문 작성 규칙:\n"
    "- 사용자가 방금 던진 질문과 다른 각도로, 답변 내용에서 자연스럽게 이어지는 후속 질문 3개.\n"
    "- 사업주 자율점검 범위(의무·서식·절차·기관·생애주기·채용·임금계산) 안에서만.\n"
    "- 짧고 구체적으로 (한 줄 ≤ 25자 권장).\n"
    "- 분쟁·진정·소송·노동위원회 관련은 추천하지 말 것.\n"
    "- 같은 주제 다른 측면(예: 의무 → 위반 시 제재, 신고 절차, 관련 서식, 상한·예외)으로 분산.\n"
    "예시:\n"
    "  [추천질문]\n"
    "  - 5인 미만은 어떻게 달라요?\n"
    "  - 위반 시 사업주 과태료는?\n"
    "  - 관련 표준 서식 어디서 받아요?"
)

_FOLLOWUP_BLOCK_RE = __import__('re').compile(
    r"\[추천질문\]\s*\n((?:\s*[-·●]\s*[^\n]+\n?)+)",
    flags=__import__('re').MULTILINE,
)

def _extract_followups(answer: str) -> tuple[str, list[str]]:
    """LLM 응답에서 [추천질문] 블록 분리 — 본문은 그 라인 제거 후 반환.

    포맷:
        ...본문...
        관련 법령: ...

        [추천질문]
        - 질문1
        - 질문2
        - 질문3
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
    # 빈 항목·너무 짧은 항목 제거 + 최대 3개로 제한
    items = [ln for ln in lines if len(ln) >= 4][:3]
    # 본문에서 블록 제거
    body = answer[: m.start()].rstrip()
    return body, items

def _sanitize_sanctions(text: str) -> str:
    """제재·처벌 표현 결정적 정제.

    사용자 요구: '전과', '벌금=형사처벌(전과)' 같은 낙인적·등식형 표현 금지.
    위반 불이익은 '과태료·벌금 등 행정·형사 제재' 로 중립 안내.
    LLM 준수에 의존하지 않도록 (a) 가이드 DB 컨텍스트, (b) 최종 답변 본문 양쪽에
    적용한다. (같은 입력 → 같은 출력: 결정성 유지)
    """
    if not text:
        return text
    import re

    s = text
    for a, b in (
        ("벌금=형사처벌(전과)", "과태료·벌금 등 행정·형사 제재"),
        ("벌금 = 형사처벌(전과)", "과태료·벌금 등 행정·형사 제재"),
        ("형사처벌(전과)", "형사 제재"),
        ("벌금=형사처벌", "벌금 등 형사 제재"),
        ("벌금 = 형사처벌", "벌금 등 형사 제재"),
    ):
        s = s.replace(a, b)
    # 괄호 주석 '(전과...)' 제거
    s = re.sub(r"\s*\(\s*전과[^)]*\)", "", s)
    # 잔여 '전과(+조사)' 언급 제거 (낙인 표현 차단)
    s = re.sub(r"전과(가|는|을|를|로|기록)?", "", s)
    # 치환 흔적 정리 — 이중 공백 / 구두점 앞 공백
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"\s+([,.)])", r"\1", s)
    return s.strip()
