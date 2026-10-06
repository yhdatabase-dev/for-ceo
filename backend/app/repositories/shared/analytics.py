"""사용량·업로드·LLM 호출 기록 저장소 — PostgreSQL.

- app.tb_cntn_rcd     접속 기록 : 익명 방문 핑
- app.tb_file_uld_rcd 파일 업로드 기록 : 업로드 메타. 실제 파일은 datadir.uploads_dir() 에 별도 저장
- ai.tb_llm_clot_log  LLM 호출 로그 : 챗봇·검토 입력/출력 (PII 는 호출 측에서 마스킹)

방문자 식별자는 익명 uuid·해시 — 원시 IP·개인정보는 저장하지 않는다.
기록 실패는 사용자 흐름을 막지 않도록 조용히 넘긴다.
문자열은 컬럼 길이(DE10 · 개발 시트)에 맞춰 자른다.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from app.repositories import base as db


def _cut(value: str | None, size: int) -> str:
    return (value or "")[:size]


# ─── 접속 기록 ───────────────────────────────
def log_visit(visitor: str | None, page: str | None, service: str | None) -> None:
    """익명 방문 1건 기록. 실패해도 silent (사용자 흐름 방해 금지)."""
    try:
        with db.connect() as c:
            c.execute(
                "INSERT INTO app.tb_cntn_rcd (cntn_dt, acsr_idntfr, cntn_path_nm, srvc_se_nm) "
                "VALUES (%s, %s, %s, %s)",
                (datetime.now(), _cut(visitor, 64), _cut(page, 300), _cut(service, 200)),
            )
    except Exception:
        pass


# ─── 파일 업로드 기록 ─────────────────────────
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
    """업로드 1건 기록. 기록 일련번호 반환 (실패 시 None)."""
    try:
        with db.connect() as c:
            row = c.execute(
                "INSERT INTO app.tb_file_uld_rcd "
                "(uld_dt, srvc_se_nm, uld_file_nm, file_sz, file_frm_nm, file_extn_nm, "
                " acsr_hash_vl, rvw_case_idntfr, file_path_nm) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING sn",
                (
                    datetime.now(), _cut(service, 200), _cut(filename, 300), int(size or 0),
                    _cut(mime, 200), _cut(ext, 5), _cut(visitor, 20),
                    _cut(case_id, 50), _cut(stored_path, 300),
                ),
            ).fetchone()
            return int(row["sn"])
    except Exception:
        return None


# ─── LLM 호출 로그 (챗봇·검토 Input/Output) ─────
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

    case_id / upload_id 로 원본 업로드 기록과 연결한다.
    """
    try:
        with db.connect() as c:
            c.execute(
                "INSERT INTO ai.tb_llm_clot_log "
                "(dmn_nm, llm_mdl_nm, inpt_cn, otpt_cn, vstr_id, case_uid, uld_id, clot_dt) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    _cut(kind, 200), _cut(model, 100),
                    _cut(input_text, 8000), _cut(output_text, 12000),
                    _cut(visitor, 20), _cut(case_id, 100) or None,
                    None if upload_id is None else str(upload_id), datetime.now(),
                ),
            )
    except Exception:
        pass


# ─── 보관기간 정리 ─────────────────────────────
def cleanup_old_uploads(retention_days: int = 30) -> int:
    """보관기간 초과 업로드 파일·기록과 LLM 호출 로그 삭제. 삭제한 업로드 건수 반환."""
    cutoff = datetime.now() - timedelta(days=retention_days)
    removed = 0
    try:
        with db.connect() as c:
            rows = c.execute(
                "SELECT sn, file_path_nm FROM app.tb_file_uld_rcd WHERE uld_dt < %s", (cutoff,)
            ).fetchall()
            for r in rows:
                if r["file_path_nm"]:
                    try:
                        Path(r["file_path_nm"]).unlink(missing_ok=True)
                    except Exception:
                        pass
                c.execute("DELETE FROM app.tb_file_uld_rcd WHERE sn = %s", (r["sn"],))
                removed += 1
            c.execute("DELETE FROM ai.tb_llm_clot_log WHERE clot_dt < %s", (cutoff,))
    except Exception:
        pass
    return removed
