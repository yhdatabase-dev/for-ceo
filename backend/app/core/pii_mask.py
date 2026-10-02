"""PII (개인식별정보) 비식별 게이트.

**용도**: 외부 LLM 호출 직전에 본문 텍스트의 PII 를 마스킹.

설계 원칙
- 보수적 — 의심스러우면 마스킹. 분석 정확도 약간 손해보더라도 PII 노출 방지 우선.
- 패턴 기반 — 한국 PII 의 정규 패턴 (전화·사업자번호·주민번호·이메일).
- 라벨 컨텍스트 기반 — "성명: 홍길동" 같이 라벨 다음에 오는 값만 마스킹 (오탐 방지).
- 결과 가독성 유지 — `홍길동` → `홍○○` 같이 형태는 유지.

**적용 위치** (LLM 호출 직전):
- `cgr.ec.services.analyze.run()` — 근로계약서 분석
- `cgr.ec.services.structure.run()` — 8섹션 구조화
- `cgr.ec.services.chat.run()` — 후속 챗봇
- `cgr.ec.services.generate.run()` — 표준 계약서 생성

**환경변수**
- `CGR_PII_MASK=0` 으로 비활성화 (테스트·디버그 용).
"""
from __future__ import annotations

import os
import re
from typing import NamedTuple


# ─────────────────────────────────────────────────────
# 정규 패턴 — 한국 PII
# ─────────────────────────────────────────────────────

# 전화번호 — 02-1234-5678 / 010-1234-5678 / 0212345678
PHONE_RE = re.compile(
    r"\b(01[016789]|02|0[3-9]\d?)[-\s]?\d{3,4}[-\s]?\d{4}\b"
)

# 사업자번호 — 123-45-67890
BIZ_NO_RE = re.compile(r"\b\d{3}-\d{2}-\d{5}\b")

# 주민등록번호 — 901231-1234567 (성별자리 1~4)
RRN_RE = re.compile(r"\b\d{6}-[1-4]\d{6}\b")

# 이메일
EMAIL_RE = re.compile(
    r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"
)

# 라벨된 성명 — "성명: 홍길동" / "이름 홍길동" / "근로자 김철수"
LABELED_NAME_RE = re.compile(
    r"(성\s*명|이\s*름|근로자\s*명?|성\s*함|대표\s*자|담당자|작성자)"
    r"\s*[:：]?\s*([가-힣]{2,4})\b"
)

# 라벨된 사번 — "사번 2024-001" / "사원번호: A1234"
LABELED_EMPNO_RE = re.compile(
    r"(사\s*번|사원\s*번호|직원\s*번호|emp(?:loyee)?\s*id)"
    r"\s*[:：]?\s*([A-Za-z0-9가-힣\-]{2,20})\b",
    re.IGNORECASE,
)

# 라벨된 계좌번호 — "계좌 110-1234-5678" / "계좌번호: 12345678"
LABELED_ACCOUNT_RE = re.compile(
    r"(계\s*좌\s*번?\s*호?|입금\s*계좌|예금\s*계좌)"
    r"\s*[:：]?\s*([\d\-]{8,30})\b"
)

# 카드번호 — 4자리 묶음
CARD_NO_RE = re.compile(r"\b(\d{4})[-\s]?(\d{4})[-\s]?(\d{4})[-\s]?(\d{4})\b")


# ─────────────────────────────────────────────────────
# 마스킹 함수들
# ─────────────────────────────────────────────────────
def _mask_name(name: str) -> str:
    """`홍길동` → `홍○○` (첫 글자 유지). 한 글자면 그대로."""
    name = name.strip()
    if len(name) <= 1:
        return name
    return name[0] + "○" * (len(name) - 1)


def _mask_phone(_m: re.Match) -> str:
    """`010-1234-5678` → `010-****-****`. 지역번호 유지로 가독성 ↑."""
    head = _m.group(1)
    return f"{head}-****-****"


def _mask_card(m: re.Match) -> str:
    """`1234-5678-9012-3456` → `1234-****-****-3456`."""
    return f"{m.group(1)}-****-****-{m.group(4)}"


class MaskResult(NamedTuple):
    masked: str
    counts: dict[str, int]  # 종류별 마스킹 횟수


