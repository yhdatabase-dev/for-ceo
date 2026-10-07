# moellab.info 자체 서버 배포 (Docker Compose)

자체 서버에 **backend(FastAPI) + frontend(Next.js) + Caddy(자동 HTTPS)** 를 한 번에 띄운다.

구조:
```
인터넷 → Caddy(80/443) → frontend:3000 → (서버사이드 BFF) → backend:8080(내부 전용)
```
- 백엔드는 인터넷에 직접 노출되지 않음(프론트 BFF 가 내부 네트워크로 호출).
- 통계·업로드·편집 프롬프트는 도커 볼륨 `cgr_data` 에 영구 보존.
- `master.db`(검토 기준 DB)는 이미지에 포함되어 함께 배포됨.

## 사전 조건
- 서버에 Docker + Docker Compose 설치
- `moellab.info` DNS A레코드가 이 서버 공인 IP를 가리킴
- 방화벽에서 80, 443 포트 개방 (Caddy 인증서 발급·서비스용)

## 배포 절차
```bash
git pull origin main                 # 최신 코드
cp .env.docker.example .env          # 환경변수 템플릿 복사
nano .env                            # 값 채우기 (아래 참고)
docker compose up -d --build         # 빌드 + 기동
docker compose logs -f caddy         # HTTPS 인증서 발급 로그 확인
```

`.env` 에 채울 값:
- `SITE_ADDRESS` = `moellab.info`
- `CGR_API_KEY` = 임의의 강한 문자열 (백엔드·프론트가 같은 값을 씀)
- `OPENAI_API_KEY` = OpenAI 키 (운영은 필수 — 없으면 백엔드가 시작하지 않음)
- `CGR_DB_HOST` · `CGR_DB_PORT` · `CGR_DB_NAME` · `CGR_DB_USER` · `CGR_DB_PASSWORD` = DB 접속 정보

## 확인
- `https://moellab.info` 접속 → 홈 화면
- LLM 기능(검토·챗봇)은 `OPENAI_API_KEY` 가 있어야 동작

## 운영
```bash
docker compose ps                    # 상태
docker compose logs -f backend       # 백엔드 로그
git pull && docker compose up -d --build   # 업데이트 재배포
docker compose down                  # 중지(볼륨은 유지)
```

> `NEXT_PUBLIC_BASE_PATH` 를 바꾸면 빌드 시 인라인되므로 `--build` 로 재빌드해야 반영됨.
> 이미 서버에 다른 리버스 프록시(nginx 등)가 80/443 을 점유 중이면, compose 의 `caddy` 서비스를 빼고
> 기존 프록시에서 `frontend` 컨테이너(예: 127.0.0.1:3000 으로 ports 매핑)로 reverse_proxy 하면 된다.
