# `app.api` — FastAPI 라우터

REST API. 모든 외부 진입은 여기를 지난다.

## 실행

```bash
cd backend && python launch_api.py
```

포트는 루트 `.env` 의 `CGR_BACKEND_PORT` (기본 18081). Swagger: http://127.0.0.1:18081/docs

## 경로

- 서비스 접두 `/api/cgr` 는 `app/main.py` 한 곳, 도메인 접두는 `routers/router.py` 한 곳에서 정의한다.
- 형식: `/api/cgr/<도메인>/<리소스>` — 리소스는 복수형 케밥, 버전·동사 없음.
- 오래 걸리는 AI 작업은 `POST /<리소스>` 로 접수하고 `GET /<리소스>/{job_id}` 로 결과를 조회한다.

전체 목록은 Swagger UI 참고.

## 인증

`X-API-Key` 헤더 — `app.core.security.require_api_key` 의존성 (키: `CGR_API_KEY`).
