"""취업규칙 검토 AI — FastAPI 백엔드 진입점.

실행:
    python launch_api.py
    # 또는
    uvicorn app.main:app --port 8503 --host 127.0.0.1

OpenAPI 문서: http://127.0.0.1:8503/docs (Swagger UI)
              http://127.0.0.1:8503/redoc (ReDoc)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# cgr 패키지 import 보장
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.routers.router import api_router
from app.schemas.common import HealthResponse
from app.core.logging import get_logger, setup as setup_logging

setup_logging()  # 'cgr' 네임스페이스 로거 stderr 구성 (CGR_LOG_LEVEL, 기본 INFO)
log = get_logger(__name__)


app = FastAPI(
    title="취업규칙 검토 AI API",
    description=(
        "취업규칙·근로계약서 검토 백엔드 REST API.\n\n"
        "**인증**: 모든 보호 엔드포인트는 `X-API-Key` 헤더 필요.\n\n"
        "**핵심 엔드포인트**:\n"
        "- `POST /api/v1/review` — 사업장 파일 업로드 + 검토 실행\n"
        "- `GET /api/v1/history` — 검토 이력"
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


# ─── CORS — 허용 출처 화이트리스트 (OWASP A05: 와일드카드+credentials 금지) ───
# 실제 호출은 프론트 BFF(서버사이드)라 CORS 가 필수는 아니지만, 보안 점검 기준상
# 출처를 env(CGR_ALLOWED_ORIGINS, 콤마구분)로 제한한다. 미설정 시 로컬·운영 도메인 기본.
_origins_env = os.environ.get("CGR_ALLOWED_ORIGINS", "").strip()
_allowed_origins = [o.strip() for o in _origins_env.split(",") if o.strip()] or [
    "http://localhost:3000",
    "https://moellab.info",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,  # 인증은 X-API-Key 헤더 — 쿠키 미사용이라 credentials 불요
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization"],
    expose_headers=["X-Process-Time"],
)

# ─── gzip 응답 압축 — 분석 결과 등 큰 JSON 응답을 60-70% 줄여 전송 시간 단축 ───
# minimum_size: 이보다 작은 응답은 압축 오버헤드만 들어서 패스. 1KB 가 합리적 임계.
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)


# ─── 보안 응답 헤더 (OWASP A05 / 국정원 점검: MIME 스니핑·클릭재킹 방지) ───
@app.middleware("http")
async def _security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return resp


# ─── 요청 상관 컨텍스트 — 요청마다 rid 발급, 이후 모든 로그에 [rid=..] 자동 부착 ───
# case_id 를 아는 라우트가 bind_context(case=...) 를 추가하면 [rid=.. case=..] 로 확장.
# 백그라운드 잡(jobs.start_job)은 contextvars 복사로 같은 rid/case 를 이어받는다.
@app.middleware("http")
async def _request_context(request, call_next):
    from app.core.logging import bind_context, new_request_id

    rid = new_request_id()
    bind_context(rid=rid)
    resp = await call_next(request)
    resp.headers.setdefault("X-Request-Id", rid)  # 사용자 문의 시 로그 대조용
    return resp


# ─── 라우터 등록 (prefix /api/v1) ──────────
API_PREFIX = "/api/v1"
app.include_router(api_router, prefix=API_PREFIX)


# ─── startup 유지보수 — 업로드 보관기간 정리(배포/재시작 시 1회) ───
@app.on_event("startup")
async def _startup_maintenance() -> None:
    try:
        from app.repositories.shared import analytics, setting as settings_store

        days = int(settings_store.get("upload_retention_days", 30) or 30)
        n = analytics.cleanup_old_uploads(days)
        log.info("startup 정리 — 보관기간 %d일 초과 업로드 %s건 삭제", days, n)
    except Exception as e:
        log.warning("startup 정리 실패 (서비스는 계속): %s: %s", type(e).__name__, e)


# ─── 헬스 체크 (인증 불요) ──────────────────
@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["health"],
    summary="헬스 체크 (인증 불필요)",
)
async def health() -> HealthResponse:
    """서비스 상태 확인. 인증 없이 호출 가능 — 로드밸런서·모니터링용."""
    services = {}
    try:
        from app.repositories.wr.master import _resolve_path
        services["master_db"] = str(_resolve_path().name)
    except Exception as e:
        services["master_db"] = f"error: {e}"
    try:
        from app.repositories.wr import slot as slot_writer
        parsed = slot_writer.load_raw()
        services["slots"] = f"{len(parsed.get('slots') or [])}개"
    except Exception as e:
        services["slots"] = f"error: {e}"
    try:
        from app.integrations.llm import cache as llm_cache
        s = llm_cache.stats()
        services["llm_cache"] = f"{s.get('entries', 0)}개"
    except Exception as e:
        services["llm_cache"] = f"error: {e}"

    return HealthResponse(status="ok", version="1.0.0", services=services)


# ─── Warm-up — Render 무료 sleep 방지용 초경량 ping ────────
# 인증 불필요 + 즉시 응답. BFF 경유(`/api/cgr/warmup`)로 호출 가능하게 API_PREFIX 안에 둠.
# UptimeRobot, 프론트 진입 시 fire-and-forget 핑 등에서 사용.
@app.get(
    f"{API_PREFIX}/warmup",
    tags=["health"],
    summary="warm-up (초경량 ping)",
    include_in_schema=False,
)
async def warmup() -> dict[str, str]:
    return {"status": "warm"}


@app.get("/", include_in_schema=False)
async def root():
    """루트 — 문서 페이지로 안내."""
    return {
        "service": "취업규칙 검토 AI API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
    }
