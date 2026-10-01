"""앱 팩토리 — 미들웨어·라우터·핸들러 조립.

===============================================================================
원본 대비 주요 변경
===============================================================================
원본 (`cgr/api/main.py`)
- FastAPI 앱 정의 + 라우터 include + 미들웨어 + startup·shutdown 이 한 파일에 섞임.
- CORS origin 은 os.environ 직접 조회.

v2
- 조립만 담당 (라우터는 `api/routers/router.py`, 예외는 `core/exceptions.py`).
- 로거·설정·DB 엔진 초기화는 부팅 시점에만 (모듈 import 시 side-effect 금지).
- CORS/에러/요청컨텍스트 미들웨어를 순서대로 설치.

부팅 순서 (create_app):
1. 설정 로드 & 필수값 검증 (assert_ready)
2. 로거 세팅
3. FastAPI 앱 생성 + lifespan (엔진 초기화/종료)
4. 미들웨어 (CORS → 요청컨텍스트)
5. 예외 핸들러
6. 라우터 include
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.routers.router import api_router
from app.core.config import assert_ready, get_settings
from app.core.database import close_pool, get_pool
from app.core.exceptions import install_exception_handlers
from app.core.logging import bind_context, get_logger, new_request_id
from app.core.logging import setup as setup_logging


# ─────────────────────────────────────────────────────────────
# Lifespan — 엔진 초기화 / 종료
# ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 부팅·종료 훅.

    - startup: 필수 시크릿 검증 · 로거 세팅 · DB 엔진 lazy init.
    - shutdown: DB 풀 정리.
    """
    assert_ready()
    setup_logging()
    log = get_logger(__name__)
    log.info("app.startup", extra={"env": "prod"})
    # DB 풀 lazy init (첫 요청 대기 전에 미리 warm-up)
    get_pool()
    yield
    log.info("app.shutdown")
    close_pool()


# ─────────────────────────────────────────────────────────────
# 앱 팩토리
# ─────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    """FastAPI 앱 인스턴스 생성.

    uvicorn 진입점:
        uvicorn app.main:app --host 0.0.0.0 --port 8503
    또는 workers>1:
        uvicorn app.main:app --workers 4 (env UVICORN_WORKERS=4 도 갱신 필수)
    """
    s = get_settings()

    app = FastAPI(
        title="for-ceo v2 API",
        version="2.0.0",
        description="고용노동부 영세사업장 자율점검 백엔드 (v2 레이어드).",
        lifespan=lifespan,
    )

    # CORS — 프론트(BFF) 에서 오는 요청만 허용
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.server.origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # gzip 응답 압축 (판정 JSON 이 크면 유효)
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    # ─── 보안 응답 헤더 (OWASP A05 / 국정원 점검: MIME 스니핑·클릭재킹 방지) ───
    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return resp

    # ─── 요청 상관 컨텍스트 — 요청마다 rid 발급, 이후 모든 로그에 자동 부착 ───
    # case_uid 를 아는 라우트가 bind_context(case_uid=...) 를 추가하면 로그에 함께 붙음.
    # 백그라운드 잡 도입 시 contextvars 복사로 같은 rid 를 이어받게 할 것.
    @app.middleware("http")
    async def _request_context(request: Request, call_next):
        rid = new_request_id()
        bind_context(request_id=rid)                    # v2 로거 규약 (키 이름 request_id 유지)
        resp = await call_next(request)
        resp.headers.setdefault("X-Request-Id", rid)    # 사용자 문의 시 로그 대조용
        return resp

    # 예외 핸들러 등록 (CgrError → status 매핑 + 일반 Exception → 500)
    install_exception_handlers(app)

    # 라우터
    app.include_router(api_router)

    return app


# uvicorn 진입점
app = create_app()
