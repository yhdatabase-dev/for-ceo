# `cgr.db` — 통합 마스터 DB

SQLite 단일 파일 (`backend/data/master.db`). 27 테이블 + 3 뷰.

## 진입

```python
from cgr import db

with db.connect() as conn:
    cur = conn.execute("SELECT * FROM v_minimum_wage_current")
    row = cur.fetchone()
    print(row["year"], row["hourly_amount"])
```

`connect()` 컨텍스트 매니저:
- `sqlite3.Row` factory → `row["col"]` 접근
- `PRAGMA foreign_keys = ON` 강제
- 자동 `commit` / `rollback`

## 스키마

[`schema.sql`](schema.sql) — 단일 진실의 원천. 4 도메인:

1. **정규화 마스터** — `document_type` · `topic` · `topic_section` · `law` · `law_article`
2. **슬롯 카탈로그** — `check_item` · `check_item_*` (5 테이블)
3. **계산형 룰** — `minimum_wage_master` · `wage_item_catalog` · `violation_type` · `recommendation_mapping`
4. **트랜잭션·검토** — `workplace` · `employee` · `payslip*` · `inspection_run` · `violation_finding` · `recommendation` · `correction_log` · `audit_*`

전체 명세 — [`../../../docs/04_자료사전.md`](../../../docs/04_자료사전.md)

## 시드

```bash
cd backend
python scripts/seed_master_db.py --drop-first
```

7 단계:
1. 스키마 생성
2. document_type
3. topic + topic_section (corpus JSON)
4. check_item from YAML (EC 35 + WR 115 + WS 11)
5. 33-매핑 → topic/law 링크 (EC 전용)
6. WS topic/law 링크 (YAML meta 필드 직접)
7. 임금 룰 마스터 (최저임금 5년치·임금항목 19·V001~V010·권고 10)

## 편의 view

```sql
-- 슬롯 한 건 풀 컨텍스트 (topic/law JSON 배열)
SELECT * FROM v_check_item_full WHERE slot_code = 'SLOT_WS_04_임금총액';

-- 한 검토 실행의 풀 컨텍스트 (findings JSON 배열)
SELECT * FROM v_inspection_full WHERE run_uid = 'RUN_xxx';

-- 현재 적용 최저임금
SELECT * FROM v_minimum_wage_current;
```

## 환경변수

| 변수 | 기본 |
|---|---|
| `CGR_MASTER_DB` | `backend/data/master.db` |

## Postgres 전환 시 호환성

대부분 SQL 표준. 차이 나는 부분:
- `INTEGER PRIMARY KEY AUTOINCREMENT` → `BIGSERIAL PRIMARY KEY`
- `datetime('now')` → `now()`
- JSON: SQLite `json_group_array` → PG `jsonb_agg`
- 뷰 정의 — PG 에서 재작성 필요
