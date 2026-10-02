"""FastAPI 백엔드 launcher — 포트 8503.

사용:
    python launch_api.py
    # 또는 reload 모드:
    python launch_api.py --reload

OpenAPI 문서: http://127.0.0.1:8503/docs

검토 앱(8501)·관리자 앱(8502)과 분리 운영. 같은 데이터(슬롯·마스터 DB·이력) 공유.
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
env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONPATH"] = ROOT

reload_flag = "--reload" if "--reload" in sys.argv else None

cmd = [
    sys.executable, "-m", "uvicorn",
    "app.main:app",
    "--host", "127.0.0.1",
    "--port", "8503",
    "--log-level", "info",
]
if reload_flag:
    cmd.append("--reload")

print("[launch_api]", " ".join(cmd), flush=True)
print("  - Swagger UI : http://127.0.0.1:8503/docs", flush=True)
print("  - ReDoc      : http://127.0.0.1:8503/redoc", flush=True)
print("  - Health     : http://127.0.0.1:8503/health", flush=True)
print("", flush=True)
print("  Auth: X-API-Key header required for protected endpoints", flush=True)
print("  Set api_key in .streamlit/secrets.toml or env API_KEY", flush=True)
sys.exit(subprocess.call(cmd, env=env))
