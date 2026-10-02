"""판정 분류 골든 테스트 — 취업규칙(5버킷) · 근로계약서(3버킷).

두 체계는 의도적으로 별개다 (ec/verdict.py docstring 참조). 여기 기대값이
바뀌면 프론트 배지·통계·신구대조표 로직이 전부 영향받으므로 신중히.
"""
from __future__ import annotations

from app.services.ai.wr import verdict as wr
from app.services.ai.ec import verdict as ec
from app.schemas.wr.values import ArticleResult, Extraction, Finding, MasterValue, Report


# ─────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────
def make_finding(status: str, severity: str = "MEDIUM") -> Finding:
    return Finding(
        slot_id="t-1", article=1, item_name="테스트",
        extracted=Extraction(slot_id="t-1", found=True),
        expected=MasterValue(), comparator="presence",
        status=status, severity=severity,
    )


# ─────────────────────────────────────────────────────
# 취업규칙 — classify 5버킷
# ─────────────────────────────────────────────────────
def test_wr_classify_buckets():
    assert wr.classify(make_finding("OK")) == "적정"
    assert wr.classify(make_finding("AMBIGUOUS")) == "검토필요"
    assert wr.classify(make_finding("ERROR")) == "검토불가"
    assert wr.classify(make_finding("MISSING", "HIGH")) == "누락"
    assert wr.classify(make_finding("VIOLATION", "MEDIUM")) == "위반"
    # severity LOW 는 status 불문 '주의'
    assert wr.classify(make_finding("MISSING", "LOW")) == "주의"
    assert wr.classify(make_finding("VIOLATION", "LOW")) == "주의"


def test_wr_severity_counter_always_5_keys():
    cnt = wr.severity_counter([make_finding("OK")])
    assert set(cnt.keys()) == {"누락", "위반", "주의", "검토필요", "적정"}
    assert cnt["적정"] == 1


def test_wr_overall_label():
    assert wr.overall_label([make_finding("OK")]) == "적정"
    assert wr.overall_label([make_finding("VIOLATION", "HIGH")]) == "부적정"
    assert wr.overall_label([make_finding("MISSING", "LOW")]) == "부적정"  # 주의도 부적정
    assert wr.overall_label([make_finding("AMBIGUOUS")]) == "적정"  # 검토필요만으론 부적정 아님
    assert wr.overall_label([make_finding("ERROR")]) == "검토불가"


def test_wr_detail_label():
    assert wr.detail_label([make_finding("OK")]) == "적정"
    assert wr.detail_label([make_finding("MISSING", "HIGH")]) == "부적정"
    assert wr.detail_label([make_finding("VIOLATION", "LOW")]) == "부적정(경미)"
    assert wr.detail_label([make_finding("AMBIGUOUS")]) == "검토 보류"
    assert wr.detail_label([make_finding("ERROR")]) == "검토불가"


def test_wr_finalize_report():
    report = Report(
        case_id="t", source_file="t.txt",
        article_results=[ArticleResult(
            article=1, title="테스트",
            findings=[make_finding("VIOLATION", "HIGH"), make_finding("OK")],
        )],
    )
    out = wr.finalize_report(report)
    assert out.overall_label == "부적정"
    assert out.summary["위반"] == 1 and out.summary["적정"] == 1


# ─────────────────────────────────────────────────────
# 근로계약서 — classify_ec 3버킷
# ─────────────────────────────────────────────────────
def test_ec_classify_matrix():
    # 미기재
    assert ec.classify_ec(present=False, severity="HIGH") == "부적절"
    assert ec.classify_ec(present=False, severity="CRITICAL") == "부적절"
    assert ec.classify_ec(present=False, severity="MEDIUM") == "보완필요"
    # 기재 + 내용 OK
    assert ec.classify_ec(present=True, content_ok=True, severity="HIGH") == "적절"
    # 기재 + 내용 미달
    assert ec.classify_ec(present=True, content_ok=False, severity="HIGH") == "부적절"
    assert ec.classify_ec(present=True, content_ok=False, severity="LOW") == "보완필요"
    # 기재 + LLM 미판단 → 항상 보완필요
    assert ec.classify_ec(present=True, content_ok=None, severity="CRITICAL") == "보완필요"


def test_ec_overall_label():
    assert ec.overall_label({"부적절": 1, "보완필요": 3}) == "부적절"
    assert ec.overall_label({"부적절": 0, "보완필요": 1}) == "보완필요"
    assert ec.overall_label({"적절": 5}) == "적절"
    assert ec.overall_label({}) == "적절"
