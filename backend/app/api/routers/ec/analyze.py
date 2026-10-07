#
# 근로계약서 33-매핑 위반 분석.
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.10.02      이시영      최초 생성 (구조 이행 — 기존 backend/cgr 코드를 분리·이동)
# 2026.10.02      이시영      구조 조정 (web/ai 파트 디렉터리 → 도메인 단일 디렉터리)
# 2026.10.06      이시영      API 경로 표준화 (/api/cgr)
# 2026.10.07      이시영      화면 경로 /cgr·features 구조 이동, sync API 삭제, 업로드 원본 미저장
# 2026.10.07      이시영      검토번호 서버 발급, 변경 사유 주석 추가
#
# Author: 이시영
# Since: 2026.10.02
#
"""근로계약서 33-매핑 위반 분석."""
from __future__ import annotations

from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from app.core import jobs
from app.core.config import get_llm_model
from app.core.logging import bind_context, get_logger
from app.core.security import require_api_key
from app.schemas.ec.request import AnalyzeIn
from app.schemas.ec.response import AnalyzeResultOut, JobStartOut
from app.services.ec import analyze as analyze_service

log = get_logger(__name__)

# 프로그램명세서 AI-P02-005: POST /api/cgr/ec/analyses + GET /analyses/{job_id}
#   (기존: /api/v1/ec/analyze/start, /analyze/result/{job_id})
router = APIRouter(tags=["employment_contract"])


@router.post(
    "/analyses",
    response_model=JobStartOut,
    summary="비동기 분석 시작 — job_id 반환",
    dependencies=[Depends(require_api_key)],
)
def post_analyze_start(body: AnalyzeIn):
    bind_context(case=body.case_id)  # 로그 상관 — 이후 이 요청·잡의 모든 로그에 case 부착
    # 클로저로 입력 캡처 — 스레드에서 실행
    def _do() -> dict[str, Any]:
        result = analyze_service.run(
            body.structured_data,
            business_size=body.business_size,
            worker_types=body.worker_types,
            legal_guidelines=body.legal_guidelines,
        )
        # 상호작용 로그 — 입력(구조화 데이터)·출력(분석결과) 전체 + 원본 연결(case_id)
        try:
            import json as _json

            from app.repositories.shared import analytics as _an

            _an.log_interaction(
                kind="근로계약서",
                model=get_llm_model(),
                input_text=_json.dumps(body.structured_data, ensure_ascii=False)[:6000],
                output_text=_json.dumps(result, ensure_ascii=False)[:12000],
                visitor="",
                case_id=body.case_id or None,
            )
        except Exception as e:
            log.warning("무시된 예외 — %s: %s", type(e).__name__, e)
        return result

    job_id = jobs.start_job(_do)
    return JobStartOut(job_id=job_id)

@router.get(
    "/analyses/{job_id}",
    response_model=AnalyzeResultOut,
    summary="비동기 분석 결과 폴링",
    dependencies=[Depends(require_api_key)],
)
def get_analyze_result(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="분석 작업을 찾을 수 없어요. 작업이 만료됐거나 서버가 재시작됐을 수 있어요. 다시 시도해 주세요.",
        )
    return AnalyzeResultOut(
        status=job["status"],
        analysis_result=job["result"],
        error=job["error"],
        elapsed_sec=job["elapsed"],
        model=get_llm_model(),
    )
