#
# 노무 주제 코퍼스 조회.
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.05.28      kimzion77   최초 생성
# 2026.10.02      이시영      구조 이행 (backend/cgr → backend/app)
# 2026.10.02      이시영      구조 조정 (web/ai 파트 디렉터리 → 도메인 단일 디렉터리)
# 2026.10.06      이시영      PostgreSQL 전환, 노무가이드 삭제
# 2026.10.06      이시영      API 경로 표준화 (/api/cgr)
# 2026.10.07      이시영      검토번호 서버 발급, 변경 사유 주석 추가
#
# Author: kimzion77
# Since: 2026.05.28
#
"""노무 주제 코퍼스 조회."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.security import require_api_key
from app.repositories import base as _db

# 개발표준정의서 API 엔드포인트: /api/cgr/<도메인>/<리소스> — 복수형 케밥, 동사·버전 금지
#   GET /api/cgr/topics/sections (기존: /api/v1/topics/corpus)
router = APIRouter(tags=["topics"])


@router.get(
    "/sections",
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
    """tb_tpc_mstr(주제) + tb_tpc_sctn(섹션) → 중첩 dict.

    테이블정의서 ai.tb_tpc_mstr · ai.tb_tpc_sctn 조회 (기존: SQLite topic · topic_section).

    빈 결과면 빈 dict `{}` — 프론트는 fallback 으로 빌드타임 JSON 을 쓰지 않고
    백엔드 응답을 그대로 신뢰한다.
    """
    out: dict[str, dict[str, dict[str, str]]] = {}
    try:
        with _db.connect() as conn:
            cur = conn.execute(
                """
                SELECT
                  t.tpc_cd_nm    AS db_code,
                  ts.sctn_no     AS section_no,
                  ts.sctn_nm     AS title,
                  ts.mtxt_cn     AS body,
                  ts.frd_mtxt_cn AS body_friendly
                FROM ai.tb_tpc_sctn ts
                JOIN ai.tb_tpc_mstr t ON t.tpc_sn = ts.tpc_sn
                ORDER BY t.tpc_cd_nm, ts.sctn_no
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
