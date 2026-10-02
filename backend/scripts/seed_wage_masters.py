"""임금명세서 계산형 위반 룰 토대 — 4개 마스터 reference 테이블 시드.

설계 출처: 임금명세서_DB모델링_설계.md (사용자 제공)

테이블
  - minimum_wage_master    : 연도별 최저임금 (2022~2026)
  - wage_item_catalog      : 임금 항목 코드·통상임금 여부
  - violation_type         : 위반 카탈로그 (V001 ~ V010)
  - recommendation_mapping : 위반 → 권고 본문 매핑

이 시드는 seed_master_db.py 의 7단계로 통합됨.
독립 실행도 가능: `python mvp/scripts/seed_wage_masters.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.repositories import base as db  # noqa: E402


# ═════════════════════════════════════════════════════════
# 1. 최저임금 마스터 (연도별)
# ═════════════════════════════════════════════════════════
#
# 출처: 최저임금위원회 매년 8월경 고시.
# 월 환산은 주 40시간 × 4.345주 = 약 209시간 기준.
MINIMUM_WAGE_ROWS = [
    # (year, hourly, monthly_209h, effective_from, effective_to, source)
    (2022, 9_160, 1_914_440, "2022-01-01", "2022-12-31",
     "최저임금위원회 고시 제2021-1호"),
    (2023, 9_620, 2_010_580, "2023-01-01", "2023-12-31",
     "최저임금위원회 고시 제2022-1호"),
    (2024, 9_860, 2_060_740, "2024-01-01", "2024-12-31",
     "최저임금위원회 고시 제2023-1호"),
    (2025, 10_030, 2_096_270, "2025-01-01", "2025-12-31",
     "최저임금위원회 고시 제2024-1호"),
    (2026, 10_320, 2_156_880, "2026-01-01", None,
     "최저임금위원회 고시 제2025-1호 (잠정)"),
]


def seed_minimum_wage(conn) -> int:
    n = 0
    for (year, hourly, monthly, eff_from, eff_to, source) in MINIMUM_WAGE_ROWS:
        conn.execute(
            "INSERT INTO minimum_wage_master "
            "(year, hourly_amount, monthly_amount_209h, effective_from, "
            " effective_to, source, notice_url) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(year) DO UPDATE SET "
            "  hourly_amount = excluded.hourly_amount, "
            "  monthly_amount_209h = excluded.monthly_amount_209h, "
            "  effective_from = excluded.effective_from, "
            "  effective_to = excluded.effective_to, "
            "  source = excluded.source",
            (year, hourly, monthly, eff_from, eff_to, source,
             "https://www.minimumwage.go.kr/"),
        )
        n += 1
    return n


# ═════════════════════════════════════════════════════════
# 2. 임금항목 카탈로그
# ═════════════════════════════════════════════════════════
#
# is_ordinary_wage(통상임금) — 정기적·일률적·고정적으로 지급되는 임금만 1.
#   상여금은 "정기" 여부에 따라 판례 분기 → 기본 0, LLM 으로 override.
# is_average_wage(평균임금)  — 사용자가 근로의 대가로 지급하는 임금의 총액. 대부분 1.
WAGE_ITEM_ROWS = [
    # (code, name, category, line_type, is_ord, is_avg, taxable, legal, desc, aliases)
    ("BASIC", "기본급", "기본급", "PAYMENT", 1, 1, 1,
     "근로기준법 제2조", "월급제·시급제·일급제의 기본 임금", '["기본급여"]'),
    ("OT", "연장근로수당", "법정수당", "PAYMENT", 0, 1, 1,
     "근로기준법 제56조", "1일 8h·1주 40h 초과 근로 — 통상임금의 50% 이상 가산",
     '["시간외수당","연장수당","오버타임수당"]'),
    ("NIGHT", "야간근로수당", "법정수당", "PAYMENT", 0, 1, 1,
     "근로기준법 제56조", "22:00~익일 06:00 근로 — 통상임금의 50% 이상 가산", '["야근수당"]'),
    ("HOLIDAY", "휴일근로수당", "법정수당", "PAYMENT", 0, 1, 1,
     "근로기준법 제56조", "휴일 근로 — 8시간 이내 50%, 초과 100% 가산", '["휴일수당"]'),
    ("WEEKLY_HOLIDAY", "주휴수당", "법정수당", "PAYMENT", 1, 1, 1,
     "근로기준법 제55조", "1주 소정근로일 개근 시 1일 유급휴일분 — 통상임금 산정 포함",
     '["유급주휴","주휴"]'),
    ("ANNUAL_LEAVE", "연차수당", "법정수당", "PAYMENT", 0, 1, 1,
     "근로기준법 제60조", "미사용 연차의 금전 보상 — 통상임금 미포함이 통설", '["연차미사용수당"]'),
    ("MEAL", "식대", "실비변상", "PAYMENT", 1, 0, 0,
     "—", "월 20만원까지 비과세. 정기·일률 지급 시 통상임금 포함 판례 다수",
     '["중식비","중식보조비","식비","식대보조"]'),
    ("VEHICLE", "자가운전보조금", "실비변상", "PAYMENT", 0, 0, 0,
     "—", "월 20만원까지 비과세. 통상임금 미포함 통설", '["자가운전수당","차량유지비"]'),
    ("BONUS_FIXED", "정기상여금", "상여", "PAYMENT", 1, 1, 1,
     "—", "정기적·일률적 지급 시 통상임금 포함 (2013 전합 판례)",
     '["고정상여","정기상여"]'),
    ("BONUS_PERF", "성과상여금", "상여", "PAYMENT", 0, 1, 1,
     "—", "성과·실적 연동 — 통상임금 미포함 통설", '["성과급","인센티브"]'),
    ("WELFARE", "복리후생비", "실비변상", "PAYMENT", 0, 0, 0,
     "—", "선택적 복지·경조사비 등", '["경조사비","복지포인트"]'),
    # ─── 공제 라인 ───
    ("INCOME_TAX", "근로소득세", "공제", "DEDUCTION", 0, 0, 0,
     "소득세법 제20조", "월급여 기준 간이세액표 적용", '["소득세"]'),
    ("LOCAL_TAX", "지방소득세", "공제", "DEDUCTION", 0, 0, 0,
     "지방세법 제93조", "근로소득세의 10%", '["주민세"]'),
    ("NATIONAL_PENSION", "국민연금", "공제", "DEDUCTION", 0, 0, 0,
     "국민연금법 제88조", "기준소득월액의 4.5% (근로자 부담)", '["연금"]'),
    ("HEALTH_INSURANCE", "건강보험", "공제", "DEDUCTION", 0, 0, 0,
     "국민건강보험법 제69조", "보수월액의 3.545% (2024년 근로자 부담)", '["건보료"]'),
    ("LONG_TERM_CARE", "장기요양보험", "공제", "DEDUCTION", 0, 0, 0,
     "노인장기요양보험법 제8조", "건강보험료의 12.95% (2024년)", '["요양보험"]'),
    ("EMPLOYMENT_INSURANCE", "고용보험", "공제", "DEDUCTION", 0, 0, 0,
     "고용보험법 제13조", "보수월액의 0.9% (근로자 부담)", '["고보료"]'),
    ("UNION_DUES", "조합비", "공제", "DEDUCTION", 0, 0, 0,
     "—", "노동조합 가입자 — 단체협약에 따라 공제", '["노조비"]'),
    ("ADVANCE_PAY", "가불금", "공제", "DEDUCTION", 0, 0, 0,
     "근로기준법 제43조", "공제 사유·금액에 근로자 동의 필요 — 일방 공제 위법",
     '["가불","선급금"]'),
]


def seed_wage_items(conn) -> int:
    n = 0
    for row in WAGE_ITEM_ROWS:
        conn.execute(
            "INSERT INTO wage_item_catalog "
            "(item_code, item_name, item_category, line_type, "
            " is_ordinary_wage, is_average_wage, is_taxable, "
            " legal_basis, description, aliases) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(item_code) DO UPDATE SET "
            "  item_name = excluded.item_name, "
            "  item_category = excluded.item_category, "
            "  line_type = excluded.line_type, "
            "  is_ordinary_wage = excluded.is_ordinary_wage, "
            "  is_average_wage = excluded.is_average_wage, "
            "  is_taxable = excluded.is_taxable, "
            "  legal_basis = excluded.legal_basis, "
            "  description = excluded.description, "
            "  aliases = excluded.aliases",
            row,
        )
        n += 1
    return n


# ═════════════════════════════════════════════════════════
# 3. 위반유형 카탈로그
# ═════════════════════════════════════════════════════════
#
# judgment_kind:
#   - rule : 코드 룰로 계산형 판단 (최저임금·연장근로수당 미달 등)
#   - llm  : 비계산적 판단 (수당이 통상임금인지 등)
VIOLATION_TYPE_ROWS = [
    # (code, name, severity, judgment_kind, legal_article, description, penalty)
    ("V001", "임금명세서 필수기재 누락", "HIGH", "rule",
     "근로기준법 제48조 제2항",
     "근로기준법 시행령 제27조의2 가 정한 필수기재 항목(성명·지급일·총액·구성항목 등)이 빠진 경우.",
     "500만원 이하 과태료"),
    ("V002", "최저임금 미달", "HIGH", "rule",
     "최저임금법 제6조",
     "시급 또는 월 환산액이 해당 연도 최저임금에 미달.",
     "3년 이하 징역 또는 2천만원 이하 벌금"),
    ("V003", "연장근로수당 부족", "HIGH", "rule",
     "근로기준법 제56조 제1항",
     "통상임금의 50% 가산이 누락되거나 부족.",
     "3년 이하 징역 또는 3천만원 이하 벌금"),
    ("V004", "야간근로수당 부족", "HIGH", "rule",
     "근로기준법 제56조 제3항",
     "22:00~06:00 근로분에 50% 가산이 누락되거나 부족.",
     "3년 이하 징역 또는 3천만원 이하 벌금"),
    ("V005", "휴일근로수당 부족", "HIGH", "rule",
     "근로기준법 제56조 제2항",
     "휴일 근로분에 50%(8h 이내)·100%(8h 초과) 가산이 누락되거나 부족.",
     "3년 이하 징역 또는 3천만원 이하 벌금"),
    ("V006", "주휴수당 미지급", "HIGH", "rule",
     "근로기준법 제55조 제1항",
     "1주 소정근로 개근 시 유급 주휴일분 임금이 누락.",
     "2년 이하 징역 또는 2천만원 이하 벌금"),
    ("V007", "임금 지급 지연", "MID", "rule",
     "근로기준법 제43조 제2항",
     "임금 지급일이 정기지급일을 도과 — 매월 1회 이상 일정한 날 지급 의무.",
     "3년 이하 징역 또는 3천만원 이하 벌금"),
    ("V008", "위법 공제", "HIGH", "rule",
     "근로기준법 제43조 제1항",
     "근로자 동의·법령 근거 없는 일방적 공제 (가불금 일방 차감 등).",
     "3년 이하 징역 또는 3천만원 이하 벌금"),
    ("V009", "통상임금 분류 오류", "MID", "llm",
     "—",
     "정기·일률·고정적으로 지급되는 수당을 통상임금에서 누락 (식대·정기상여 등 판례 쟁점).",
     "—"),
    ("V010", "공제내역 미분리", "MID", "rule",
     "근로기준법 시행령 제27조의2 제5호",
     "공제 항목별 금액이 아닌 총액만 표기 (항목별 분리 의무 위반).",
     "500만원 이하 과태료"),
]


def seed_violation_types(conn) -> int:
    n = 0
    for row in VIOLATION_TYPE_ROWS:
        code, name, sev, kind, legal, desc, penalty = row
        # 가능하면 law_article 매칭
        law_article_id = _find_law_article_id(conn, legal)
        conn.execute(
            "INSERT INTO violation_type "
            "(violation_code, violation_name, severity, judgment_kind, "
            " legal_article, law_article_id, description, penalty) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(violation_code) DO UPDATE SET "
            "  violation_name = excluded.violation_name, "
            "  severity = excluded.severity, "
            "  judgment_kind = excluded.judgment_kind, "
            "  legal_article = excluded.legal_article, "
            "  law_article_id = excluded.law_article_id, "
            "  description = excluded.description, "
            "  penalty = excluded.penalty",
            (code, name, sev, kind, legal, law_article_id, desc, penalty),
        )
        n += 1
    return n


def _find_law_article_id(conn, legal_article: str) -> int | None:
    """'근로기준법 제48조 제2항' → law_article.id.

    없으면 law / law_article 행을 즉석 생성 — 위반 카탈로그가 항상 self-contained.
    """
    if not legal_article or legal_article == "—":
        return None
    import re

    m = re.match(
        r"(.+?(?:법률|법|시행령|시행규칙))\s*"
        r"제(\d+)조(?:의(\d+))?"
        r"(?:\s*제(\d+)항)?"
        r"(?:\s*제(\d+)호)?",
        legal_article,
    )
    if not m:
        return None
    law_code = m.group(1).strip().replace(" ", "")
    article = f"제{m.group(2)}조"
    if m.group(3):
        article += f"의{m.group(3)}"
    paragraph = f"제{m.group(4)}항" if m.group(4) else None
    item = f"제{m.group(5)}호" if m.group(5) else None

    # 1) 존재하면 그대로 반환
    cur = conn.execute(
        "SELECT la.id FROM law_article la JOIN law l ON l.id = la.law_id "
        "WHERE l.code = ? AND la.article_no = ? "
        "  AND COALESCE(la.paragraph_no, '') = COALESCE(?, '') "
        "  AND COALESCE(la.item_no, '') = COALESCE(?, '') "
        "LIMIT 1",
        (law_code, article, paragraph, item),
    )
    row = cur.fetchone()
    if row:
        return row["id"]

    # 2) law 없으면 생성
    cur = conn.execute(
        "INSERT INTO law (code, full_name, external_base) VALUES (?, ?, ?) "
        "ON CONFLICT(code) DO UPDATE SET code = excluded.code RETURNING id",
        (law_code, law_code, f"https://www.law.go.kr/법령/{law_code}"),
    )
    law_id = cur.fetchone()["id"]

    # 3) law_article 생성
    external_url = f"https://www.law.go.kr/법령/{law_code}/{article}"
    cur = conn.execute(
        "INSERT INTO law_article "
        "(law_id, article_no, paragraph_no, item_no, external_url) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(law_id, article_no, paragraph_no, item_no) "
        "DO UPDATE SET external_url = excluded.external_url RETURNING id",
        (law_id, article, paragraph, item, external_url),
    )
    return cur.fetchone()["id"]


# ═════════════════════════════════════════════════════════
# 4. 권고안 매핑
# ═════════════════════════════════════════════════════════
RECOMMENDATION_ROWS = [
    # (violation_code, condition_expr, recommendation_text, template_fix, priority)
    ("V001", None,
     "임금명세서에 누락된 필수기재 항목({missing_fields})을 채워 재발급하세요. "
     "교부는 서면 또는 전자문서(이메일·앱·문자) 모두 가능하며, 교부 사실을 입증할 수 있어야 합니다.",
     None, 10),
    ("V002", None,
     "{year}년 최저시급은 {hourly_amount:,}원입니다. "
     "현재 시급 {current_hourly:,}원은 {diff:,}원 미달 — 해당 금액을 소급 지급하고 차기 임금부터 인상하세요.",
     None, 10),
    ("V003", None,
     "연장근로 {ot_hours}h 에 대해 통상시급 {ordinary_hourly:,}원 × 1.5 × 시간 = "
     "{expected:,}원이 지급되어야 합니다. 실제 지급 {actual:,}원과의 차액 {diff:,}원을 추가 지급하세요.",
     None, 10),
    ("V004", None,
     "야간근로 {night_hours}h 에 대해 통상시급의 50% 가산이 누락. "
     "추가 지급액: 통상시급 {ordinary_hourly:,}원 × 0.5 × {night_hours}h = {diff:,}원.",
     None, 10),
    ("V005", None,
     "휴일근로 {holiday_hours}h — 8시간 이내 50%, 초과분 100% 가산이 누락. "
     "차액 {diff:,}원을 추가 지급하세요.",
     None, 10),
    ("V006", None,
     "1주 {weekly_hours}h 개근 시 주휴수당(통상시급 × 1일 소정근로시간)이 지급되어야 합니다. "
     "누락분: {diff:,}원.",
     None, 10),
    ("V007", None,
     "정기지급일({pay_date_standard})을 {days_late}일 도과. "
     "매월 1회 이상 일정한 날에 지급해야 하며 지연 시 지연이자(연 20%) 발생 가능.",
     None, 20),
    ("V008", None,
     "근로자 동의 또는 법령 근거 없는 공제는 위법입니다 ({deducted_item} {amount:,}원). "
     "근로자 동의서를 받지 않았다면 즉시 환급하세요.",
     None, 10),
    ("V009", None,
     "{item_name}을(를) 통상임금에 포함하면 연장·야간·휴일근로수당 산정 기준이 바뀝니다. "
     "정기·일률·고정 지급 여부를 다시 검토하세요. (판례: 대법 2012다89399 전합)",
     None, 30),
    ("V010", None,
     "공제 항목을 분리 기재하세요 — 예: 소득세 {it:,}원 / 국민연금 {np:,}원 / "
     "건강보험 {hi:,}원 / 고용보험 {ei:,}원 / 공제 총액 {total:,}원.",
     None, 10),
]


def seed_recommendations(conn) -> int:
    n = 0
    for row in RECOMMENDATION_ROWS:
        violation_code, cond, text, template, priority = row
        # 중복 방지 — (violation_code, recommendation_text) 같으면 skip
        cur = conn.execute(
            "SELECT recommendation_id FROM recommendation_mapping "
            "WHERE violation_code = ? AND recommendation_text = ?",
            (violation_code, text),
        )
        if cur.fetchone():
            continue
        conn.execute(
            "INSERT INTO recommendation_mapping "
            "(violation_code, condition_expr, recommendation_text, "
            " template_fix, priority) VALUES (?, ?, ?, ?, ?)",
            (violation_code, cond, text, template, priority),
        )
        n += 1
    return n


# ═════════════════════════════════════════════════════════
# main
# ═════════════════════════════════════════════════════════
def main() -> None:
    db.init_schema(drop_first=False)  # 추가 테이블만 — drop 안 함
    with db.connect() as conn:
        n1 = seed_minimum_wage(conn)
        print(f"minimum_wage_master: {n1} rows")
        n2 = seed_wage_items(conn)
        print(f"wage_item_catalog: {n2} rows")
        n3 = seed_violation_types(conn)
        print(f"violation_type: {n3} rows")
        n4 = seed_recommendations(conn)
        print(f"recommendation_mapping: {n4} rows")


if __name__ == "__main__":
    main()
