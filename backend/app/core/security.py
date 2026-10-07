"""API 인증 — X-API-Key 헤더 검증.

키는 환경변수 CGR_API_KEY (app.core.config). 미설정이면 503 으로 막는다(보안 사고 방지).
"""
from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.core.config import get_service_api_key


async def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> str:
    """일반 엔드포인트용 의존성. 잘못된 키 → 401."""
    expected = get_service_api_key()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CGR_API_KEY 미설정 — 운영자에게 문의",
        )
    if not x_api_key or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 API Key. X-API-Key 헤더 확인.",
        )
    return x_api_key
