"""guide 라우터 — 원본 `cgr/api/routes/guide.py` 이관.

라우트 목록 (원본 매핑 그대로 유지):
- GET  /guide/items                       list_guide_items
- GET  /guide/items/{code}                get_guide_item
- GET  /guide/glossary                    list_glossary
- GET  /guide/by-size/{min_size}          list_by_size
- GET  /guide/by-stage/{stage}            list_by_stage
- GET  /guide/timeline                    list_timeline
- GET  /guide/forms                       list_forms
- GET  /guide/forms/{code}/download       download_form
- GET  /guide/wage-calc                   list_wage_calc
- GET  /guide/orgs                        list_orgs
- GET  /guide/audit                       list_audit_guide
- GET  /guide/required-docs               list_required_docs
- GET  /guide/lifecycle                   list_lifecycle
- GET  /guide/recruit                     list_recruit
- GET  /guide/overview                    overview
- POST /guide/chat                        chat
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, RedirectResponse
import psycopg

from app.api.deps import get_db, get_visitor, require_user
from app.core.config import get_settings
from app.core.exceptions import CgrError, NotFoundError
from app.core.logging import get_logger

log = get_logger(__name__)
from app.schemas.guide import (
    FormListOut,
    GlossaryListOut,
    GuideChatIn,
    GuideChatOut,
    GuideItemListOut,
    GuideItemOut,
    GuideOverviewOut,
    ObligationTimelineListOut,
    SizeThresholdDutyListOut,
)
from app.services.guide import GuideChatService, GuideService

# 라우터 전체에 인증 적용
router = APIRouter(
    prefix="/guide",
    tags=["guide"],
    dependencies=[Depends(require_user)],
)


# ─── 가이드 항목 ─────────────────────────────────
@router.get("/items", response_model=GuideItemListOut)
def list_guide_items(
    audience: str | None = None,
    category: str | None = None,
    db: psycopg.Connection = Depends(get_db),
) -> GuideItemListOut:
    return GuideService(db).list_guide_items(audience=audience, category=category)


@router.get("/items/{code}", response_model=GuideItemOut)
def get_guide_item(code: str, db: psycopg.Connection = Depends(get_db)) -> GuideItemOut:
    item = GuideService(db).get_guide_item(code)
    if not item:
        raise NotFoundError(f"guide_item.code={code} 를 찾을 수 없습니다.")
    return item


# ─── 용어 사전 ────────────────────────────────────
@router.get("/glossary", response_model=GlossaryListOut)
def list_glossary(db: psycopg.Connection = Depends(get_db)) -> GlossaryListOut:
    return GuideService(db).list_glossary()


# ─── 사업장 규모별 의무 ───────────────────────────
@router.get("/by-size/{min_size}", response_model=SizeThresholdDutyListOut)
def list_by_size(min_size: str, db: psycopg.Connection = Depends(get_db)) -> SizeThresholdDutyListOut:
    return GuideService(db).list_size_threshold_duties(min_size)


# ─── 시기별 의무 · 타임라인 ────────────────────────
@router.get("/by-stage/{stage}", response_model=ObligationTimelineListOut)
def list_by_stage(stage: str, db: psycopg.Connection = Depends(get_db)) -> ObligationTimelineListOut:
    return GuideService(db).list_by_stage(stage)


@router.get("/timeline", response_model=ObligationTimelineListOut)
def list_timeline(db: psycopg.Connection = Depends(get_db)) -> ObligationTimelineListOut:
    return GuideService(db).list_timeline()


# ─── 서식 ─────────────────────────────────────────
@router.get("/forms", response_model=FormListOut)
def list_forms(
    category: str | None = None,
    audience: str | None = None,
    db: psycopg.Connection = Depends(get_db),
) -> FormListOut:
    return GuideService(db).list_forms(category=category, audience=audience)


@router.get("/forms/{code}/download")
def download_form(code: str, db: psycopg.Connection = Depends(get_db)):
    """서식 다운로드 — 로컬 파일이 있으면 FileResponse, 없으면 외부 URL 리다이렉트."""
    row = GuideService(db).repo.get_form_row(code)
    if not row:
        raise NotFoundError(f"form.code={code}")
    local_filename = row.get("local_filename")
    if local_filename:
        fp = get_settings().data.data_dir / "forms" / local_filename
        if fp.exists():
            return FileResponse(
                path=str(fp),
                media_type=row.get("local_mime") or "application/octet-stream",
                filename=local_filename,
            )
    if row.get("download_url"):
        return RedirectResponse(row["download_url"], status_code=302)
    raise NotFoundError(f"form.code={code} 파일도 URL도 없음")


# ─── 임금 계산식·기관·기타 ─────────────────────────
@router.get("/wage-calc", summary="임금 계산식 목록 (위반 코드별 필터)")
def list_wage_calc(
    violation_code: str | None = None, db: psycopg.Connection = Depends(get_db)
) -> dict:
    return {"items": GuideService(db).list_wage_calc(violation_code=violation_code)}


@router.get("/orgs", summary="정부 기관·온라인 채널 목록")
def list_orgs(db: psycopg.Connection = Depends(get_db)) -> dict:
    return {"items": GuideService(db).list_orgs()}


@router.get("/audit", summary="근로감독 대응 가이드")
def list_audit_guide(db: psycopg.Connection = Depends(get_db)) -> dict:
    return GuideService(db).list_audit_guide()


@router.get("/required-docs", summary="사업장 비치·보존 서류 목록")
def list_required_docs(db: psycopg.Connection = Depends(get_db)) -> dict:
    return {"items": GuideService(db).list_required_docs()}


@router.get("/lifecycle", summary="고용 생애주기 (채용~퇴직) 단계별 준수사항")
def list_lifecycle(db: psycopg.Connection = Depends(get_db)) -> dict:
    return {"items": GuideService(db).list_lifecycle()}


@router.get("/recruit", summary="채용 단계 컴플라이언스")
def list_recruit(db: psycopg.Connection = Depends(get_db)) -> dict:
    return {"items": GuideService(db).list_recruit()}


# ─── 오버뷰 ────────────────────────────────────────
@router.get("/overview", response_model=GuideOverviewOut)
def overview(db: psycopg.Connection = Depends(get_db)) -> GuideOverviewOut:
    return GuideService(db).overview()


# ─── 챗봇 ──────────────────────────────────────────
@router.post("/chat", response_model=GuideChatOut, summary="가이드 챗봇 (RAG)")
def chat(
    payload: GuideChatIn,
    request: Request,
    db: psycopg.Connection = Depends(get_db),
) -> GuideChatOut:
    visitor = get_visitor(request)
    try:
        return GuideChatService(db).chat(payload, visitor=visitor)
    except CgrError:
        raise
    except Exception as e:
        raise CgrError(f"가이드 챗봇 응답 실패: {type(e).__name__}: {e}") from e
