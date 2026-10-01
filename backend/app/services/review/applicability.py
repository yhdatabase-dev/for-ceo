"""슬롯 적용 가능성 (applicability) 룰.

===============================================================================
원본 이관
===============================================================================
원본: `cgr/applicability.py` (54줄) → v2 로 그대로 이관 (순수 함수).

변경점
- `cgr.models.SlotDef` → `app.schemas.review.values.SlotDefVO`
- `cgr.models.WorkplaceContext` → `app.schemas.shared.WorkplaceContextIn`
- 로직·매핑 테이블·레이블은 원본과 100% 동일.

사업장 정보에 따른 슬롯 SKIP 정책 (원본 그대로):
- 교대근로 미도입: 22조 SKIP
- 산안법 비대상 업종: 89·90·91·94·95조 SKIP
- 화학물질 미취급: 92조 (MSDS) SKIP
- 작업환경측정 미대상: 93조 SKIP
- 5인 이상 사업장은 디폴트 가정 — 별도 체크박스 미사용
"""
from __future__ import annotations

from app.schemas.review.values import SlotDefVO
from app.schemas.shared import WorkplaceContextIn


# 조 번호 → 컨텍스트 키 매핑. 해당 키가 False 일 때 슬롯 SKIP.
# True 또는 None(미입력)이면 활성.
ARTICLE_REQUIRES: dict[int, list[str]] = {
    22: ["shift_work_used"],
    89: ["osha_applicable"],
    90: ["osha_applicable"],
    91: ["osha_applicable"],
    92: ["chemical_handling"],
    93: ["workenv_measurement"],
    94: ["osha_applicable"],
    95: ["osha_applicable"],
}


_LABELS = {
    "shift_work_used": "교대근로 미도입",
    "osha_applicable": "산안법 비대상 업종",
    "chemical_handling": "화학물질 미취급",
    "workenv_measurement": "작업환경측정 미대상",
}


def is_slot_applicable(
    slot: SlotDefVO,
    context: WorkplaceContextIn | None,
) -> tuple[bool, str | None]:
    """슬롯이 이 사업장에 적용 가능한지 판정.

    Args:
        slot:    슬롯 정의 (article 번호로 매핑 조회)
        context: 사업장 컨텍스트 (None 이면 무조건 활성)

    Returns:
        (applicable, skip_reason)
        - applicable=True  : 검사 진행 (skip_reason=None)
        - applicable=False : SKIP — 리포트에 skip_reason 표시
    """
    if context is None:
        return True, None
    requires = ARTICLE_REQUIRES.get(slot.article, [])
    for key in requires:
        v = getattr(context, key, None)
        # None = 모름 → 보수적으로 활성 (원본 정책 그대로)
        if v is False:
            label = _LABELS.get(key, key)
            return False, f"사업장 정보상 미적용 ({label})"
    return True, None
