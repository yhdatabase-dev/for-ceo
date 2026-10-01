"""통합 환경설정 — pydantic-settings v2 BaseSettings.

===============================================================================
원본 대비 주요 변경
===============================================================================
원본 (for-ceo)
- `cgr/config.py` : `get_api_key()`, `get_llm_model()`, `get_embed_model()`,
                    `get_embed_dim()` 4개 함수. 3단계 fallback (env → secrets.toml → DEFAULT).
- `cgr/datadir.py`: `data_dir()`, `prompts_dir()`, `uploads_dir()`, `events_db_path()`.
- `cgr/db/__init__.py`: `os.environ.get("CGR_MASTER_DB")` 직접 조회.
- `cgr/api/main.py`: `os.environ.get("CGR_ALLOWED_ORIGINS")` 직접 조회.
- `cgr/api/auth.py`: `os.environ.get("API_KEY")` / `ADMIN_API_KEY`.
→ env 조회가 파일 6곳 이상에 산재. 부팅 시점 검증 없음. 오타 방지 없음.

v2 (여기)
- 모든 env 를 이 파일 한 곳에서 정의 (Pydantic BaseSettings).
- 도메인별 서브클래스로 분리 (Server / DB / LLM / Data / Behavior).
- 시크릿은 `SecretStr` → 로그·repr 자동 마스킹.
- `@lru_cache` 팩토리 → 프로세스 싱글턴, 부팅 시점 1회 파싱.
- `.env` 자동 로드 (pydantic-settings 표준).
- `assert_ready()` 로 필수 시크릿 누락 시 부팅 실패.

===============================================================================
사용법
===============================================================================
    from app.core.config import get_settings

    s = get_settings()
    dsn = s.db.dsn.get_secret_value()          # SecretStr → 원문
    api_key = s.llm.api_key.get_secret_value()
    port = s.server.port

값 우선순위 (pydantic-settings 표준):
    1. 함수 인자 override (테스트에서 monkeypatch 후 cache_clear)
    2. 환경변수 (셸 · 도커 env_file)
    3. .env 파일 (같은 폴더)
    4. Field default
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = ".env"


def _cfg(prefix: str) -> SettingsConfigDict:
    """도메인별 SettingsConfigDict 생성 헬퍼.

    env_prefix: 이 클래스 모든 필드 앞에 붙어서 env 이름 조립.
                예) env_prefix="CGR_PG_" + field_name="dsn" → env "CGR_PG_DSN"
    case_sensitive=False: 대소문자 무시 (관례상 env 는 전부 대문자).
    extra="ignore": 정의되지 않은 env 는 무시 (오타 감지는 별도 단계에서).
    """
    return SettingsConfigDict(
        env_prefix=prefix,
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# ─────────────────────────────────────────────────────────────
# 1) 서버 (FastAPI · Uvicorn) — env prefix: CGR_API_
# ─────────────────────────────────────────────────────────────
class ServerSettings(BaseSettings):
    """FastAPI 서버 바인딩·CORS·인증 키.

    원본 대비:
    - 원본은 uvicorn CLI 로 호스트·포트 지정 (`launch_api.py`). 여기선 env 로 통일.
    - 원본 `CGR_ALLOWED_ORIGINS` (쉼표 구분) → `CGR_API_ALLOWED_ORIGINS` (prefix 통일).
    - 원본 `API_KEY` / `ADMIN_API_KEY` → `CGR_API_KEY` / `CGR_API_ADMIN_KEY` (SecretStr).
    - `workers` 는 DB 풀 크기 계산에 필수 (다른 프로젝트 관례상 UVICORN_WORKERS 로 별칭).
    """

    model_config = _cfg("CGR_API_")

    host: str = Field(default="0.0.0.0", description="바인딩 호스트")
    port: int = Field(default=8503, description="바인딩 포트")

    # CORS 허용 origin (쉼표 구분 문자열로 받아 리스트로 가공)
    allowed_origins: str = Field(
        default="http://localhost:3000",
        description="허용 origin 쉼표 구분 목록",
    )

    # 인증 키
    key: SecretStr = Field(default=SecretStr(""), description="일반 API 키")
    admin_key: SecretStr = Field(default=SecretStr(""), description="관리자 API 키")

    # uvicorn --workers 값 (DB 풀 크기 계산용). alias 로 prefix 우회
    workers: int = Field(default=1, alias="UVICORN_WORKERS", description="워커 수")

    @property
    def origins_list(self) -> list[str]:
        """CORS 미들웨어에 넘길 리스트 형태."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


