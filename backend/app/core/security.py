"""API 인증 — X-API-Key 헤더 검증.

키 우선순위:
  1. 환경변수 API_KEY (운영용 권장)
  2. .streamlit/secrets.toml 의 api_key (단일 소스 재사용)
  3. 모두 없으면 API 응답 503 (보안 사고 방지)

관리자 API 는 별도 ADMIN_API_KEY 권장 — 분리 안 했으면 동일 키 사용.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Header, HTTPException, status


def _load_secrets() -> dict:
    """`.streamlit/secrets.toml` 안전 로드. tomllib 사용."""
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        return {}
    p = Path(__file__).resolve().parents[2] / ".streamlit" / "secrets.toml"
    if not p.exists():
        return {}
    try:
        return tomllib.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve_api_key() -> str | None:
    """일반 API 키."""
    env = os.environ.get("API_KEY")
    if env:
        return env
    s = _load_secrets()
    return s.get("api_key")


def _resolve_admin_key() -> str | None:
    """관리자 전용 키. 미설정 시 일반 키와 동일하게 처리."""
    env = os.environ.get("ADMIN_API_KEY")
    if env:
        return env
    s = _load_secrets()
    return s.get("admin_api_key") or _resolve_api_key()


async def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> str:
    """일반 엔드포인트용 의존성. 잘못된 키 → 401."""
    expected = _resolve_api_key()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API_KEY 미설정 — 운영자에게 문의 (환경변수 API_KEY 또는 .streamlit/secrets.toml 의 api_key)",
        )
    if not x_api_key or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 API Key. X-API-Key 헤더 확인.",
        )
    return x_api_key


async def require_admin_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> str:
    """관리자 엔드포인트용 의존성. 슬롯 편집·캐시 비우기 등."""
    expected = _resolve_admin_key()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_API_KEY 미설정",
        )
    if not x_api_key or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="관리자 권한 필요. 유효한 X-API-Key 헤더 필요.",
        )
    return x_api_key
