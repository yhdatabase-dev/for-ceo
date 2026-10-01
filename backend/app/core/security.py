"""인증·인가·마스킹.

===============================================================================
원본 대비 주요 변경
===============================================================================
원본
- `cgr/api/auth.py`: `API_KEY` / `ADMIN_API_KEY` 를 os.environ 직접 조회. header 검증.
- `cgr/pii_mask.py`: 정규식 마스킹 (전화·주민번호·이메일·이름 등).
- `cgr/upload_tracker.py:anon_visitor()`: IP+UA+날짜 → SHA-256.

v2 변경점
- API 키는 `get_settings().server.key/admin_key` 에서 SecretStr 로 관리.
- 인증 실패 시 `AuthenticationError` / `AuthorizationError` 던짐 (핸들러가 401/403 변환).
- PII 마스킹은 `mask_pii_text(text)`, `mask_name(name)`, `hash_pii(text)` 함수화.
- visitor 익명화도 여기에 통합 (`anon_visitor(ip, ua, date_str)`).
- **`ensure_masked_before_llm(text)`** — LLM 호출 전 게이트웨이 (SFR-003 방어선).
"""
from __future__ import annotations

import hashlib
import re
from datetime import date

from fastapi import Request

from app.core.config import get_settings
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    PrivacyGateError,
    ServiceUnavailableError,
)


# ─────────────────────────────────────────────────────────────
# 인증 (API 키 header)
# ─────────────────────────────────────────────────────────────
_API_KEY_HEADER = "X-API-Key"


def require_api_key(request: Request) -> None:
    """일반 API 접근 인증.

    원본 `cgr/api/auth.py:require_api_key` 와 동일 동작:
    - 서버에 API 키 미설정 → HTTP 503 (요청 거부, 배포 실수 방어)
    - 헤더 없음 or 키 불일치 → HTTP 401
    """
    expected = get_settings().server.key.get_secret_value()
    if not expected:
        # 원본: 키 미설정 시 서비스 사용 불가 (보안 사고 방지)
        raise ServiceUnavailableError(
            "API_KEY 미설정 — 운영자에게 문의 "
            "(환경변수 CGR_API_KEY 설정)"
        )
    provided = request.headers.get(_API_KEY_HEADER, "")
    if not provided or provided != expected:
        raise AuthenticationError(
            "유효하지 않은 API Key. X-API-Key 헤더 확인."
        )


def require_admin_key(request: Request) -> None:
    """관리자 API 접근 인증. 실패 시 AuthorizationError."""
    provided = request.headers.get(_API_KEY_HEADER, "")
    expected = get_settings().server.admin_key.get_secret_value()
    if not expected:
        raise AuthorizationError("관리자 API 키가 서버에 설정되지 않았습니다.")
    if provided != expected:
        raise AuthorizationError("관리자 권한이 필요합니다.")


# ─────────────────────────────────────────────────────────────
# PII 마스킹 (외부 LLM 전송 전 필수)
# ─────────────────────────────────────────────────────────────
_RE_PHONE = re.compile(r"01[016789][-\s]?\d{3,4}[-\s]?\d{4}")
_RE_RRN = re.compile(r"\d{6}[-\s]?[1-4]\d{6}")   # 주민등록번호
_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_RE_BIZNO = re.compile(r"\d{3}-?\d{2}-?\d{5}")   # 사업자번호

# 마스킹 마커 (재식별 방지)
_MARK_PHONE = "[PHONE]"
_MARK_RRN = "[RRN]"
_MARK_EMAIL = "[EMAIL]"
_MARK_BIZNO = "[BIZNO]"

# 마스킹 성공 여부 판별용 마커 (게이트웨이가 인식)
_MASKED_MARKERS = (_MARK_PHONE, _MARK_RRN, _MARK_EMAIL, _MARK_BIZNO)


def mask_pii_text(text: str) -> str:
    """텍스트 내 PII 를 마스킹 마커로 치환.

    현재 지원: 휴대전화, 주민번호, 이메일, 사업자번호.
    이름은 별도 `mask_name()` 사용 (컨텍스트가 필요).

    ⚠️ 이 함수는 완벽하지 않다. 외부 LLM 전송 전에는 반드시
       `ensure_masked_before_llm()` 을 통과시켜라.
    """
    if not text:
        return text
    text = _RE_RRN.sub(_MARK_RRN, text)         # RRN 먼저 (전화 오탐 방지)
    text = _RE_PHONE.sub(_MARK_PHONE, text)
    text = _RE_EMAIL.sub(_MARK_EMAIL, text)
    text = _RE_BIZNO.sub(_MARK_BIZNO, text)
    return text


def mask_name(name: str) -> str:
    """한글 이름을 성만 남기고 마스킹 (예: "홍길동" → "홍○○").

    영문 이름 등은 첫 글자만 남기고 마스킹 (예: "John Doe" → "J○○ D○○").
    """
    if not name or len(name) <= 1:
        return name
    if re.match(r"^[가-힣]+$", name):
        return name[0] + "○" * (len(name) - 1)
    # 영문 이름 (공백 단위)
    parts = name.split()
    return " ".join(
        p[0] + "○" * (len(p) - 1) if len(p) > 1 else p for p in parts
    )


def mask_pii_in_payload(payload):
    """dict/list/str payload 안의 모든 문자열 값에 mask_pii_text 재귀 적용.

    원본 `cgr/pii_mask.py:mask_pii_in_payload` 이관 — EC 계열 (analyze/generate/chat)
    이 nested dict 를 그대로 LLM 에 넘길 때 사용.
    """
    if isinstance(payload, str):
        return mask_pii_text(payload)
    if isinstance(payload, dict):
        return {k: mask_pii_in_payload(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [mask_pii_in_payload(v) for v in payload]
    return payload


def hash_pii(text: str) -> str:
    """PII 를 SHA-256 hex 로 단방향 해시 (사업자번호·사원번호 등 식별자 저장용)."""
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────
# 비식별 게이트웨이 (SFR-003 방어선)
# ─────────────────────────────────────────────────────────────
def ensure_masked_before_llm(text: str) -> str:
    """외부 LLM 전송 직전 최종 검증 + 자동 마스킹.

    - `CGR_PII_MASK=false` 로 껐으면 통과 (개발용 예외)
    - 켰으면: 마스킹 실행 → 여전히 미탐지 PII 가 있으면 PrivacyGateError

    이 함수를 통과하지 않은 텍스트를 외부 LLM 에 전송하면 안 된다.
    `app/integrations/llm/client.py` 의 chat() 는 이 게이트를 강제한다.
    """
    if not get_settings().behavior.pii_mask:
        return text
    masked = mask_pii_text(text)
    # 2차 검증: 마스킹 후에도 미탐지 PII 가 있으면 실패
    if _RE_RRN.search(masked) or _RE_PHONE.search(masked):
        raise PrivacyGateError(
            "PII 마스킹 실패 — 외부 전송 차단",
            meta={"markers_found": [m for m in _MASKED_MARKERS if m in masked]},
        )
    return masked


# ─────────────────────────────────────────────────────────────
# 익명 방문자 해시
# ─────────────────────────────────────────────────────────────
def anon_visitor(ip: str, user_agent: str, day: date | None = None) -> str:
    """방문자 익명 해시 = SHA-256(ip + ua + YYYY-MM-DD)[:16].

    - 날짜를 매일 바꾸므로 크로스-데이 트래킹 불가 (개인정보 보호)
    - 하루 안에서는 안정적 (DAU 집계 가능)
    """
    d = (day or date.today()).isoformat()
    raw = f"{ip}|{user_agent}|{d}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
