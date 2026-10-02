"""슬롯 적용 가능성 (applicability) 룰.

사업장 정보(WorkplaceContext)에 따라 일부 조의 슬롯을 SKIP 처리.
- 교대근로 미도입 사업장: 22조 SKIP
- 산안법 비대상 업종: 89·90·91·94·95조 SKIP
- 화학물질 미취급: 92조 (MSDS) SKIP
- 작업환경측정 미대상: 93조 SKIP
- 5인 미만 사업장: 32조의 공휴일 슬롯 SKIP (5인 이상에만 적용)
"""
from __future__ import annotations

from app.schemas.wr.values import SlotDef, WorkplaceContext


# 조 번호 → 컨텍스트 키 매핑. 해당 키가 False 일 때 슬롯 SKIP.
# True 또는 None(미입력)이면 활성.
# 5인 이상 사업장은 디폴트 가정 — 별도 체크박스 미사용.
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


def is_slot_applicable(slot: SlotDef, context: WorkplaceContext | None) -> tuple[bool, str | None]:
    """슬롯이 이 사업장에 적용 가능한지 판정.

    Returns:
        (applicable, skip_reason)
        applicable=True 면 검사 진행. False 면 SKIP — 리포트에 표시.
    """
    if context is None:
        return True, None
    requires = ARTICLE_REQUIRES.get(slot.article, [])
    for key in requires:
        v = getattr(context, key, None)
        # None = 모름 → 보수적으로 활성
        if v is False:
            label = _LABELS.get(key, key)
            return False, f"사업장 정보상 미적용 ({label})"
    return True, None


_LABELS = {
    "shift_work_used": "교대근로 미도입",
    "osha_applicable": "산안법 비대상 업종",
    "chemical_handling": "화학물질 미취급",
    "workenv_measurement": "작업환경측정 미대상",
}
