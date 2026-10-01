"""라우터 집약 — include_router 는 오직 이 파일에서만.

===============================================================================
원본 대비 주요 변경
===============================================================================
원본 (`cgr/api/main.py`)
- FastAPI 앱 안에서 12개 라우터를 직접 include_router.
- 앱 팩토리와 라우터 집약이 한 파일에 섞임.

v2
- 앱 팩토리 (`main.py`) 는 조립만.
- 라우터 집약은 이 파일에서. `include_router` 유일점.
- prefix `/api/v1` 통일 (버전 관리 여지).

도메인 라우터
- review: 취업규칙 (WR)
- ec:     근로계약서 (EC)
- guide:  고용노동 가이드
- admin:  관리자 (2개 이상 도메인 공유)
- shared: history, master_db, topics, track 등
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import health
from app.api.routers.review import router as review_router
from app.api.routers.ec import router as ec_router
from app.api.routers.guide import router as guide_router
from app.api.routers.admin import router as admin_router
from app.api.routers.shared import router as shared_router


api_router = APIRouter()

# 헬스체크는 prefix 없이 (`/health`)
api_router.include_router(health.router)

# 도메인 라우터 — 각 __init__.py 에서 sub-router 조합
_V1 = "/api/v1"
api_router.include_router(review_router, prefix=_V1)
api_router.include_router(ec_router, prefix=_V1)
api_router.include_router(guide_router, prefix=_V1)
api_router.include_router(admin_router, prefix=_V1)
api_router.include_router(shared_router, prefix=_V1)
