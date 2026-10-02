"""사용량·업로드 이벤트 저장소 — events.db (가변 데이터 디렉터리 / Fly 볼륨).

- visit_event  : 익명 방문 핑 → 방문수·DAU/WAU/MAU
- upload_record: 업로드 메타(관리자 열람용). 실제 파일은 datadir.uploads_dir() 에 별도 저장.

master.db(참조 데이터·배포마다 재시드)와 분리한다. 이 DB 는 배포 후에도 누적돼야
하므로 영구 볼륨(datadir)에 둔다. 방문자 식별자(visitor)는 익명 uuid 해시 — 원시 IP·
개인정보는 저장하지 않는다.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from app.core import datadir

_SCHEMA = """
CREATE TABLE IF NOT EXISTS visit_event (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  ts      TEXT NOT NULL,
  visitor TEXT,
  page    TEXT,
  service TEXT
);
CREATE INDEX IF NOT EXISTS idx_visit_ts ON visit_event(ts);
CREATE INDEX IF NOT EXISTS idx_visit_visitor ON visit_event(visitor);

CREATE TABLE IF NOT EXISTS upload_record (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          TEXT NOT NULL,
  service     TEXT,
  filename    TEXT,
  size        INTEGER,
  mime        TEXT,
  ext         TEXT,
  visitor     TEXT,
  case_id     TEXT,
  stored_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_upload_ts ON upload_record(ts);

CREATE TABLE IF NOT EXISTS interaction_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          TEXT NOT NULL,
  kind        TEXT,    -- 챗봇 / 근로계약서 / 임금명세서 / 취업규칙 / 노무계약서
  model       TEXT,
  input_text  TEXT,
  output_text TEXT,
  visitor     TEXT,
  case_id     TEXT,    -- 검토 케이스 id (upload_record.case_id 와 연결)
  upload_id   INTEGER  -- 원본 업로드 파일 id (upload_record.id) — 상세에서 이미지 열람
);
CREATE INDEX IF NOT EXISTS idx_interaction_ts ON interaction_log(ts);
CREATE INDEX IF NOT EXISTS idx_interaction_kind ON interaction_log(kind);
"""

_ensured = False


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    global _ensured
    path = datadir.events_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        if not _ensured:
            conn.executescript(_SCHEMA)
            # 기존 DB 마이그레이션 — 컬럼이 없으면 추가(있으면 무시)
            for _ddl in (
                "ALTER TABLE interaction_log ADD COLUMN case_id TEXT",
                "ALTER TABLE interaction_log ADD COLUMN upload_id INTEGER",
            ):
                try:
                    conn.execute(_ddl)
                except Exception:
                    pass
            _ensured = True
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ─── 방문 이벤트 ───────────────────────────────
def log_visit(visitor: str | None, page: str | None, service: str | None) -> None:
    """익명 방문 1건 기록. 실패해도 silent (사용자 흐름 방해 금지)."""
    try:
        with _connect() as c:
            c.execute(
                "INSERT INTO visit_event(ts,visitor,page,service) VALUES(?,?,?,?)",
                (_now(), (visitor or "")[:64], (page or "")[:200], (service or "")[:40]),
            )
    except Exception:
        pass


# ─── 업로드 기록 ───────────────────────────────
def add_upload(
    *,
    service: str,
    filename: str,
    size: int,
    mime: str,
    ext: str,
    visitor: str | None,
    case_id: str | None,
    stored_path: str | None,
) -> int | None:
    try:
        with _connect() as c:
            cur = c.execute(
                "INSERT INTO upload_record(ts,service,filename,size,mime,ext,visitor,case_id,stored_path) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    _now(), service, (filename or "")[:300], int(size or 0),
                    (mime or "")[:120], (ext or "")[:20], (visitor or "")[:64],
                    (case_id or "")[:120], stored_path or "",
                ),
            )
            return cur.lastrowid
    except Exception:
        return None


def list_uploads(
    limit: int = 100, offset: int = 0, service: str | None = None
) -> tuple[list[dict[str, Any]], int]:
    with _connect() as c:
        if service:
            rows = c.execute(
                "SELECT * FROM upload_record WHERE service=? ORDER BY id DESC LIMIT ? OFFSET ?",
                (service, limit, offset),
            ).fetchall()
            total = c.execute(
                "SELECT COUNT(*) n FROM upload_record WHERE service=?", (service,)
            ).fetchone()["n"]
        else:
            rows = c.execute(
                "SELECT * FROM upload_record ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            total = c.execute("SELECT COUNT(*) n FROM upload_record").fetchone()["n"]
    return [dict(r) for r in rows], total


def get_upload(uid: int) -> dict[str, Any] | None:
    with _connect() as c:
        r = c.execute("SELECT * FROM upload_record WHERE id=?", (uid,)).fetchone()
    return dict(r) if r else None


# ─── 상호작용 로그 (챗봇·검토 Input/Output) ─────
def log_interaction(
    *,
    kind: str,
    model: str,
    input_text: str,
    output_text: str,
    visitor: str | None,
    case_id: str | None = None,
    upload_id: int | None = None,
) -> None:
    """LLM 상호작용 1건 기록. PII 는 호출 측에서 마스킹된 본문이 들어온다. 실패해도 silent.

    case_id / upload_id 를 주면 상세 화면에서 원본 업로드 파일(이미지 포함)을 함께 열람한다.
    """
    try:
        with _connect() as c:
            c.execute(
                "INSERT INTO interaction_log(ts,kind,model,input_text,output_text,visitor,case_id,upload_id) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (
                    _now(), (kind or "")[:40], (model or "")[:80],
                    (input_text or "")[:8000], (output_text or "")[:12000],
                    (visitor or "")[:64], ((case_id or "")[:120] or None), upload_id,
                ),
            )
    except Exception:
        pass


def list_interactions(
    limit: int = 100, offset: int = 0, kind: str | None = None
) -> tuple[list[dict[str, Any]], int]:
    """목록 — 본문은 미리보기로 잘라서 반환(상세는 get_interaction)."""
    sel = (
        "SELECT id, ts, kind, model, visitor, "
        "substr(input_text,1,200) AS input_preview, "
        "substr(output_text,1,240) AS output_preview FROM interaction_log"
    )
    with _connect() as c:
        if kind:
            rows = c.execute(
                f"{sel} WHERE kind=? ORDER BY id DESC LIMIT ? OFFSET ?",
                (kind, limit, offset),
            ).fetchall()
            total = c.execute(
                "SELECT COUNT(*) n FROM interaction_log WHERE kind=?", (kind,)
            ).fetchone()["n"]
        else:
            rows = c.execute(
                f"{sel} ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
            total = c.execute("SELECT COUNT(*) n FROM interaction_log").fetchone()["n"]
    return [dict(r) for r in rows], total


def get_interaction(iid: int) -> dict[str, Any] | None:
    """로그 1건 상세 — 연결된 원본 업로드(파일/이미지) 메타를 함께 붙여 반환.

    upload_id 가 있으면 그 파일, 없으면 같은 case_id 의 최근 업로드를 찾아 연결한다.
    """
    with _connect() as c:
        r = c.execute("SELECT * FROM interaction_log WHERE id=?", (iid,)).fetchone()
        if not r:
            return None
        rec = dict(r)
        uid = rec.get("upload_id")
        cid = (rec.get("case_id") or "").strip()
        rows: list[sqlite3.Row] = []
        # 같은 case_id 로 올린 원본 파일 전부(여러 장 사진 등) — 오래된→최근 순
        if cid:
            rows = list(
                c.execute(
                    "SELECT id,filename,mime,ext,size,stored_path FROM upload_record "
                    "WHERE case_id=? ORDER BY id ASC",
                    (cid,),
                ).fetchall()
            )
        # case_id 매칭이 없으면 upload_id 단건 폴백
        if not rows and uid:
            one = c.execute(
                "SELECT id,filename,mime,ext,size,stored_path FROM upload_record WHERE id=?",
                (uid,),
            ).fetchone()
            if one is not None:
                rows = [one]
    uploads = []
    for up in rows:
        u = dict(up)
        sp = u.pop("stored_path", "") or ""
        uploads.append(
            {
                "id": u["id"],
                "filename": u.get("filename") or "",
                "mime": u.get("mime") or "",
                "ext": u.get("ext") or "",
                "size": u.get("size") or 0,
                "has_file": bool(sp and Path(sp).exists()),
            }
        )
    rec["uploads"] = uploads
    return rec


def cleanup_old_uploads(retention_days: int = 30) -> int:
    """보관기간 초과 업로드 파일·레코드 삭제. 삭제 건수 반환."""
    cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat(timespec="seconds")
    removed = 0
    try:
        with _connect() as c:
            rows = c.execute(
                "SELECT id, stored_path FROM upload_record WHERE ts < ?", (cutoff,)
            ).fetchall()
            for r in rows:
                sp = r["stored_path"]
                if sp:
                    try:
                        Path(sp).unlink(missing_ok=True)
                    except Exception:
                        pass
                c.execute("DELETE FROM upload_record WHERE id=?", (r["id"],))
                removed += 1
            # 상호작용 로그도 보관기간 초과분 정리
            c.execute("DELETE FROM interaction_log WHERE ts < ?", (cutoff,))
    except Exception:
        pass
    return removed


# ─── 집계 (대시보드) ───────────────────────────
def analytics_summary(daily_days: int = 30) -> dict[str, Any]:
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    d7 = (now - timedelta(days=7)).isoformat(timespec="seconds")
    d30 = (now - timedelta(days=30)).isoformat(timespec="seconds")
    d_daily = (now - timedelta(days=daily_days)).isoformat(timespec="seconds")
    with _connect() as c:
        total_visits = c.execute("SELECT COUNT(*) n FROM visit_event").fetchone()["n"]
        dau = c.execute(
            "SELECT COUNT(DISTINCT visitor) n FROM visit_event WHERE substr(ts,1,10)=?",
            (today,),
        ).fetchone()["n"]
        wau = c.execute(
            "SELECT COUNT(DISTINCT visitor) n FROM visit_event WHERE ts>=?", (d7,)
        ).fetchone()["n"]
        mau = c.execute(
            "SELECT COUNT(DISTINCT visitor) n FROM visit_event WHERE ts>=?", (d30,)
        ).fetchone()["n"]
        daily = c.execute(
            "SELECT substr(ts,1,10) d, COUNT(*) visits, COUNT(DISTINCT visitor) users "
            "FROM visit_event WHERE ts>=? GROUP BY d ORDER BY d",
            (d_daily,),
        ).fetchall()
        total_uploads = c.execute("SELECT COUNT(*) n FROM upload_record").fetchone()["n"]
        by_service = c.execute(
            "SELECT service, COUNT(*) n FROM upload_record GROUP BY service"
        ).fetchall()
    return {
        "total_visits": total_visits,
        "dau": dau,
        "wau": wau,
        "mau": mau,
        "total_uploads": total_uploads,
        "daily": [dict(r) for r in daily],
        "uploads_by_service": {(r["service"] or "기타"): r["n"] for r in by_service},
    }
