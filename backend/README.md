# for-ceo.v2 backend

> for-ceo (원본) 백엔드를 `docs/리팩토리 구조.md` 의 레이어드 아키텍처로 재구성.
>
> 대상 도메인: **review(WR 취업규칙) · ec(근로계약서) · guide(고용노동 가이드)**
> 제외 도메인: `ws`(임금명세서), `sc`(노무제공자 계약서) — v2 리팩토링에서 제외
>
> **PostgreSQL 은 외부에서 이미 프로비저닝 (테이블 포함).**
> SQLAlchemy · Alembic · ORM 미사용. psycopg 3 raw SQL 만 사용.

---

## 폴더 구조

```
backend/
├── app/
│   ├── api/routers/{review,ec,guide,admin,shared}   ── Controller
│   ├── schemas/{common,review,ec,guide,shared}      ── DTO/VO
│   ├── services/{review,ec,guide,shared}            ── 업무 로직
│   ├── repositories/{review,ec,guide,shared}        ── psycopg raw SQL
│   ├── core/{config,database,exceptions,logging,security}.py
│   ├── integrations/{llm,parsers}                    ── 외부 어댑터
│   ├── utils/                                        ── 순수 함수
│   └── main.py                                       ── 앱 팩토리
├── scripts/{dev,ops,equiv}/                          ── 일회성 도구
└── tests/{unit,integration,equivalence,lint}/
```

## 실행

```bash
# 1. 의존성
pip install -r requirements.txt

# 2. env 설정 (외부 PG DSN 필수)
cp .env.example .env    # CGR_PG_DSN 실제 값으로

# 3. 서버 기동
uvicorn app.main:app --host 0.0.0.0 --port 8503
```

Docker:
```bash
docker compose up -d
docker compose logs -f api
```

## 원본 대비 핵심 변경점

| 축 | 원본 (for-ceo) | v2 |
|---|---|---|
| **DB** | SQLite (`data/master.db`, `data/events.db`) | **PostgreSQL (외부 프로비저닝)** — 스키마 4개 (`cgr_master`, `cgr_txn`, `cgr_log`, `cgr_admin`) |
| **DB 접근** | 직접 `sqlite3.connect` | psycopg 3 + ConnectionPool (SQLAlchemy 미사용) |
| **아키텍처** | 평면 모듈 (cgr/*) | 레이어드 (api → services → repositories) |
| **프롬프트/슬롯/설정** | 로컬 파일 | PG 테이블 (`cgr_admin.prompt` 등) |
| **로그** | JSONL 파일 | PG (`cgr_log.*`) |
| **DTO/VO 분리** | 없음 | 명시적 (`schemas/<domain>/{requests,responses,values}.py`) |
| **LLM 어댑터** | 직접 `OpenAI()` 인스턴스화 | `integrations/llm/client.py` 어댑터 |
| **파서** | `parsers/*.py` 각자 호출 | `integrations/parsers/` 어댑터 인터페이스 |
| **환경설정** | `cgr/config.py` 함수 4개 + 산재된 env | `app/core/config.py` Pydantic BaseSettings 단일 소스 |
| **로깅** | `cgr/log.py` | `app/core/logging.py` + 요청 컨텍스트 |

## 도메인 격리 규칙

- `services/review` ↔ `services/ec` ↔ `services/guide` **상호 import 금지**
- 공유는 `services/shared` 에만 두고 각 도메인이 그것을 import
- 라우트는 서비스만 부름 (repository 직접 접근 금지)
- 서비스는 repositories 를 부름 (raw SQL 금지)
- utils 는 어느 계층도 import 안 함 (순수 함수만)
