"""guide 도메인 응답 DTO — 서버가 프론트로 보내는 계약.

원본 매핑
- GET  /guide/items              → GuideItemListOut / GuideItemOut
- GET  /guide/glossary           → GlossaryListOut
- GET  /guide/by-size/{...}      → SizeThresholdDutyListOut
- GET  /guide/timeline           → ObligationTimelineListOut
- GET  /guide/forms              → FormListOut
- GET  /guide/overview           → GuideOverviewOut
- POST /guide/chat               → GuideChatOut
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# ─── 가이드 항목 (꿀팁) ───────────────────────────
class GuideItemOut(BaseModel):
    code: str
    audience: str            # worker | employer | both
    category: str | None = None
    title: str
    worker_reason: str | None = None
    employer_reason: str | None = None
    key_points: str | None = None
    related_laws: str | None = None
    priority: str | None = None
    applies_under_5: str | None = None
    note: str | None = None


class GuideItemListOut(BaseModel):
    items: list[GuideItemOut]


# ─── 용어 사전 ────────────────────────────────────
class GlossaryItemOut(BaseModel):
    code: str
    term: str
    short_def: str | None = None
    full_def: str | None = None
    confusable_with: str | None = None
    legal_basis: str | None = None


class GlossaryListOut(BaseModel):
    items: list[GlossaryItemOut]


# ─── 사업장 규모별 의무 ──────────────────────────
class SizeThresholdDutyOut(BaseModel):
    code: str
    min_size: str
    duty: str
    description: str | None = None
    related_docs: str | None = None
    legal_basis: str | None = None
    note: str | None = None


class SizeThresholdDutyListOut(BaseModel):
    size: str = ""
    rank: int = 0
    duties: list[SizeThresholdDutyOut]


# ─── 의무 타임라인 ────────────────────────────────
class ObligationTimelineOut(BaseModel):
    code: str
    stage: str
    duty: str
    description: str | None = None
    deadline: str | None = None
    legal_basis: str | None = None
    priority: str | None = None
    penalty: str | None = None


class ObligationTimelineListOut(BaseModel):
    items: list[ObligationTimelineOut]


# ─── 서식 ─────────────────────────────────────────
class FormOut(BaseModel):
    code: str
    form_name: str
    category: str | None = None
    purpose: str | None = None
    submitter: str | None = None
    submit_to: str | None = None
    submit_method: str | None = None
    deadline: str | None = None
    legal_basis: str | None = None
    audience: str = "employer"
    has_local: bool = False           # backend/data/forms/<file> 존재 여부
    download_url: str | None = None   # 외부(고용노동부) URL — 폴백


class FormListOut(BaseModel):
    items: list[FormOut]


# ─── 오버뷰 (카운트 요약) ─────────────────────────
class GuideOverviewOut(BaseModel):
    n_guide_items: int = 0
    n_timeline: int = 0
    n_wage_calc: int = 0
    n_glossary: int = 0
    n_forms: int = 0
    n_orgs: int = 0
    n_required_docs: int = 0
    n_lifecycle: int = 0


# ─── 챗봇 응답 ────────────────────────────────────
class RelatedFormHint(BaseModel):
    """챗봇 답변에 첨부되는 서식 링크 힌트."""

    code: str
    form_name: str
    category: str | None = None
    audience: str = "employer"
    has_local: bool = False
    purpose: str | None = None


class GuideChatOut(BaseModel):
    """`POST /guide/chat` 응답."""

    answer: str
    matched_sources: list[str] = Field(default_factory=list, description="RAG 매칭 근거")
    follow_ups: list[str] = Field(default_factory=list, description="추천 후속 질문")
    related_forms: list[RelatedFormHint] = Field(default_factory=list)
    clarify: str | None = Field(default=None, description="모호한 경우 되묻기")
    elapsed_sec: float = 0.0
    model: str = ""