# ─────────────────────────────────────────────────────────────
# 2) 데이터베이스 (PostgreSQL) — env prefix: CGR_PG_
# ─────────────────────────────────────────────────────────────
class DBSettings(BaseSettings):
    """PostgreSQL 접속·풀·재시도.

    원본 대비:
    - 원본은 SQLite 파일 경로만 관리 (`CGR_MASTER_DB`, `CGR_EVENTS_DB`).
    - v2 는 PG DSN 하나로 통합. 스키마 분리는 SQLAlchemy 에서 처리.
    - 풀 크기는 워커 수를 감안한 자동 계산 (원본에는 풀 자체가 없음).
    - retry 정책 신설 — 일시 네트워크 오류 자동 재시도.
    """

    model_config = _cfg("CGR_PG_")

    dsn: SecretStr = Field(
        default=SecretStr(""),
        description="PostgreSQL DSN (postgresql://user:pw@host:port/db)",
    )
    total_max_conn: int = Field(
        default=50,
        description="PG 전체 허용 커넥션 상한 (모든 워커 합산)",
    )
    pool_min_per_worker: int = Field(
        default=1, description="워커당 풀 최소 크기"
    )
    retry_max_attempts: int = Field(default=3, description="일시 에러 재시도 횟수")
    retry_delay_seconds: float = Field(default=0.5, description="재시도 간 대기(초)")


# ─────────────────────────────────────────────────────────────
# 3) LLM (OpenAI) — env prefix: OPENAI_
# ─────────────────────────────────────────────────────────────
class LLMSettings(BaseSettings):
    """OpenAI API 키·모델·임베딩 설정.

    원본 대비:
    - 원본은 `cgr/config.py` 함수 4개로 지연 조회.
    - v2 는 인스턴스 필드로 정적 접근 + SecretStr 마스킹.
    - env 이름은 원본 그대로 (OPENAI_*) → 기존 배포 스크립트 호환.
    """

    model_config = _cfg("OPENAI_")

    api_key: SecretStr = Field(default=SecretStr(""), description="OpenAI API 키")
    model: str = Field(default="gpt-5.4-mini", description="채팅/추론 모델")
    embedding_model: str = Field(
        default="text-embedding-3-large", description="임베딩 모델"
    )
    embedding_dim: int = Field(
        default=1024,
        description="임베딩 차원 (text-embedding-3-large 는 truncate 지원)",
    )


# ─────────────────────────────────────────────────────────────
# 4) 데이터 디렉토리 (파일 저장) — env prefix: CGR_
# ─────────────────────────────────────────────────────────────
class DataDirSettings(BaseSettings):
    """가변 데이터 디렉토리 — 업로드 원본 등 여전히 파일 시스템에 남는 것.

    원본 대비:
    - 원본 `data/prompts/` (프롬프트 파일) → v2 는 PG `cgr_admin.prompt` 로 이관.
    - 원본 `data/slots/*.yaml` → v2 는 PG `cgr_master.check_item` 등으로 이관.
    - 원본 `data/master.db`, `data/events.db` → v2 는 PG.
    - 남는 것: 업로드 원본 파일, 리포트 아카이브 등.
    """

    model_config = _cfg("CGR_")

    data_dir: Path = Field(
        default=Path("./data"),
        description="가변 데이터 루트 (운영: /data 영구 볼륨)",
    )
    uploads_dir: Optional[Path] = Field(
        default=None,
        description="업로드 파일 저장 경로 (미지정 시 {data_dir}/uploads)",
    )

    def resolved_uploads_dir(self) -> Path:
        return self.uploads_dir or (self.data_dir / "uploads")


