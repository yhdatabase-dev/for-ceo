#
# 통합 DB — PostgreSQL 연결 helper.
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.05.28      kimzion77   최초 생성
# 2026.10.02      이시영      구조 이행 (backend/cgr → backend/app)
# 2026.10.06      이시영      PostgreSQL 전환, 노무가이드 삭제
# 2026.10.06      이시영      주석 정리
# 2026.10.07      이시영      검토번호 서버 발급, 변경 사유 주석 추가
#
# Author: kimzion77
# Since: 2026.05.28
#
"""통합 DB — PostgreSQL 연결 helper.

테이블정의서: CGR 테이블은 PostgreSQL 스키마 ai · app 의 tb_ 테이블로 조회한다
(기존: SQLite master.db · events.db 파일). 접속 정보는 app.core.config.get_db_conninfo.

- 모든 쿼리는 `with connect() as conn:` 컨텍스트 매니저로 — 자동 commit/rollback
- 행은 dict 로 반환 → 컬럼명으로 접근 (row['name'])
- 값은 바인딩 파라미터(%s)로만 전달한다
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from app.core.config import get_db_conninfo

CONNECT_TIMEOUT_SEC = 5


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """PostgreSQL 연결 컨텍스트 — 자동 commit / rollback."""
    conn = psycopg.connect(
        **get_db_conninfo(), row_factory=dict_row, connect_timeout=CONNECT_TIMEOUT_SEC
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
