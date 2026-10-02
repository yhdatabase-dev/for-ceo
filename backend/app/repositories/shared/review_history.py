"""검토 이력 영속화 — append-only JSONL.

저장 위치: data/review_history.jsonl
한 줄 = 한 검토 결과:
{
  "ts": "2026-05-08T14:30:00",
  "case_id": "비스코스_24f5b58074fd",
  "filename": "2.비스코스 취업규칙.docx",
  "n_findings": 115,
  "by_status": {"OK": 91, "VIOLATION": 11, "MISSING": 10, ...},
  "by_severity": {"CRITICAL": 3, "HIGH": 8, ...},
  "by_bucket": {"적정": 91, "위반": 11, "누락": 10, "주의": 3, "검토필요": 0},
  "top_violations": ["SLOT_육아휴직_기간_최대1년6개월", ...],
  "report_path": "/output/report_xxx.json"
}

reporter.save_report() 끝에서 append_history() 호출 (try/except 로 검토 통과 보장).
"""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]  # app/repositories/shared/x.py -> backend 루트


def history_path() -> Path:
    p = _project_root() / "data" / "review_history.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def append_history(entry: dict[str, Any]) -> None:
    """JSONL 한 줄 append. 실패해도 예외 전파 안 함 (검토 통과 보장)."""
    try:
        line = json.dumps(entry, ensure_ascii=False)
        with history_path().open("a", encoding="utf-8") as fp:
            fp.write(line + "\n")
    except Exception:
        # 검토 자체는 통과 — 이력 누락은 silent fail
        pass


def read_history(limit: int | None = None) -> list[dict[str, Any]]:
    """이력 전체 읽기. limit 지정 시 마지막 N개만."""
    p = history_path()
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


def stats(history: list[dict[str, Any]] | None = None) -> dict:
    """이력 요약 통계."""
    if history is None:
        history = read_history()
    n = len(history)
    if n == 0:
        return {"n_total": 0}
    avg_violation = sum(h.get("by_bucket", {}).get("위반", 0) for h in history) / n
    avg_missing = sum(h.get("by_bucket", {}).get("누락", 0) for h in history) / n
    # 최근 30일
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()
    recent = sum(1 for h in history if h.get("ts", "") >= cutoff)
    # 빈출 위반 슬롯
    slot_counter: Counter[str] = Counter()
    for h in history:
        for sid in h.get("top_violations", []) or []:
            slot_counter[sid] += 1
    return {
        "n_total": n,
        "n_recent_30d": recent,
        "avg_violation": round(avg_violation, 2),
        "avg_missing": round(avg_missing, 2),
        "top_slots": slot_counter.most_common(10),
    }


def build_entry_from_report(report) -> dict[str, Any]:
    """Report 객체 → 이력 엔트리 dict.

    cgr.models.Report 와 cgr.verdict.classify 사용.
    LLM 호출 없이 메모리 데이터만으로 구성.
    """
    from app.services.wr.verdict import classify

    by_status: Counter[str] = Counter()
    by_severity: Counter[str] = Counter()
    by_bucket: Counter[str] = Counter()
    violations: list[str] = []

    for ar in report.article_results:
        for f in ar.findings:
            by_status[f.status] += 1
            by_severity[f.severity] += 1
            b = classify(f)
            by_bucket[b] += 1
            if b in ("위반", "누락"):
                violations.append(f.slot_id)

    # 현재 활성 LLM 모델 (model A/B 비교용)
    try:
        from app.core.config import get_llm_model
        llm_model = get_llm_model()
    except Exception:
        llm_model = ""

    return {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "case_id": getattr(report, "case_id", ""),
        "filename": (
            os.path.basename(getattr(report, "source_file", ""))
            if getattr(report, "source_file", None)
            else ""
        ),
        "overall_label": getattr(report, "overall_label", ""),
        "llm_model": llm_model,
        "n_findings": sum(by_status.values()),
        "by_status": dict(by_status),
        "by_severity": dict(by_severity),
        "by_bucket": dict(by_bucket),
        "top_violations": violations[:20],
        "report_path": "",  # save_report 가 채움
    }
