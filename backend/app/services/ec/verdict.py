"""근로계약서 분류 — 3-Bucket (적절 / 보완필요 / 부적절).

취업규칙(5-Bucket: 누락/위반/주의/검토필요/적정)과 별개 체계.
RFP 매핑 표에서 기존 노무사회 분류 그대로.
"""
from __future__ import annotations

from typing import Literal

ECBucket = Literal["적절", "보완필요", "부적절"]


def classify_ec(
    *,
    present: bool,
    content_ok: bool | None = None,
    severity: str = "MEDIUM",
) -> ECBucket:
    """
    근로계약서 슬롯 1건의 분류.

    매개변수:
      present: 본문에 해당 항목이 기재되어 있는지
      content_ok: 기재 내용이 법정 기준을 충족하는지
                  None = LLM 판단 미수행 / True = 충족 / False = 미달
      severity: 슬롯의 violation_severity (CRITICAL/HIGH/MEDIUM/LOW)

    분류 규칙:
      - 미기재 → 부적절 (severity HIGH 이상) 또는 보완필요 (MEDIUM 이하)
      - 기재 있고 내용 OK → 적절
      - 기재 있고 내용 미달 → 부적절 (severity HIGH 이상) 또는 보완필요
      - 기재 있고 LLM 판단 없음 → 보완필요 (감독관 확인 권장)
    """
    is_severe = severity in ("CRITICAL", "HIGH")

    if not present:
        return "부적절" if is_severe else "보완필요"

    if content_ok is True:
        return "적절"

    if content_ok is False:
        return "부적절" if is_severe else "보완필요"

    # content_ok is None — LLM 미판단
    return "보완필요"


def overall_label(buckets: dict[ECBucket, int]) -> str:
    """
    종합 판정 — 부적절이 1개라도 있으면 부적절, 보완필요만 있으면 보완필요, 그 외 적절.

    프론트의 verdict 필드에 사용 (취업규칙의 '부적정/적정/검토불가' 와 대비됨).
    """
    if buckets.get("부적절", 0) > 0:
        return "부적절"
    if buckets.get("보완필요", 0) > 0:
        return "보완필요"
    return "적절"
