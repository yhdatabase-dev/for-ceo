"""환경설정 — 모든 설정값은 환경변수로 받고 이 모듈 한 곳에서 읽는다.

값의 출처(앞이 우선):
  1. 프로세스 환경변수 (운영·컨테이너는 이것만 쓴다)
  2. 저장소 루트 .env (로컬 개발용, git 제외. 항목 설명은 .env.example)

.env 의 값은 import 시 os.environ 에 채워 넣는다(이미 있는 값은 덮지 않음).
그래서 아직 환경변수를 직접 읽는 모듈도 같은 값을 보게 된다.
"""
from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _REPO_ROOT / ".env"

DEFAULT_LLM_MODEL = "gpt-5.4-mini"
DEFAULT_EMBED_MODEL = "text-embedding-3-large"
DEFAULT_EMBED_DIM = 1024  # text-embedding-3-large 는 truncate 지원 (default 3072)
DEFAULT_BACKEND_PORT = 18081
DEFAULT_FRONTEND_PORT = 18091
DEFAULT_MAX_UPLOAD_MB = 20


def _load_env_file() -> None:
    """루트 .env 의 KEY=VALUE 를 os.environ 에 채운다. 이미 설정된 환경변수가 우선."""
    if not _ENV_FILE.exists():
        return
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v:
            os.environ.setdefault(k, v)


_load_env_file()


def _env(key: str, default: str = "") -> str:
    return (os.environ.get(key) or "").strip() or default


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key) or default)
    except ValueError:
        return default


def _env_flag(key: str, default: bool) -> bool:
    v = _env(key)
    if not v:
        return default
    return v.lower() not in ("0", "false", "off", "no")


# ─── 실행 환경 ───

def get_environment() -> str:
    """local | dev | prod"""
    return _env("CGR_ENVIRONMENT", "local").lower()


def is_prod() -> bool:
    return get_environment() == "prod"


def get_log_level() -> str:
    return _env("CGR_LOG_LEVEL", "INFO").upper()


def get_backend_port() -> int:
    return _env_int("CGR_BACKEND_PORT", DEFAULT_BACKEND_PORT)


def get_frontend_port() -> int:
    return _env_int("CGR_FRONTEND_PORT", DEFAULT_FRONTEND_PORT)


def get_allowed_origins() -> list[str]:
    """CORS 허용 출처(쉼표 구분). 미설정 시 로컬 프론트 주소."""
    raw = _env("CGR_ALLOWED_ORIGINS")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or [f"http://localhost:{get_frontend_port()}"]


# ─── DB ───

_DB_KEYS = ("CGR_DB_HOST", "CGR_DB_PORT", "CGR_DB_NAME", "CGR_DB_USER", "CGR_DB_PASSWORD")


def get_db_conninfo() -> dict[str, str]:
    """PostgreSQL 접속 정보."""
    info = {k: _env(k) for k in _DB_KEYS}
    missing = [k for k, v in info.items() if not v]
    if missing:
        raise RuntimeError(f"DB 접속 정보 누락: {', '.join(missing)} (환경변수 또는 루트 .env)")
    return {
        "host": info["CGR_DB_HOST"],
        "port": info["CGR_DB_PORT"],
        "dbname": info["CGR_DB_NAME"],
        "user": info["CGR_DB_USER"],
        "password": info["CGR_DB_PASSWORD"],
    }


# ─── 인증 ───

def get_service_api_key() -> str:
    """프론트 서버(BFF)가 X-API-Key 로 보내는 서비스 키."""
    return _env("CGR_API_KEY")


# ─── 파일 · 데이터 ───

def get_data_dir() -> str:
    return _env("CGR_DATA_DIR")


def get_uploads_dir() -> str:
    return _env("CGR_UPLOADS_DIR")


def get_prompts_dir() -> str:
    return _env("CGR_PROMPTS_DIR")


def get_max_upload_mb() -> int:
    return _env_int("CGR_MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_MB)


# ─── LLM ───

def _real_api_key() -> str:
    return _env("OPENAI_API_KEY")


def is_llm_mock() -> bool:
    """키가 없거나 CGR_LLM_MOCK=1 이면 mock 으로 동작한다. 운영(prod)에서는 mock 을 쓰지 않는다."""
    if is_prod():
        return False
    return _env_flag("CGR_LLM_MOCK", False) or not _real_api_key()


def get_api_key(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    if is_llm_mock():
        return "mock-key"
    return _real_api_key()


def get_llm_model(explicit: str | None = None) -> str:
    return explicit or _env("CGR_LLM_MODEL", DEFAULT_LLM_MODEL)


def get_embed_model(explicit: str | None = None) -> str:
    return explicit or _env("CGR_EMBED_MODEL", DEFAULT_EMBED_MODEL)


def get_embed_dim(explicit: int | None = None) -> int:
    return explicit or _env_int("CGR_EMBED_DIM", DEFAULT_EMBED_DIM)


def init_llm() -> None:
    """앱·스크립트 시작 시 1회 호출. mock 이면 내장 가짜 LLM 서버를 띄우고 그쪽으로 연결한다.

    운영(prod)인데 키가 없으면 바로 실패한다.
    """
    if is_prod() and not _real_api_key():
        raise RuntimeError("OPENAI_API_KEY 미설정 — 운영 환경에서는 mock 을 쓰지 않는다")
    if not is_llm_mock():
        return
    from app.integrations.llm import mock

    base_url = mock.start()
    os.environ["OPENAI_BASE_URL"] = base_url  # OpenAI SDK 가 읽는 주소
    os.environ["CGR_DISABLE_CACHE"] = "1"     # 가짜 응답이 LLM 캐시에 남지 않게


def assert_ready() -> None:
    """CLI 스크립트용 — LLM 연결 준비, 실패 시 안내 후 종료."""
    try:
        init_llm()
    except RuntimeError as e:
        from app.core.logging import get_logger

        get_logger(__name__).error(f"[설정 오류] {e}")
        raise SystemExit(2)
