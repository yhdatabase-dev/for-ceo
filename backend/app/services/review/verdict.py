"""Finding 집계 → 부적정 판정 (5-Bucket).

===============================================================================
원본 이관
===============================================================================
원본: `cgr/verdict.py` (91줄) → v2 로 이관 (순수 함수).

변경점
- `cgr.models.Finding` → `app.schemas.review.values.FindingVO`
- `cgr.models.Report`  → `app.schemas.review.values.ReportVO`
- 원본 Report 는 `article_results: list[ArticleResult]` 로 그룹핑된 구조였으나
  v2 ReportVO 는 `findings: list[FindingVO]` 로 평면화됨.
- `finalize_report` 는 이 구조 차이를 반영해 축약됨 (그룹핑 로직 불필요).
- classify · severity_counter · detail_label · overall_label 은 원본과 100% 동일.

분류 체계 (status 우선 + severity 보조):
- 🔴 누락      = status=MISSING & severity ≠ LOW (본문에 필수기재 누락)
- 🟡 위반      = status=VIOLATION & severity ≠ LOW (본문은 있으나 법정 기준 미달)
- 🔵 주의      = status in {VIOLATION, MISSING} & severity = LOW (임의·확인적 규정 미준수)
- 🟣 검토필요  = status=AMBIGUOUS (매칭 모호 — 감독관 재확인)
- ✅ 적정      = status=OK

종합 판정:
- 누락·위반 1건 이상 → "부적정"
- 주의만            → "부적정(경미)"
- 검토필요만        → "검토 보류"
- 모두 OK           → "적정"
- ERROR 만          → "검토불가"
"""
from __future__ import annotations

from typing import Literal

from app.schemas.review.values import FindingVO, ReportVO

OverallLabel = Literal["적정", "부적정", "검토불가"]
DetailLabel = str  # "적정" | "부적정" | "부적정(경미)" | "검토 보류" | "검토불가"


def classify(f: FindingVO) -> str:
    """Finding 1건을 5개 버킷 중 하나로 분류."""
    if f.status == "OK":
        return "적정"
    if f.status == "AMBIGUOUS":
        return "검토필요"
    if f.status == "ERROR":
        return "검토불가"
    # MISSING / VIOLATION
    if f.severity == "LOW":
        return "주의"
    if f.status == "MISSING":
        return "누락"
    if f.status == "VIOLATION":
        return "위반"
    return "검토불가"


def severity_counter(findings: list[FindingVO]) -> dict[str, int]:
    """5개 버킷 단위로 카운트.

    0 인 버킷도 키는 유지 (UI 가 항상 동일한 5칸을 보여주도록).
    """
    out: dict[str, int] = {"누락": 0, "위반": 0, "주의": 0, "검토필요": 0, "적정": 0}
    for f in findings:
        b = classify(f)
        if b in out:
            out[b] = out.get(b, 0) + 1
    return out


def detail_label(findings: list[FindingVO]) -> DetailLabel:
    """상세 라벨 (5가지) — UI 표시용."""
    cnt = severity_counter(findings)
    has_err = any(f.status == "ERROR" for f in findings)
    miss = cnt.get("누락", 0)
    viol = cnt.get("위반", 0)
    warn = cnt.get("주의", 0)
    amb = cnt.get("검토필요", 0)

    if miss == 0 and viol == 0 and warn == 0 and amb == 0:
        if has_err:
            return "검토불가"
        return "적정"
    if miss > 0 or viol > 0:
        return "부적정"
    if warn > 0:
        return "부적정(경미)"
    return "검토 보류"


def overall_label(findings: list[FindingVO]) -> OverallLabel:
    """종합 라벨 (3가지) — API 응답용."""
    cnt = severity_counter(findings)
    if cnt.get("누락", 0) > 0 or cnt.get("위반", 0) > 0 or cnt.get("주의", 0) > 0:
        return "부적정"
    err = any(f.status == "ERROR" for f in findings)
    if err and not any(f.status == "OK" for f in findings):
        return "검토불가"
    return "적정"


def finalize_report(report: ReportVO) -> ReportVO:
    """리포트 summary + overall_label 채움.

    v2 는 ReportVO.findings 가 평면 리스트라 원본의 article_results 순회 불필요.
    """
    report.summary = severity_counter(report.findings)
    report.overall_label = overall_label(report.findings)
    return report
