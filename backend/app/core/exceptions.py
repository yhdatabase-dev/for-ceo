"""도메인 예외 계층 + FastAPI 전역 예외 핸들러.

===============================================================================
원본 대비 주요 변경
===============================================================================
원본
- 도메인 예외 계층 없음. `except Exception` 산재 116건.
- 라우트마다 `raise HTTPException(...)` 을 직접 던짐.
- 결과: 어느 단에서 어떤 원인으로 실패했는지 로그로 추적 어려움.

v2 변경점
- `CgrError` 기저 예외 + 도메인별 하위 예외.
- 각 예외에 HTTP status 자동 매핑 (`http_status` 속성).
- `install_exception_handlers(app)` 로 FastAPI 에 1곳 등록.
- 서비스·리포지토리 계층은 도메인 예외만 던짐 (HTTP 상관 X).
- 라우트는 도메인 예외를 그대로 흘려보냄 (핸들러가 변환).
- 미분류 `Exception` 은 500 으로 반환 + 스택 트레이스는 로그만.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────
# 도메인 예외 계층
# ─────────────────────────────────────────────────────────────
class CgrError(Exception):
    """모든 도메인 예외의 기저.

    Attributes:
        code: 짧은 에러 코드 (프론트가 분기용으로 사용)
        detail: 사용자에게 보여줄 메시지
        http_status: FastAPI 응답 status code (기본 500)
        meta: 부가 정보 (로그·디버그용, 사용자 응답에는 노출 안 함)
    """

    http_status: int = 500
    code: str = "internal_error"

    def __init__(self, detail: str = "", *, meta: dict[str, Any] | None = None) -> None:
        super().__init__(detail or self.code)
        self.detail = detail or self.code
        self.meta = meta or {}


# ── 입력·인증 계열 ─────────────────────────────
class ValidationError(CgrError):
    """요청 파라미터·본문이 유효하지 않음."""

    http_status = 400
    code = "validation_error"


class AuthenticationError(CgrError):
    """인증 실패 (API 키 누락·불일치)."""

    http_status = 401
    code = "auth_failed"


class AuthorizationError(CgrError):
    """권한 부족 (관리자 전용 API 를 일반 키로 접근)."""

    http_status = 403
    code = "forbidden"


class NotFoundError(CgrError):
    """리소스 미존재 (case_id, article_no 등)."""

    http_status = 404
    code = "not_found"


class ConflictError(CgrError):
    """리소스 충돌 (동시 편집·중복 생성)."""

    http_status = 409
    code = "conflict"


# ── 업로드·파싱 계열 ──────────────────────────
class UploadError(CgrError):
    """파일 업로드 실패 (크기 초과·MIME 불일치)."""

    http_status = 400
    code = "upload_failed"


class ParseError(CgrError):
    """문서 파싱 실패 (손상된 파일·미지원 형식)."""

    http_status = 422
    code = "parse_failed"


# ── 외부 시스템 계열 ──────────────────────────
class LLMError(CgrError):
    """외부 LLM 호출 실패 (timeout · API 에러 · 응답 파싱 실패)."""

    http_status = 502
    code = "llm_error"


class PrivacyGateError(CgrError):
    """비식별 게이트웨이 통과 실패 — PII 마스킹 없이 외부로 나가려 함.

    SFR-003 방어선. 이 예외가 뜨면 절대 외부 전송하지 말 것.
    """

    http_status = 500
    code = "privacy_gate_failed"


class DBError(CgrError):
    """DB 접근 실패 (일시 에러 재시도 후에도 실패한 경우)."""

    http_status = 503
    code = "db_error"


class ServiceUnavailableError(CgrError):
    """서비스 사용 불가 — 서버 설정 누락 등으로 요청 처리 불가.

    원본 `cgr/api/auth.py:require_api_key` 가 API_KEY 미설정 시 HTTP 503 을 던지던 것을
    v2 도메인 예외 계층으로 이관.
    """

    http_status = 503
    code = "service_unavailable"


# ── 업무 로직 계열 ────────────────────────────
class RuleError(CgrError):
    """룰 엔진 판정 실패 (슬롯 정의 오류 등)."""

    http_status = 500
    code = "rule_error"


# ─────────────────────────────────────────────────────────────
# FastAPI 전역 핸들러
# ─────────────────────────────────────────────────────────────
async def _cgr_error_handler(request: Request, exc: CgrError) -> JSONResponse:
    """CgrError 전용 핸들러 — status/code/detail 매핑."""
    log.warning(
        "cgr_error",
        extra={
            "path": request.url.path,
            "code": exc.code,
            "status": exc.http_status,
            "meta": exc.meta,
        },
    )
    return JSONResponse(
        status_code=exc.http_status,
        content={
            "error": exc.code,
            "detail": exc.detail,
        },
    )


async def _generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """분류되지 않은 모든 예외 → 500. 스택은 로그만, 사용자에겐 일반 메시지."""
    log.exception(
        "unhandled_error",
        extra={"path": request.url.path},
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "detail": "서버 내부 오류가 발생했습니다.",
        },
    )


def install_exception_handlers(app: FastAPI) -> None:
    """앱 부팅 시 `app.main` 에서 호출."""
    app.add_exception_handler(CgrError, _cgr_error_handler)
    app.add_exception_handler(Exception, _generic_error_handler)
