#
# 가변 데이터 디렉터리 해석 — 로컬은 backend/data, 운영(Fly)은 /data(영구 볼륨).
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.06.22      kimzion77   최초 생성
# 2026.10.02      이시영      구조 이행 (backend/cgr → backend/app)
# 2026.10.06      이시영      PostgreSQL 전환, 노무가이드 삭제
# 2026.10.07      이시영      환경설정 통합 (루트 .env·config.py), mock LLM 추가
# 2026.10.07      이시영      화면 경로 /cgr·features 구조 이동, sync API 삭제, 업로드 원본 미저장
# 2026.10.07      이시영      검토번호 서버 발급, 변경 사유 주석 추가
#
# Author: kimzion77
# Since: 2026.06.22
#
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

