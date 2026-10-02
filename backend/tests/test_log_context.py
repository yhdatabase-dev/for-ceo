"""요청 상관 로깅(rid/case) 테스트 — 관측성: 로그를 케이스 단위로 꿰는 능력.

보증하는 것
- bind_context 로 묶은 rid/case 가 모든 로그 레코드에 [rid=.. case=..] 로 붙는다.
- 백그라운드 잡(jobs.start_job)·스레드풀에도 컨텍스트가 전파된다.
- 미들웨어가 요청마다 X-Request-Id 를 발급한다.
"""
from __future__ import annotations

import contextvars
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core import logging as cgr_log


@pytest.fixture(autouse=True)
def _clean_ctx():
    cgr_log.clear_context()
    yield
    cgr_log.clear_context()


def _record() -> logging.LogRecord:
    return logging.LogRecord("cgr.test", logging.INFO, __file__, 1, "msg", None, None)


# ─── 필터 — ctx 주입 ───
def test_filter_injects_rid_and_case():
    cgr_log.bind_context(rid="abc12345", case="CASE-9")
    rec = _record()
    assert cgr_log._ContextFilter().filter(rec) is True
    assert rec.ctx == " [rid=abc12345 case=CASE-9]"


def test_filter_empty_context_is_blank():
    rec = _record()
    cgr_log._ContextFilter().filter(rec)
    assert rec.ctx == ""


def test_bind_merges_and_ignores_empty():
    cgr_log.bind_context(rid="r1")
    cgr_log.bind_context(case="c1", rid=None)  # None 은 기존 rid 유지
    assert cgr_log.current_context() == {"rid": "r1", "case": "c1"}
    cgr_log.bind_context(case="")  # 빈 문자열도 무시
    assert cgr_log.current_context()["case"] == "c1"


def test_real_handler_formats_ctx():
    """실제 등록된 핸들러(필터+포맷터)가 [rid=..] 를 포함한 한 줄을 만든다."""
    cgr_log.setup()
    handler = logging.getLogger("cgr").handlers[0]
    cgr_log.bind_context(rid="fmt1")
    rec = logging.LogRecord(
        "cgr.tests.fmt", logging.INFO, __file__, 1, "포맷 확인 %d", (1,), None
    )
    for f in handler.filters:
        f.filter(rec)
    line = handler.format(rec)
    assert "[rid=fmt1]" in line and "포맷 확인 1" in line


# ─── 전파 — 잡·스레드풀 ───
def test_start_job_propagates_context():
    from app.core import jobs

    cgr_log.bind_context(rid="jobrid", case="JOB-CASE")
    job_id = jobs.start_job(lambda: cgr_log.current_context())
    for _ in range(100):
        j = jobs.get_job(job_id)
        if j and j["status"] in ("done", "error"):
            break
        time.sleep(0.02)
    assert j["status"] == "done", j.get("error")
    assert j["result"] == {"rid": "jobrid", "case": "JOB-CASE"}


def test_threadpool_copy_context_pattern():
    """run.py 의 submit(copy_context().run, fn) 패턴이 컨텍스트를 나른다."""
    cgr_log.bind_context(case="POOL-1")
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [
            ex.submit(contextvars.copy_context().run, cgr_log.current_context)
            for _ in range(3)
        ]
        results = [f.result() for f in futs]
    assert all(r.get("case") == "POOL-1" for r in results)


def test_plain_thread_does_not_leak_context():
    """전파 장치 없는 새 스레드는 컨텍스트가 비어야 정상 (누수 방지 확인)."""
    import threading

    cgr_log.bind_context(case="LEAK?")
    seen: dict = {"ctx": None}

    def _t():
        seen["ctx"] = cgr_log.current_context()

    th = threading.Thread(target=_t)
    th.start(); th.join()
    assert seen["ctx"] == {}


# ─── 미들웨어 — X-Request-Id ───
def test_middleware_sets_request_id():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        r1 = c.get("/health")
        r2 = c.get("/health")
    rid1, rid2 = r1.headers.get("X-Request-Id"), r2.headers.get("X-Request-Id")
    assert rid1 and len(rid1) == 8
    assert rid1 != rid2  # 요청마다 새 ID


# ─── 소스 린트 — print 스타일 인자가 로거에 남는 사고 방지 ───
def test_no_print_style_kwargs_in_log_calls():
    """print(..., file=sys.stderr) → log.info(...) 전환 시 file= 인자가 남으면
    실행 시점에 TypeError: Logger._log() got an unexpected keyword argument 'file'.
    테스트가 못 잡는 실전용 경로에서 터지므로 (실사고: 취업규칙 검토 71% 중단)
    소스 수준에서 차단한다."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app"
    # log.<level>( ... file= ... ) — 호출 괄호 안에서만 매치 (중첩 1단계 허용)
    pat = re.compile(
        r"log\.(debug|info|warning|error|exception|critical)\s*\("
        r"(?:[^()]|\([^()]*\))*?\bfile\s*=",
        re.S,
    )
    offenders = []
    for p in root.rglob("*.py"):
        if pat.search(p.read_text(encoding="utf-8")):
            offenders.append(str(p.relative_to(root)))
    assert not offenders, f"log 호출에 print 스타일 file= 인자 잔존: {offenders}"
