"""API 라우터 집결 — 도메인 prefix 는 이 파일 한 곳에서만 선언한다 (DE03 3.4).

등록 순서는 구 cgr/api/main.py 의 순서(review → wr_classify → ec → history → topics → guide → track)를
그대로 따른다. 경로·메서드는 구조 이행 전과 같다.
web/ai 파트 구분은 확정 전이라 도메인 디렉터리 하나에 둔다.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers.ec import analyze as ec_analyze
from app.api.routers.ec import chat as ec_chat
from app.api.routers.ec import classify as ec_classify
from app.api.routers.ec import document as ec_document
from app.api.routers.ec import extract as ec_extract
from app.api.routers.ec import generate as ec_generate
from app.api.routers.ec import structure as ec_structure
from app.api.routers.ec import validate_field as ec_validate_field
from app.api.routers.guide import chat as guide_chat
from app.api.routers.guide import content as guide_content
from app.api.routers.history import entries as history_entries
from app.api.routers.topics import corpus as topics_corpus
from app.api.routers.track import visits as track_visits
from app.api.routers.wr import classify as wr_classify
from app.api.routers.wr import document as wr_document
from app.api.routers.wr import review as wr_review
from app.api.routers.wr import revision as wr_revision
from app.api.routers.wr import summary as wr_summary

api_router = APIRouter()

# ── 취업규칙 (wr) — URL 세그먼트는 구조 이행 전과 같은 /review ──
api_router.include_router(wr_review.router, prefix="/review")
api_router.include_router(wr_revision.router, prefix="/review")
api_router.include_router(wr_document.router, prefix="/review")
api_router.include_router(wr_summary.router, prefix="/review")
api_router.include_router(wr_classify.router, prefix="/review")

# ── 근로계약서 (ec) ──
api_router.include_router(ec_extract.router, prefix="/ec")
api_router.include_router(ec_classify.router, prefix="/ec")
api_router.include_router(ec_structure.router, prefix="/ec")
api_router.include_router(ec_analyze.router, prefix="/ec")
api_router.include_router(ec_validate_field.router, prefix="/ec")
api_router.include_router(ec_generate.router, prefix="/ec")
api_router.include_router(ec_document.router, prefix="/ec")
api_router.include_router(ec_chat.router, prefix="/ec")

# ── 검토 이력 · 노무 주제 · 노무 가이드 · 방문 추적 ──
api_router.include_router(history_entries.router, prefix="/history")
api_router.include_router(topics_corpus.router, prefix="/topics")
api_router.include_router(guide_content.router, prefix="/guide")
api_router.include_router(guide_chat.router, prefix="/guide")
api_router.include_router(track_visits.router, prefix="/track")
