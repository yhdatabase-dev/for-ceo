"""review 도메인 공개 인터페이스 — 취업규칙(WR).

원본 매핑
- cgr/run.py:review_file           → WrReviewService.review_file (오케스트레이터)
- cgr/wr_classify.py:run           → WrClassifyService.run (근로환경 1차 분류)
- cgr/revise.py:run("취업규칙", …) → WrReviseService.run (수정본 생성)

파이프라인 (원본 review_file):
  parse → article_prefilter → embed_matcher → 병렬 extract → evaluate
       → explain (LLM 이유 보강) → optional_display_emb → finalize
"""
from __future__ import annotations

from .classify_service import WrClassifyService
from .review_service import WrReviewService
from .revise_service import WrReviseService

__all__ = ["WrReviewService", "WrClassifyService", "WrReviseService"]
