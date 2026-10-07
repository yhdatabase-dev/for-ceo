#
# 익명 방문 핑.
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.10.02      이시영      최초 생성 (구조 이행 — 기존 backend/cgr 코드를 분리·이동)
# 2026.10.02      이시영      구조 조정 (web/ai 파트 디렉터리 → 도메인 단일 디렉터리)
# 2026.10.06      이시영      API 경로 표준화 (/api/cgr)
# 2026.10.07      이시영      검토번호 서버 발급, 변경 사유 주석 추가
#
# Author: 이시영
# Since: 2026.10.02
#
"""익명 방문 핑."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.security import require_api_key
from app.core.upload import anon_visitor
from app.repositories.shared import analytics
from app.schemas.track.request import TrackIn

# 개발표준정의서 API 엔드포인트: /api/cgr/<도메인>/<리소스> — 복수형 케밥, 동사·버전 금지
#   POST /api/cgr/track/visits (기존: /api/v1/track)
router = APIRouter(tags=["track"])


@router.post("/visits", summary="익명 방문 핑", dependencies=[Depends(require_api_key)])
async def post_track(body: TrackIn, request: Request) -> dict:
    visitor = (body.visitor or "").strip()[:64] or anon_visitor(request)
    analytics.log_visit(visitor, body.page, body.service)
    return {"ok": True}
