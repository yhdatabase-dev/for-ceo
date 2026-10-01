# 취업규칙 검토 AI — FastAPI 백엔드 컨테이너 (Fly.io / 도커 배포)
#
# 빌드 컨텍스트는 레포 루트 — 루트의 Excel 마스터 DB 와 backend/ 를 함께 복사한다.
# master_db.py 가 parents[2](= 컨테이너의 /app)에서 Excel 을 찾으므로 경로 일치.

FROM python:3.14.7-slim

# 한글 파일명·로그 깨짐 방지
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 1) 의존성 먼저 — 레이어 캐시 (코드만 바뀌면 재설치 안 함)
COPY backend/requirements-api.txt /app/backend/requirements-api.txt
RUN pip install --no-cache-dir -r /app/backend/requirements-api.txt

# 2) 백엔드 코드 + 데이터 (master.db, slots, forms 등)
COPY backend /app/backend

# 3) 레포 루트의 Excel 마스터 DB (취업규칙 검토의 ground-truth)
#    master_db.py 의 _REPO_ROOT = /app 와 일치해야 함.
COPY ["취업규칙 마스터 db (2026).xlsx", "/app/취업규칙 마스터 db (2026).xlsx"]
COPY ["취업규칙 마스터 db.xlsx", "/app/취업규칙 마스터 db.xlsx"]

WORKDIR /app/backend

# 비-root 실행(OWASP A05 보안설정오류/컨테이너 하드닝). 운영 데이터는 Fly 볼륨(/data).
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Fly.io 는 내부 포트를 PORT 환경변수로 주입 (없으면 8080)
ENV PORT=8080
EXPOSE 8080

# shell 형식 — $PORT 치환 필요
CMD uvicorn cgr.api.main:app --host 0.0.0.0 --port ${PORT}
