"""비동기 잡 러너 — 긴 LLM 작업을 게이트웨이 타임아웃 없이 처리.

배경:
    Vercel(무료) 함수 60초, 일부 프록시 30초 제한 + Render 무료 cold start 가
    합쳐지면 동기 분석 요청이 끊겨 'Unterminated JSON' 으로 실패한다.

설계:
    - 작업을 백그라운드 데몬 스레드에서 실행하고, 호출자에게는 job_id 만 즉시 반환.
    - 클라이언트는 짧은 GET 폴링으로 결과를 가져온다. 폴링 한 번은 1초 미만이라
      어떤 게이트웨이 타임아웃에도 안 걸림.
    - 결정성: 작업 자체는 기존 서비스(temp=0 + 캐시)를 그대로 호출 — 잡 래퍼는
      실행 위치만 바꿀 뿐 결과를 바꾸지 않는다.

메모리:
    - 단일 인스턴스(MVP) 기준 in-memory dict 로 충분.
    - 새 작업 시작 시 완료된 지 _TTL_SEC 지난 잡은 청소 → 누수 방지.
    - Render 가 재시작되면 진행 중 잡은 사라짐 — 클라이언트는 404 받고 재시도하면 됨.
"""
from __future__ import annotations

import contextvars
import threading
import time
import uuid
from typing import Any, Callable

_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()
_TTL_SEC = 600  # 완료된 잡 보존 시간 (10분)


def _cleanup_locked() -> None:
    """_LOCK 을 이미 잡은 상태에서 호출 — 오래된 완료 잡 제거."""
    now = time.time()
    stale = [
        jid
        for jid, j in _JOBS.items()
        if j["status"] in ("done", "error") and (now - j["finished_at"]) > _TTL_SEC
    ]
    for jid in stale:
        _JOBS.pop(jid, None)


def start_job(fn: Callable[[], Any]) -> str:
    """`fn` 을 백그라운드 스레드에서 실행하고 job_id 반환.

    fn 의 반환값은 result 로, 예외는 error 문자열로 저장된다.
    """
    job_id = uuid.uuid4().hex
    with _LOCK:
        _cleanup_locked()
        _JOBS[job_id] = {
            "status": "pending",
            "result": None,
            "error": None,
            "started_at": time.time(),
            "finished_at": 0.0,
            "elapsed": 0.0,
        }

    # 요청의 로그 상관 컨텍스트(rid/case)를 잡 스레드로 전파 — 제출 시점에 복사.
    ctx = contextvars.copy_context()

    def _run() -> None:
        t0 = time.time()
        try:
            result = ctx.run(fn)
            with _LOCK:
                if job_id in _JOBS:
                    _JOBS[job_id].update(
                        status="done",
                        result=result,
                        finished_at=time.time(),
                        elapsed=round(time.time() - t0, 2),
                    )
        except Exception as e:  # noqa: BLE001 — 어떤 예외든 잡에 기록
            with _LOCK:
                if job_id in _JOBS:
                    _JOBS[job_id].update(
                        status="error",
                        error=f"{type(e).__name__}: {e}",
                        finished_at=time.time(),
                        elapsed=round(time.time() - t0, 2),
                    )

    threading.Thread(target=_run, name=f"job-{job_id[:8]}", daemon=True).start()
    return job_id


def get_job(job_id: str) -> dict[str, Any] | None:
    """잡 상태 스냅샷 반환. 없으면 None."""
    with _LOCK:
        j = _JOBS.get(job_id)
        if j is None:
            return None
        return dict(j)  # 얕은 복사 — 외부 변형 방지
