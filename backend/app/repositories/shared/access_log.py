"""방문·서비스 사용 로그 — append-only JSONL.

저장 위치: data/access_log.jsonl
용도:
  - 검토 앱(8501) / 관리자 앱(8502) / 향후 근로계약서·임금명세서 앱 방문 추적
  - 서비스(취업규칙/근로계약서/임금명세서) 별 사용량 집계
  - 일자별 활동·세션 카운트

한 줄 = 1 이벤트:
{
  "ts": "2026-05-09T14:30:00",
  "service": "취업규칙" | "근로계약서" | "임금명세서" | "관리자",
  "action": "visit" | "review" | "edit" | ...,
  "session_id": "<streamlit session>" (선택),
  "meta": {...}
}

서비스 라벨은 호출 측에서 명시 (기본: "취업규칙").
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


SERVICE_OPTIONS = ["취업규칙", "근로계약서", "임금명세서", "관리자"]
ACTION_OPTIONS = ["visit", "review", "edit", "login", "settings_change", "slot_edit", "cache_clear"]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]  # app/repositories/shared/x.py -> backend 루트


def log_path() -> Path:
    p = _project_root() / "data" / "access_log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def log_event(
    service: str = "취업규칙",
    action: str = "visit",
    session_id: str | None = None,
    meta: dict | None = None,
) -> None:
    """이벤트 1건 append. 실패해도 silent."""
    try:
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "service": service,
            "action": action,
        }
        if session_id:
            entry["session_id"] = session_id
        if meta:
            entry["meta"] = meta
        with log_path().open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_events(limit: int | None = None) -> list[dict[str, Any]]:
    """전체 이벤트 읽기. limit 시 마지막 N개."""
    p = log_path()
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    with p.open(encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    if limit:
        rows = rows[-limit:]
    return rows


def stats(events: list[dict] | None = None) -> dict:
    """방문 통계 요약."""
    if events is None:
        events = read_events()
    from collections import Counter

    n = len(events)
    if n == 0:
        return {"n_total": 0}

    # 서비스별 카운트
    by_service: Counter = Counter()
    # 액션별 카운트
    by_action: Counter = Counter()
    # 일자별 카운트
    by_date: Counter = Counter()
    # 세션 고유 수
    sessions: set[str] = set()

    cutoff_7d = (datetime.now() - timedelta(days=7)).isoformat()
    cutoff_30d = (datetime.now() - timedelta(days=30)).isoformat()
    n_7d = 0
    n_30d = 0

    for e in events:
        by_service[e.get("service", "")] += 1
        by_action[e.get("action", "")] += 1
        d = (e.get("ts") or "")[:10]
        if d:
            by_date[d] += 1
        sid = e.get("session_id")
        if sid:
            sessions.add(sid)
        ts = e.get("ts", "")
        if ts >= cutoff_7d:
            n_7d += 1
        if ts >= cutoff_30d:
            n_30d += 1

    return {
        "n_total": n,
        "n_7d": n_7d,
        "n_30d": n_30d,
        "n_sessions": len(sessions),
        "by_service": dict(by_service),
        "by_action": dict(by_action),
        "by_date": dict(by_date),
    }


def truncate(keep_last: int = 10000) -> int:
    """오래된 로그 정리. 최근 N건만 유지. (운영 중 자동 호출 권장)

    Returns: 제거된 라인 수
    """
    p = log_path()
    if not p.exists():
        return 0
    events = read_events()
    if len(events) <= keep_last:
        return 0
    removed = len(events) - keep_last
    kept = events[-keep_last:]
    tmp = p.with_suffix(".tmp")
    tmp.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in kept) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, p)
    return removed
