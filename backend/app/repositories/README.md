# `app.repositories` — DB 접근

PostgreSQL (스키마 `ai` · `app`).

## 진입

```python
from app.repositories import base as db

with db.connect() as conn:
    row = conn.execute(
        "SELECT crtr_yr, hrwg_amt FROM ai.tb_yr_lwprc_wage WHERE crtr_yr = %s", ("2026",)
    ).fetchone()
    print(row["crtr_yr"], row["hrwg_amt"])
```

`connect()` 컨텍스트 매니저:
- 행은 dict → `row["col"]` 접근
- 값은 바인딩 파라미터(`%s`)로만 전달
- 자동 `commit` / `rollback`

## 접속 정보

`app.core.config.get_db_conninfo()` — 환경변수 우선, 없으면 `backend/.env` (git 제외).

| 변수 | 내용 |
|---|---|
| `PGHOST` · `PGPORT` | 서버 |
| `PGDATABASE` | DB 이름 |
| `PGUSER` · `PGPASSWORD` | 계정 |

## 서비스가 쓰는 테이블

| 용도 | 테이블 |
|---|---|
| 근로계약서 슬롯 카탈로그 (`ec/catalog.py`) | `ai.tb_chck_item_slot` · `tb_chck_item_apcbt` · `tb_chck_item_risk` · `tb_chck_item_ref_tpc` · `tb_chck_item_stt` · `tb_doc_knd` |
| 법령 · 노무 주제 | `ai.tb_stt_mstr` · `tb_stt_artcl` · `tb_tpc_mstr` · `tb_tpc_sctn` |
| 최저임금 | `ai.tb_yr_lwprc_wage` |
| 접속 · 업로드 · LLM 호출 기록 (`shared/analytics.py`) | `app.tb_cntn_rcd` · `app.tb_file_uld_rcd` · `ai.tb_llm_clot_log` |

DB 접속이 안 되면 슬롯은 `data/slots/*.yaml`, 주제 본문은 `data/topic_corpus.json` 으로 대신 읽는다.

## 기준 데이터 갱신

슬롯 yaml · 코퍼스가 바뀌면 `scripts/seed_master_db.py` 로 `data/master.db`(SQLite)를 다시 만든 뒤
PostgreSQL 로 다시 적재한다. SQLite 스키마는 `scripts/master_schema.sql`.
