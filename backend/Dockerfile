# ═══════════════════════════════════════════════════════════════════
# for-ceo.v2 backend Dockerfile
# ═══════════════════════════════════════════════════════════════════
# 로그 정책
#   - 앱은 stderr 로만 → Docker json-file 드라이버가 수집
#   - Python -u (unbuffered) 로 즉시 flush → docker logs 에 지연 없이 반영
#   - 이미지 안에는 로그 파일 없음. 볼륨도 로그용 아님.

FROM python:3.12-slim

# 시스템 의존성 (psycopg 3, hwp 파서용 libmagic 등)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성 먼저 (레이어 캐시 유리)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 코드 (SQLAlchemy/alembic 미사용, PG 는 외부 DB)
COPY app ./app
COPY scripts ./scripts

# 데이터 디렉토리 (볼륨 마운트 지점)
RUN mkdir -p /app/data

# stderr/stdout 을 즉시 flush (Docker 로그 지연 방지)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8503

# 헬스체크 (docker inspect 로 상태 확인)
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8503/health || exit 1

# 기동
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8503 --workers ${UVICORN_WORKERS:-1}"]
