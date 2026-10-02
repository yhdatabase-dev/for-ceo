"""노무 주제 코퍼스 조회."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.security import require_api_key
from app.repositories import base as _db

router = APIRouter(tags=["topics"])


@router.get(
    "/corpus",
    summary="주제 코퍼스 전체 (프론트엔드 hover/excerpt 용)",
    description=(
        "노무사회 31개 주제 × 1,769 섹션 본문을 한 번에 반환.\n"
        "프론트엔드는 모듈 캐시로 1회만 호출.\n\n"
        "body_friendly 가 있으면 그것이 LLM paraphrase 본문.\n"
        "원문(body)만 필요한 호출자는 body_friendly 를 무시하면 됨."
    ),
    dependencies=[Depends(require_api_key)],
    response_class=JSONResponse,
)
def get_corpus() -> JSONResponse:
    """SQLite topic + topic_section → 중첩 dict.

    빈 결과면 빈 dict `{}` — 프론트는 fallback 으로 빌드타임 JSON 을 쓰지 않고
    백엔드 응답을 그대로 신뢰한다.
    """
    out: dict[str, dict[str, dict[str, str]]] = {}
    try:
        with _db.connect() as conn:
            cur = conn.execute(
                """
                SELECT
                  t.code      AS db_code,
                  ts.section_no AS section_no,
                  ts.title     AS title,
                  ts.body_original AS body,
                  ts.body_friendly AS body_friendly
                FROM topic_section ts
                JOIN topic t ON t.id = ts.topic_id
                ORDER BY t.code, ts.section_no
                """
            )
            for r in cur.fetchall():
                db_code = r["db_code"]
                if not db_code:
                    continue
                bucket = out.setdefault(db_code, {})
                section_no = r["section_no"] or ""
                if not section_no:
                    continue
                entry: dict[str, str] = {
                    "title": r["title"] or "",
                    "body": r["body"] or "",
                }
                if r["body_friendly"]:
                    entry["body_friendly"] = r["body_friendly"]
                bucket[section_no] = entry
    except Exception:
        # DB 부재·쿼리 실패 → 빈 코퍼스. 프론트는 4순위 fallback 메시지로 동작.
        out = {}

    return JSONResponse(
        content=out,
        headers={
            # 코퍼스는 seed 시점에만 바뀜 → 길게 캐시 가능
            "Cache-Control": "public, max-age=3600",
        },
    )
