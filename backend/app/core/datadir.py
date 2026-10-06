"""가변 데이터 디렉터리 해석 — 로컬은 backend/data, 운영(Fly)은 /data(영구 볼륨).

env `CGR_DATA_DIR` 로 override. 업로드 파일·편집형 프롬프트가
배포 후에도 살아있어야 하므로 이 디렉터리를 Fly 볼륨에 둔다(배포 시 초기화 방지).

세부 경로는 개별 env 로도 덮을 수 있다:
  CGR_PROMPTS_DIR / CGR_UPLOADS_DIR
지정이 없으면 모두 data_dir() 하위로 떨어진다.
"""
from __future__ import annotations

import os
from pathlib import Path

# backend/cgr/datadir.py → parents[1] = backend
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DATA = _BACKEND_ROOT / "data"


def data_dir() -> Path:
    env = os.environ.get("CGR_DATA_DIR")
    p = Path(env) if env else _DEFAULT_DATA
    p.mkdir(parents=True, exist_ok=True)
    return p


def prompts_dir() -> Path:
    env = os.environ.get("CGR_PROMPTS_DIR")
    p = Path(env) if env else (data_dir() / "prompts")
    p.mkdir(parents=True, exist_ok=True)
    return p


def uploads_dir() -> Path:
    env = os.environ.get("CGR_UPLOADS_DIR")
    p = Path(env) if env else (data_dir() / "uploads")
    p.mkdir(parents=True, exist_ok=True)
    return p