# ─────────────────────────────────────────────────────────────
# 5) 동작 스위치 — env prefix: CGR_
# ─────────────────────────────────────────────────────────────
class BehaviorSettings(BaseSettings):
    """런타임 동작 토글.

    원본 대비:
    - 원본 `CGR_LOG_LEVEL`, `CGR_DISABLE_CACHE`, `CGR_PII_MASK` 그대로 이관.
    - `CGR_PII_MASK=true` 는 운영에서 반드시 유지 (SFR-003 비식별 게이트웨이).
    """

    model_config = _cfg("CGR_")

    log_level: str = Field(default="INFO", description="DEBUG|INFO|WARNING|ERROR")
    disable_cache: bool = Field(
        default=False, description="LLM 응답 캐시 비활성 (테스트 격리용)"
    )
    pii_mask: bool = Field(
        default=True,
        description="외부 LLM 호출 전 PII 마스킹 (프로덕션은 항상 True)",
    )
    # 파일 저장 (선택 — 없으면 stderr 만)
    # 도커 배포 시: 호스트 볼륨(./logs)에 마운트된 컨테이너 경로 지정
    #   예: CGR_LOG_FILE=/app/logs/app.log  +  volume ./logs:/app/logs
    # 값이 있으면 stderr + 파일 둘 다에 씀 (dual write)
    log_file: str = Field(
        default="",
        description="로그 파일 경로 (빈 문자열이면 파일 저장 안 함)",
    )
    log_file_max_bytes: int = Field(
        default=20 * 1024 * 1024,   # 20MB
        description="로그 파일 하나 최대 크기 (byte)",
    )
    log_file_backup_count: int = Field(
        default=10,
        description="회전 후 보관할 백업 파일 개수 (총 용량 = max_bytes × count)",
    )


# ─────────────────────────────────────────────────────────────
# 최상위 조립
# ─────────────────────────────────────────────────────────────
class AppSettings(BaseSettings):
    """전체 앱 설정 — 서브 도메인 조립.

    호출: `get_settings().<domain>.<field>`
    예:   `get_settings().db.dsn.get_secret_value()`
          `get_settings().server.port`
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    server: ServerSettings = Field(default_factory=ServerSettings)
    db: DBSettings = Field(default_factory=DBSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    data: DataDirSettings = Field(default_factory=DataDirSettings)
    behavior: BehaviorSettings = Field(default_factory=BehaviorSettings)


# ─────────────────────────────────────────────────────────────
# 팩토리 (프로세스 싱글턴)
# ─────────────────────────────────────────────────────────────
@lru_cache
def get_settings() -> AppSettings:
    """싱글턴 설정 인스턴스.

    테스트에서 env 를 바꾸고 재파싱하려면 `get_settings.cache_clear()`.
    """
    return AppSettings()


# ─────────────────────────────────────────────────────────────
# 필수 시크릿 검증 (앱 부팅 시 호출)
# ─────────────────────────────────────────────────────────────
def assert_ready() -> None:
    """필수 시크릿 누락 시 명시적 실패.

    원본 `cgr/config.py:assert_ready()` 는 OpenAI 키만 검사했음.
    v2 는 PG DSN 도 검사 (PG 없이는 부팅 자체가 무의미).
    """
    s = get_settings()
    missing: list[str] = []
    if not s.llm.api_key.get_secret_value():
        missing.append("OPENAI_API_KEY")
    if not s.db.dsn.get_secret_value():
        missing.append("CGR_PG_DSN")
    if missing:
        raise RuntimeError(
            f"[설정 오류] 필수 환경변수 누락: {', '.join(missing)}. "
            f".env 또는 셸 환경변수로 설정하세요."
        )
