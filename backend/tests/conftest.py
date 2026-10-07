"""테스트 공통 픽스처 — 운영 데이터·외부 API 완전 격리.

원칙
- 외부 LLM 호출 금지: 여기 테스트는 결정적 코드 경로(룰엔진·판정·마스킹·검증)만 다룬다.
- 운영 데이터 오염 금지: 가변 데이터(uploads·prompts)는 임시 디렉터리로,
  DB 접속은 닿지 않는 주소로 돌려 개발 DB 에 기록이 남지 않게 한다
  (DB 조회는 yaml·json fallback, 기록은 silent 실패).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]

# cgr import 보장 (pytest.ini pythonpath=. 와 이중 안전망)
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def pytest_configure(config):
    """cgr 모듈 import 전에 환경 격리 — 세션 전체 적용."""
    tmp = Path(config.cache.mkdir("cgr_data"))  # pytest 관리 임시 디렉터리
    os.environ["CGR_DATA_DIR"] = str(tmp)        # uploads·prompts → 임시
    os.environ["CGR_ENVIRONMENT"] = "local"
    os.environ["CGR_DB_HOST"] = "127.0.0.1"      # 개발 DB 격리 — 닿지 않는 포트
    os.environ["CGR_DB_PORT"] = "1"
    os.environ["CGR_DB_NAME"] = "test"
    os.environ["CGR_DB_USER"] = "test"
    os.environ["CGR_DB_PASSWORD"] = "test"
    os.environ["CGR_DISABLE_CACHE"] = "1"        # LLM 캐시 디스크 쓰기 금지
    os.environ["CGR_API_KEY"] = "test-api-key"
    # LLM 실호출 금지 — 내장 가짜 LLM 으로 고정
    os.environ["CGR_LLM_MOCK"] = "1"
