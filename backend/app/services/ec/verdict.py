"""EC 3-Bucket 분류 헬퍼 — 원본 `cgr/ec/verdict.py` 이관.

===============================================================================
원본 이관
===============================================================================
원본 100% 이관. WR (5-Bucket) 과 완전 별개 분류 체계.

3-Bucket: 적절 / 보완필요 / 부적절
- 미기재 → 부적절 (severity HIGH 이상) 또는 보완필요
- 기재 + 내용 OK → 적절
- 기재 + 내용 미달 → 부적절 (HIGH+) 또는 보완필요
- 기재 + LLM 미판단 → 보완필요
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
    """근로계약서 슬롯 1건 분류 — 원본 로직 그대로."""
    is_severe = severity in ("CRITICAL", "HIGH")

    if not present:
        return "부적절" if is_severe else "보완필요"

    if content_ok is True:
        return "적절"

    if content_ok is False:
        return "부적절" if is_severe else "보완필요"

    return "보완필요"


def overall_label(buckets: dict[str, int]) -> str:
    """종합 라벨 — 부적절 1개 이상이면 부적절, 보완필요만 있으면 보완필요, 그 외 적절."""
    if buckets.get("부적절", 0) > 0:
        return "부적절"
    if buckets.get("보완필요", 0) > 0:
        return "보완필요"
    return "적절"


def slot_applies_to(
    applicability: dict,
    business_size: str | None,
    worker_types: list[str],
) -> bool:
    """원본 `cgr/ec/catalog.py:EcSlot.applies_to` 이관.

    EcSlotVO 는 applicability 를 dict 로 보관하므로 스탠드얼론 헬퍼로 분리.
    """
    bs = applicability.get("business_size") or "any"
    if bs != "any":
        if bs == "5+" and business_size == "5-":
            return False
        if bs == "5-" and business_size == "5+":
            return False

    wt = applicability.get("worker_types")
    if wt and wt != "any":
        user_types = set(worker_types or ["정규직"])
        slot_types = set(wt) if isinstance(wt, list) else {wt}
        if not (user_types & slot_types):
            return False

    return True
