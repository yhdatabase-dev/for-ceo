#
# API 라우터 집결 — 도메인 prefix 는 이 파일 한 곳에서만 선언한다.
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.10.02      이시영      최초 생성 (구조 이행 — 기존 backend/cgr 코드를 분리·이동)
# 2026.10.02      이시영      구조 조정 (web/ai 파트 디렉터리 → 도메인 단일 디렉터리)
# 2026.10.06      이시영      PostgreSQL 전환, 노무가이드 삭제
# 2026.10.06      이시영      주석 정리
# 2026.10.06      이시영      API 경로 표준화 (/api/cgr)
# 2026.10.07      이시영      챗봇 기능 삭제
# 2026.10.07      이시영      검토번호 서버 발급, 변경 사유 주석 추가
#
# Author: 이시영
# Since: 2026.10.02
#
"""API 라우터 집결 — 도메인 prefix 는 이 파일 한 곳에서만 선언한다.

등록 순서는 구 cgr/api/main.py 의 순서(review → wr_classify → ec → history → topics → track)를
그대로 따른다. 경로는 /api/cgr/<도메인>/<리소스> 형식이다.
web/ai 파트 구분은 확정 전이라 도메인 디렉터리 하나에 둔다.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers.ec import analyze as ec_analyze
from app.api.routers.ec import classify as ec_classify
from app.api.routers.ec import document as ec_document
from app.api.routers.ec import extract as ec_extract
from app.api.routers.ec import generate as ec_generate
from app.api.routers.ec import structure as ec_structure
from app.api.routers.ec import validate_field as ec_validate_field
from app.api.routers.history import entries as history_entries
from app.api.routers.topics import corpus as topics_corpus
from app.api.routers.track import visits as track_visits
from app.api.routers.wr import classify as wr_classify
from app.api.routers.wr import document as wr_document
from app.api.routers.wr import review as wr_review
from app.api.routers.wr import revision as wr_revision
from app.api.routers.wr import summary as wr_summary

api_router = APIRouter()
# 개발표준정의서 API 엔드포인트: 도메인 prefix 는 이 파일 한 곳에서 선언, 도메인은 백엔드 도메인 식별자와 같게
#   (기존: 취업규칙 prefix /review → /wr)

# ── 취업규칙 (wr) ──
api_router.include_router(wr_review.router, prefix="/wr")
api_router.include_router(wr_revision.router, prefix="/wr")
api_router.include_router(wr_document.router, prefix="/wr")
api_router.include_router(wr_summary.router, prefix="/wr")
api_router.include_router(wr_classify.router, prefix="/wr")

# ── 근로계약서 (ec) ──
api_router.include_router(ec_extract.router, prefix="/ec")
api_router.include_router(ec_classify.router, prefix="/ec")
api_router.include_router(ec_structure.router, prefix="/ec")
api_router.include_router(ec_analyze.router, prefix="/ec")
api_router.include_router(ec_validate_field.router, prefix="/ec")
api_router.include_router(ec_generate.router, prefix="/ec")
api_router.include_router(ec_document.router, prefix="/ec")

# ── 검토 이력 · 노무 주제 · 방문 추적 ──
api_router.include_router(history_entries.router, prefix="/history")
api_router.include_router(topics_corpus.router, prefix="/topics")
api_router.include_router(track_visits.router, prefix="/track")
