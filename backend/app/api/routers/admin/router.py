"""관리자 라우터 — 원본 `cgr/api/routes/admin.py` 이관.

라우트
- GET    /admin/cache            LLM 캐시 통계
- DELETE /admin/cache            LLM 캐시 초기화 (admin)
- GET    /admin/settings         관리자 설정 조회
- PUT    /admin/settings         관리자 설정 편집 (admin)
- GET    /admin/prompts          프롬프트 목록 (admin)
- PUT    /admin/prompts          프롬프트 저장 (admin)
- GET    /admin/logs             LLM 상호작용 로그 (admin)
- GET    /admin/logs/{lid}       로그 상세 (admin)
- GET    /admin/uploads          업로드 목록 (admin)
"""
from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api.deps import get_db, require_admin, require_user
from app.core.exceptions import NotFoundError
from app.integrations.llm.cache import cache_clear, cache_stats
from app.repositories.shared import InteractionLogRepo, PromptRepo, SettingRepo, UploadRepo

router = APIRouter(prefix="/admin", tags=["admin"])


# ─── LLM 캐시 ─────────────────────────────────────
@router.get("/cache")
def get_cache_stats(_: None = Depends(require_user)) -> dict:
    return cache_stats()


@router.delete("/cache")
def delete_cache(_: None = Depends(require_admin)) -> dict:
    return {"deleted": cache_clear()}


# ─── 관리자 설정 ──────────────────────────────────
@router.get("/settings")
def get_settings_all(
    db: psycopg.Connection = Depends(get_db),
    _: None = Depends(require_user),
) -> dict:
    return SettingRepo(db).load_all()


class SettingsPatchIn(BaseModel):
    patch: dict


@router.put("/settings")
def put_settings(
    body: SettingsPatchIn,
    request: Request,
    db: psycopg.Connection = Depends(get_db),
    _: None = Depends(require_admin),
) -> dict:
    SettingRepo(db).bulk_update(body.patch, edited_by=_actor(request))
    return {"ok": True, "updated": list(body.patch.keys())}


# ─── 프롬프트 ─────────────────────────────────────
@router.get("/prompts")
def list_prompts(
    db: psycopg.Connection = Depends(get_db),
    _: None = Depends(require_admin),
) -> dict:
    rows = PromptRepo(db).list_all()  # list[dict]
    return {
        "prompts": [
            {
                "key": r["key"],
                "label": r["label"],
                "category": r.get("category"),
                "content": r["content"],
                "is_override": r["is_override"],
                "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
            }
            for r in rows
        ]
    }


class PromptSaveIn(BaseModel):
    key: str
    content: str
    label: str | None = None
    category: str | None = None


@router.put("/prompts")
def put_prompt(
    body: PromptSaveIn,
    request: Request,
    db: psycopg.Connection = Depends(get_db),
    _: None = Depends(require_admin),
) -> dict:
    PromptRepo(db).save(
        key=body.key,
        content=body.content,
        label=body.label,
        category=body.category,
        edited_by=_actor(request),
    )
    return {"ok": True, "key": body.key}


# ─── LLM 상호작용 로그 ───────────────────────────
@router.get("/logs")
def list_logs(
    limit: int = 50,
    offset: int = 0,
    kind: str | None = None,
    db: psycopg.Connection = Depends(get_db),
    _: None = Depends(require_admin),
) -> dict:
    total, rows = InteractionLogRepo(db).list(limit=limit, offset=offset, kind=kind)
    return {
        "total": total,
        "items": [
            {
                "id": r["id"],
                "ts": r["ts"].isoformat() if r.get("ts") else None,
                "kind": r.get("kind"),
                "model": r.get("model"),
                "input_preview": (r.get("input_text") or "")[:200],
                "output_preview": (r.get("output_text") or "")[:200],
                "case_uid": r.get("case_uid"),
            }
            for r in rows
        ],
    }


@router.get("/logs/{lid}")
def get_log(
    lid: int,
    db: psycopg.Connection = Depends(get_db),
    _: None = Depends(require_admin),
) -> dict:
    row = InteractionLogRepo(db).get(lid)
    if not row:
        raise NotFoundError(f"log id={lid}")
    return {
        "id": row["id"],
        "ts": row["ts"].isoformat() if row.get("ts") else None,
        "kind": row.get("kind"),
        "model": row.get("model"),
        "input_text": row.get("input_text"),
        "output_text": row.get("output_text"),
        "visitor": row.get("visitor"),
        "case_uid": row.get("case_uid"),
    }


# ─── 업로드 ───────────────────────────────────────
@router.get("/uploads")
def list_uploads(
    limit: int = 50,
    offset: int = 0,
    service: str | None = None,
    db: psycopg.Connection = Depends(get_db),
    _: None = Depends(require_admin),
) -> dict:
    total, rows = UploadRepo(db).list(limit=limit, offset=offset, service=service)
    return {
        "total": total,
        "items": [
            {
                "id": r["id"],
                "ts": r["ts"].isoformat() if r.get("ts") else None,
                "service": r.get("service"),
                "filename": r.get("filename"),
                "size_bytes": r.get("size_bytes"),
                "mime": r.get("mime"),
                "case_uid": r.get("case_uid"),
            }
            for r in rows
        ],
    }


def _actor(request: Request) -> str:
    """관리자 편집자 표기. header 'X-Admin-Actor' 존중 (미지정 시 'admin')."""
    return request.headers.get("X-Admin-Actor", "admin")
