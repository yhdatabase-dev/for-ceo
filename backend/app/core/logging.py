"""공용 로깅 — print(file=sys.stderr) 를 대체하는 구조화 로거.

원칙
- 출력은 기존과 동일하게 stderr (Fly/도커 로그 수집 경로 불변).
- 레벨은 env `CGR_LOG_LEVEL` (기본 INFO). 배포 환경에서 DEBUG 로 올려 추적 가능.
- **로그에 PII 금지** — 본문·추출값을 통째로 기록하지 않는다. 길이·건수·예외 타입 위주.

요청 상관관계 (rid/case)
- 미들웨어가 요청마다 rid 를 발급해 `bind_context(rid=...)`, 케이스를 아는 라우트가
  `bind_context(case=...)` 하면 이후 그 요청·잡의 모든 로그 줄에 `[rid=.. case=..]` 가 붙는다.
- contextvars 기반 — 백그라운드 잡·스레드풀에는 `contextvars.copy_context().run(...)`
  으로 전파한다 (jobs.start_job 이 자동 처리).

사용:
    from cgr.log import get_logger
    log = get_logger(__name__)
    log.info("[추출 완료] %d개 조, %.1fs", n, elapsed)
"""
from __future__ import annotations

import contextvars
import logging
import os
import sys
import uuid

_CONFIGURED = False

# 요청 단위 상관 컨텍스트 — {'rid': ..., 'case': ...}
_LOG_CTX: contextvars.ContextVar[dict] = contextvars.ContextVar("cgr_log_ctx", default={})


def new_request_id() -> str:
    """짧은 요청 ID (8 hex) — 응답 헤더 X-Request-Id 와 로그 상관용."""
    return uuid.uuid4().hex[:8]


def bind_context(**kw: str | None) -> None:
    """현재 컨텍스트에 rid/case 병합 — 빈 값은 무시. 예: bind_context(case=case_id)."""
    cur = dict(_LOG_CTX.get())
    for k, v in kw.items():
        if v:
            cur[k] = str(v)
    _LOG_CTX.set(cur)


def clear_context() -> None:
    _LOG_CTX.set({})


def current_context() -> dict:
    """스냅샷 (테스트·디버그용)."""
    return dict(_LOG_CTX.get())


class _ContextFilter(logging.Filter):
    """모든 레코드에 `.ctx` 속성 주입 — 포맷의 %(ctx)s 자리."""

    def filter(self, record: logging.LogRecord) -> bool:
        c = _LOG_CTX.get()
        parts = []
        if c.get("rid"):
            parts.append(f"rid={c['rid']}")
        if c.get("case"):
            parts.append(f"case={c['case']}")
        record.ctx = f" [{' '.join(parts)}]" if parts else ""
        return True


def setup(level: str | None = None) -> None:
    """루트 'cgr' 로거 1회 구성 — 중복 핸들러 방지."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    lvl_name = (level or os.environ.get("CGR_LOG_LEVEL", "INFO")).upper()
    lvl = getattr(logging, lvl_name, logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(_ContextFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-7s [%(name)s]%(ctx)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger("cgr")
    root.setLevel(lvl)
    root.addHandler(handler)
    root.propagate = False  # uvicorn 루트 로거로 이중 출력 방지
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """모듈용 로거. 'cgr.' 네임스페이스로 묶어 일괄 레벨 제어."""
    setup()
    if not name.startswith("cgr"):
        name = f"cgr.{name}"
    return logging.getLogger(name)
