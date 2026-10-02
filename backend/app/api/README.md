# `cgr.api` — FastAPI 백엔드

REST API. 모든 외부 진입은 여기 통과.

## 실행

```bash
cd backend && python launch_api.py
# 또는
uvicorn cgr.api.main:app --host 127.0.0.1 --port 8503
```

Swagger: http://127.0.0.1:8503/docs

## 인증

`X-API-Key` 헤더 — `auth.require_api_key` 의존성으로 모든 보호 엔드포인트 적용.
관리자 엔드포인트(`PUT`/`DELETE`) 는 `require_admin_key`.

## 라우터

| 라우터 | prefix | 책임 |
|---|---|---|
| `routes.review` | `/api/v1/review` | 취업규칙 통합 검토 |
| `routes.ec` | `/api/v1/ec` | 근로계약서 4단계 + chat |
| `routes.ws` | `/api/v1/ws` | 임금명세서 analyze/inspect/generate/catalog |
| `routes.topics` | `/api/v1/topics` | 노무사회 코퍼스 |
| `routes.slots` | `/api/v1/slots` | 슬롯 카탈로그 |
| `routes.master_db` | `/api/v1/master-db` | 마스터 DB read-only |
| `routes.history` | `/api/v1/history` | 검토 이력 |
| `routes.admin` | `/api/v1/admin` | 시스템 설정·캐시 |

전체 엔드포인트 — [`Swagger UI`](http://127.0.0.1:8503/docs)

## 신규 라우트 추가

1. `cgr/api/routes/xxx.py` 작성:
   ```python
   from fastapi import APIRouter, Depends
   from cgr.api.auth import require_api_key

   router = APIRouter(prefix="/xxx", tags=["xxx"])

   @router.post("/yyy", dependencies=[Depends(require_api_key)])
   def post_yyy(body: MyIn) -> MyOut:
       ...
   ```
2. `cgr/api/main.py` 의 import + `include_router` 등록
3. 재시작 (uvicorn `--reload` 모드면 자동)

## CORS

`main.py` — `allow_origins=["*"]` 개발용. 운영 시 도메인 제한 권장.
