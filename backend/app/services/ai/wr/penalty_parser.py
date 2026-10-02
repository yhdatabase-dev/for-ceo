"""벌칙 자동 분류기.

마스터 DB I열·슬롯 카탈로그 penalty 의 각 항목을 두 카테고리로 자동 분류:
  - 📋 omission : 취업규칙 필수기재 미기재 시 적용 (행정 위반)
  - ⚖️ violation : 법령 내용 자체 위반 시 적용 (실체 위반)

분류 규칙 (우선순위 순):
  1. "직접 적용 벌칙 없음" / "권고사항" → 둘 다 빈 리스트 (분류 제외)
  2. 명시 키워드:
     - "미기재" / "필수기재" / "제93조" / "제116조 제2항 제2호" → omission
     - "징역" / "벌금" + 본 조항 위반 키워드 → violation
  3. 슬래시 "/" 로 결합된 경우 — 분할 후 각각 분류
"""
from __future__ import annotations

import re
from typing import Iterable


# 미기재 식별자 (취업규칙 작성 의무 위반)
_OMISSION_PATTERNS = [
    r"제93조",                       # 근기법 제93조 (필수기재사항)
    r"제116조\s*제2항\s*제2호",         # 미기재 과태료 조항
    r"미기재",
    r"필수기재\s*누락",
    r"필수\s*기재",
    r"(?:취업규칙|필수기재)\s*미기재",
]

# 법령 위반 식별자
_VIOLATION_PATTERNS = [
    r"제109조",                       # 근기법 제109조 (형사처벌)
    r"제110조",                       # 근기법 제110조 (형사처벌)
    r"제108조",                       # 근기법 제108조
    r"징역",                          # 형사처벌
    r"벌금",                          # 형사처벌 또는 위반 벌금
    r"과태료",                        # 미기재 키워드와 함께 안 나오면 법령 위반
    r"위반",                          # 모든 "위반" 단어 (조 단독 위반 표현 포함)
    r"부당\s*(?:거부|처우)",            # 부당거부·부당처우
    r"불리\s*(?:처우|행위)",            # 불리처우 (예: 신고자)
    r"제\d+조(?:의\d+)?",              # 법령 조항 단독 인용 (예: "근로기준법 제27조")
]


_OMISSION_RE = re.compile("|".join(_OMISSION_PATTERNS))
_VIOLATION_RE = re.compile("|".join(_VIOLATION_PATTERNS))

# "직접 적용 벌칙 없음" / "권고" 류 — 분류 제외
_NO_PENALTY_RE = re.compile(r"직접\s*적용\s*벌칙\s*없음|권고사항|권고\s*수준")


def is_no_penalty(item: str) -> bool:
    """벌칙 없음 (권고 사항) 인지 판정."""
    return bool(_NO_PENALTY_RE.search(item or ""))


def classify_one(item: str) -> str:
    """단일 항목을 omission / violation / no_penalty / unknown 중 하나로 분류.

    분류 우선순위:
      1. 권고·벌칙 없음 → no_penalty
      2. 미기재 키워드 ('미기재', '제93조', '제116조 제2항 제2호') → omission
         (미기재 항목은 법문에 '위반' 단어가 같이 나와도 omission 으로 분류)
      3. 위반·형사처벌 키워드 → violation
      4. 둘 다 매칭 안 됨 → unknown
    """
    if not item or not item.strip():
        return "no_penalty"
    if is_no_penalty(item):
        return "no_penalty"
    # omission 우선 — "미기재" 표현이 더 구체적 정보
    if _OMISSION_RE.search(item):
        return "omission"
    if _VIOLATION_RE.search(item):
        return "violation"
    return "unknown"


def split_compound(item: str) -> list[tuple[str, str]]:
    """슬래시(/) 로 결합된 복합 벌칙을 분할하고 각각 분류.

    Returns:
        [(category, text), ...]
        category: omission / violation / unknown / no_penalty
    """
    parts = [p.strip() for p in re.split(r"\s+/\s+", item) if p.strip()]
    if len(parts) <= 1:
        return [(classify_one(item), item)]
    out: list[tuple[str, str]] = []
    for p in parts:
        out.append((classify_one(p), p))
    return out


def split_penalty(penalty: Iterable[str] | None) -> dict[str, list[str]]:
    """penalty 리스트 전체를 두 카테고리 + 기타로 분류.

    Returns:
        {
            "omission":   ["근로기준법 제93조 ...", ...],
            "violation":  ["근로기준법 제110조 ...", ...],
            "no_penalty": ["직접 적용 벌칙 없음 ..."],   # UI 에서 별도 처리
            "unknown":    [...]                       # 분류 실패 — 표기는 violation 쪽에 함께
        }
    """
    out: dict[str, list[str]] = {
        "omission": [],
        "violation": [],
        "no_penalty": [],
        "unknown": [],
    }
    if not penalty:
        return out
    for item in penalty:
        item = str(item).strip()
        if not item:
            continue
        for cat, text in split_compound(item):
            if text not in out[cat]:
                out[cat].append(text)
    return out


def format_for_user(penalty: Iterable[str] | None) -> dict[str, list[str]]:
    """사용자에게 표시할 두 카테고리.

    Returns:
        {
            "omission":  [...],   # 📋 취업규칙 미기재 시
            "violation": [...],   # ⚖️ 법령 위반 시
        }

    unknown 은 violation 으로 흡수 (보수적). no_penalty 는 비어 있는 카테고리로 처리.
    """
    parts = split_penalty(penalty)
    return {
        "omission": parts["omission"],
        "violation": parts["violation"] + parts["unknown"],
    }
