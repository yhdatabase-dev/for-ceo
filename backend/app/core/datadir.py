"""가변 데이터 디렉터리 해석 — 로컬은 backend/data, 운영(Fly)은 /data(영구 볼륨).

env `CGR_DATA_DIR` 로 override. 편집형 프롬프트가
배포 후에도 살아있어야 하므로 이 디렉터리를 Fly 볼륨에 둔다(배포 시 초기화 방지).

세부 경로는 개별 env 로도 덮을 수 있다:
  CGR_PROMPTS_DIR
지정이 없으면 모두 data_dir() 하위로 떨어진다.
"""
from __future__ import annotations

from pathlib import Path

from app.core import config  # 개발표준정의서 Directory 구조: 환경설정 값은 환경변수로 주입하고 /app/core/config.py 한 곳에서만 읽는다 (기존: os.environ 직접 읽음)

# backend/cgr/datadir.py → parents[1] = backend
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DATA = _BACKEND_ROOT / "data"


def data_dir() -> Path:
    env = config.get_data_dir()
    p = Path(env) if env else _DEFAULT_DATA
    p.mkdir(parents=True, exist_ok=True)
    return p


def prompts_dir() -> Path:
    env = config.get_prompts_dir()
    p = Path(env) if env else (data_dir() / "prompts")
    p.mkdir(parents=True, exist_ok=True)
    return p

