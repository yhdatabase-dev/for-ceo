#
# Finding 집계 → 부적정 판정.
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.05.28      kimzion77   최초 생성
# 2026.10.02      이시영      구조 이행 (backend/cgr → backend/app)
# 2026.10.02      이시영      구조 조정 (web/ai 파트 디렉터리 → 도메인 단일 디렉터리)
#
# Author: kimzion77
# Since: 2026.05.28
#
"""Finding 집계 → 부적정 판정.

분류 체계 (status 우선 + severity 보조):
  - 🔴 누락 = status=MISSING & severity ≠ LOW (본문에 필수기재 누락)
  - 🟡 위반 = status=VIOLATION & severity ≠ LOW (본문은 있으나 법정 기준 미달)
  - 🔵 주의 = (status in {VIOLATION, MISSING}) & severity = LOW (임의·확인적 규정 미준수)
  - 🟣 검토필요 = status=AMBIGUOUS (매칭 모호 — 감독관 재확인)
  - ✅ 적정 = status=OK

종합 판정:
  - 누락·위반 1건 이상 → "부적정"
  - 주의만 → "부적정(경미)"
  - 검토필요만 → "검토 보류"
  - 모두 OK → "적정"
  - ERROR 만 → "검토불가"
"""
from __future__ import annotations

from typing import Literal

from app.schemas.wr.values import Finding, Report

OverallLabel = Literal["적정", "부적정", "검토불가"]
DetailLabel = str  # "적정" | "부적정" | "부적정(경미)" | "검토 보류" | "검토불가"


def classify(f: Finding) -> str:
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


def severity_counter(findings: list[Finding]) -> dict[str, int]:
    """5개 버킷 단위로 카운트."""
    out: dict[str, int] = {"누락": 0, "위반": 0, "주의": 0, "검토필요": 0, "적정": 0}
    for f in findings:
        b = classify(f)
        if b in out:
            out[b] = out.get(b, 0) + 1
    # 0 인 버킷도 키는 유지 (UI 가 항상 동일한 5칸을 보여주도록)
    return out


def detail_label(findings: list[Finding]) -> DetailLabel:
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


def overall_label(findings: list[Finding]) -> OverallLabel:
    cnt = severity_counter(findings)
    if cnt.get("누락", 0) > 0 or cnt.get("위반", 0) > 0 or cnt.get("주의", 0) > 0:
        return "부적정"
    err = any(f.status == "ERROR" for f in findings)
    if err and not any(f.status == "OK" for f in findings):
        return "검토불가"
    return "적정"


def finalize_report(report: Report) -> Report:
    all_findings: list[Finding] = []
    for ar in report.article_results:
        all_findings.extend(ar.findings)
    report.summary = severity_counter(all_findings)
    report.overall_label = overall_label(all_findings)
    return report
