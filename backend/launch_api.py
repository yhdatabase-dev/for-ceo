"""FastAPI 백엔드 launcher — 포트는 CGR_BACKEND_PORT (루트 .env, 기본 18081).

개발표준정의서 Directory 구조: 환경설정 값은 환경변수로 주입하고 /app/core/config.py 한 곳에서만 읽는다 (기존: 포트 8503 고정, PYTHONPATH 를 덮어씀).

사용:
    python launch_api.py
    # 또는 reload 모드:
    python launch_api.py --reload
"""
import io
import os
import subprocess
import sys

# Windows cp949 stdout 에서도 ASCII 외 문자 출력 가능하도록
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from app.core.config import get_backend_port  # noqa: E402  (루트 .env 로드 포함)

port = str(get_backend_port())
env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONPATH"] = os.pathsep.join(p for p in (ROOT, env.get("PYTHONPATH")) if p)

cmd = [
    sys.executable, "-m", "uvicorn",
    "app.main:app",
    "--host", "127.0.0.1",
    "--port", port,
    "--log-level", "info",
]
if "--reload" in sys.argv:
    cmd.append("--reload")

print("[launch_api]", " ".join(cmd), flush=True)
print(f"  - Swagger UI : http://127.0.0.1:{port}/docs", flush=True)
print(f"  - Health     : http://127.0.0.1:{port}/health", flush=True)
print("  Auth: X-API-Key header (CGR_API_KEY)", flush=True)
sys.exit(subprocess.call(cmd, env=env))