# ─────────────────────────────────────────────────────
# 메인 진입
# ─────────────────────────────────────────────────────
def is_enabled() -> bool:
    """환경변수로 비활성 가능 — 기본 ON."""
    return os.environ.get("CGR_PII_MASK", "1").lower() not in ("0", "false", "off")


def mask_pii(text: str) -> MaskResult:
    """본문 텍스트에서 PII 패턴 검출·마스킹.

    반환: (마스킹된 텍스트, {종류: 횟수} 카운트)
    환경변수 `CGR_PII_MASK=0` 이면 원본 그대로.
    """
    if not text or not is_enabled():
        return MaskResult(text or "", {})

    counts: dict[str, int] = {}

    def _count(key: str, n: int = 1) -> None:
        counts[key] = counts.get(key, 0) + n

    out = text

    # 1) 주민번호 — 가장 민감. 먼저.
    matches = RRN_RE.findall(out)
    if matches:
        _count("rrn", len(matches))
        out = RRN_RE.sub("******-*******", out)

    # 2) 카드번호 — 4-4-4-4 패턴 (전화번호보다 먼저 — overlap 방지)
    matches = CARD_NO_RE.findall(out)
    if matches:
        _count("card", len(matches))
        out = CARD_NO_RE.sub(_mask_card, out)

    # 3) 사업자번호
    matches = BIZ_NO_RE.findall(out)
    if matches:
        _count("biz_no", len(matches))
        out = BIZ_NO_RE.sub("***-**-*****", out)

    # 4) 전화번호
    matches = PHONE_RE.findall(out)
    if matches:
        _count("phone", len(matches))
        out = PHONE_RE.sub(_mask_phone, out)

    # 5) 이메일
    matches = EMAIL_RE.findall(out)
    if matches:
        _count("email", len(matches))
        out = EMAIL_RE.sub("****@****", out)

    # 6) 라벨된 성명
    def _name_replace(m: re.Match) -> str:
        _count("name", 1)
        label = m.group(1)
        name = m.group(2)
        return f"{label}: {_mask_name(name)}"

    out = LABELED_NAME_RE.sub(_name_replace, out)

    # 7) 라벨된 사번
    def _empno_replace(m: re.Match) -> str:
        _count("emp_no", 1)
        label = m.group(1)
        emp = m.group(2)
        # 앞 1자 + 나머지 마스킹
        if len(emp) <= 1:
            masked = emp
        else:
            masked = emp[0] + "*" * (len(emp) - 1)
        return f"{label}: {masked}"

    out = LABELED_EMPNO_RE.sub(_empno_replace, out)

    # 8) 라벨된 계좌
    def _acc_replace(m: re.Match) -> str:
        _count("account", 1)
        label = m.group(1)
        return f"{label}: ********"

    out = LABELED_ACCOUNT_RE.sub(_acc_replace, out)

    return MaskResult(out, counts)


def mask_pii_text(text: str) -> str:
    """간단 진입 — 마스킹된 텍스트만 반환."""
    return mask_pii(text).masked


# ─────────────────────────────────────────────────────
# 안전망 — payload dict 안의 모든 string 값 마스킹
# ─────────────────────────────────────────────────────
def mask_pii_in_payload(payload: dict) -> dict:
    """딕셔너리의 모든 string 값에 마스킹 적용 — 재귀.

    LLM 에 전달되는 복잡한 JSON (예: structured_data) 한 번에 처리할 때.
    list / nested dict 도 재귀.
    """
    if not is_enabled():
        return payload

    def _walk(v):
        if isinstance(v, str):
            return mask_pii_text(v)
        if isinstance(v, dict):
            return {k: _walk(val) for k, val in v.items()}
        if isinstance(v, list):
            return [_walk(item) for item in v]
        return v

    return _walk(payload)


# ─────────────────────────────────────────────────────
# 디버그·테스트
# ─────────────────────────────────────────────────────
def summary(result: MaskResult) -> str:
    """`{'name': 2, 'phone': 1}` → '이름2·전화1' 같이 사람용 요약."""
    LABELS = {
        "rrn": "주민번호",
        "card": "카드번호",
        "biz_no": "사업자번호",
        "phone": "전화번호",
        "email": "이메일",
        "name": "이름",
        "emp_no": "사번",
        "account": "계좌",
    }
    parts = [f"{LABELS.get(k, k)} {v}" for k, v in result.counts.items()]
    return " · ".join(parts) if parts else "없음"
