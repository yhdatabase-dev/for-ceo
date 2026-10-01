"""로깅 설정·요청 컨텍스트.

===============================================================================
원본 대비 주요 변경
===============================================================================
원본 (`cgr/log.py`, 97줄)
- `setup()`: root 로거 없이 'cgr' 네임스페이스에 StreamHandler 부착.
- `get_logger(name)`, `bind_context(**kv)`, `new_request_id()`.
- ContextVar 로 request_id 등 요청 스코프 필드 전파.

v2 변경점
- 네임스페이스 'cgr' → 'app' 로 변경 (패키지명 일치).
- setup() 은 앱 부팅 지점(`main.py`) 에서만 호출 (모듈 import 시 side-effect 금지).
- 로그 레벨은 `get_settings().behavior.log_level` 에서 조회.
- extra 필드에 request_id / trace_id / user_hash 등 자동 주입 (있으면).
- PII 는 로그에 절대 금지 (§리팩계획 R2 · SFR-003) — extra 필드도 마스킹 후 전달.
"""
from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


_LOGGER_NAMESPACE = "app"

# 요청 스코프 컨텍스트 (미들웨어에서 세팅, 모든 로그 라인에 자동 부착)
_ctx_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_ctx_case_uid: ContextVar[str | None] = ContextVar("case_uid", default=None)
_ctx_visitor: ContextVar[str | None] = ContextVar("visitor", default=None)


class _ContextFilter(logging.Filter):
    """모든 로그 레코드에 요청 컨텍스트를 자동 부착."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _ctx_request_id.get() or "-"
        record.case_uid = _ctx_case_uid.get() or "-"
        record.visitor = _ctx_visitor.get() or "-"
        return True


def setup(level: str | None = None) -> None:
    """앱 부팅 시 1회 호출 — 로그 포맷·핸들러 설치.

    원본과 달리 모듈 최상단에서 호출 금지. 반드시 `app.main` 에서만.
    """
    if level is None:
        # 지연 import — core.config 가 무거워질 때 로딩 순서 안전
        from app.core.config import get_settings

        level = get_settings().behavior.log_level

    root = logging.getLogger(_LOGGER_NAMESPACE)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # 중복 부착 방지
    if root.handlers:
        return

    # 공용 포맷터 (stderr · 파일 모두 같은 형식)
    formatter = logging.Formatter(
        fmt=(
            "%(asctime)s | %(levelname)-7s | %(name)s "
            "| req=%(request_id)s case=%(case_uid)s "
            "| %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    ctx_filter = _ContextFilter()

    # ─ 1) stderr 핸들러 (항상) ─────────────────────
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(ctx_filter)
    root.addHandler(stream_handler)

    # ─ 2) 파일 핸들러 (CGR_LOG_FILE 지정 시만) ────
    from app.core.config import get_settings  # 지연 import
    s = get_settings()
    if s.behavior.log_file:
        log_path = Path(s.behavior.log_file)
        # 디렉토리 자동 생성 (예: /app/logs/ 가 없을 때)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            filename=str(log_path),
            maxBytes=s.behavior.log_file_max_bytes,
            backupCount=s.behavior.log_file_backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(ctx_filter)
        root.addHandler(file_handler)

    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    """모듈 로거 팩토리. 관례상 `__name__` 을 넘긴다."""
    return logging.getLogger(name)


# ─── 요청 컨텍스트 (미들웨어·엔진 진입점에서 세팅) ─────────
def new_request_id() -> str:
    """새 요청 ID 생성 후 컨텍스트 저장."""
    rid = uuid.uuid4().hex[:12]
    _ctx_request_id.set(rid)
    return rid


def bind_context(**kv: Any) -> None:
    """현재 요청 컨텍스트에 필드 부착.

    지원 키: request_id, case_uid, visitor.
    (그 외 키는 무시 — 로그 포맷에 반영되지 않음)
    """
    if "request_id" in kv:
        _ctx_request_id.set(kv["request_id"])
    if "case_uid" in kv:
        _ctx_case_uid.set(kv["case_uid"])
    if "visitor" in kv:
        _ctx_visitor.set(kv["visitor"])


def clear_context() -> None:
    """요청 종료 시 컨텍스트 초기화 (미들웨어에서 호출)."""
    _ctx_request_id.set(None)
    _ctx_case_uid.set(None)
    _ctx_visitor.set(None)
