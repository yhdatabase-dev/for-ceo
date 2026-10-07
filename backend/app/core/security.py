#
# API 인증 — X-API-Key 헤더 검증.
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.05.28      kimzion77   최초 생성
# 2026.10.02      이시영      구조 이행 (backend/cgr → backend/app)
# 2026.10.07      이시영      환경설정 통합 (루트 .env·config.py), mock LLM 추가
# 2026.10.07      이시영      검토번호 서버 발급, 변경 사유 주석 추가
#
# Author: kimzion77
# Since: 2026.05.28
#
"""API 인증 — X-API-Key 헤더 검증.

키는 환경변수 CGR_API_KEY (app.core.config). 미설정이면 503 으로 막는다(보안 사고 방지).

개발표준정의서 비밀 관리: API 키는 환경변수로 주입한다
(기존: 환경변수 API_KEY 또는 .streamlit/secrets.toml, 관리자 키 별도 — 관리자 기능은 삭제).
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
