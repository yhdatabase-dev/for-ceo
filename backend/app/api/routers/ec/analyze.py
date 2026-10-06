"""근로계약서 33-매핑 위반 분석."""
from __future__ import annotations

import time
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
from app.schemas.ec.response import AnalyzeOut, AnalyzeResultOut, JobStartOut
from app.services.ec import analyze as analyze_service

log = get_logger(__name__)

router = APIRouter(tags=["employment_contract"])


@router.post(
    "/analyses/sync",
    response_model=AnalyzeOut,
    summary="구조화 데이터 + 컨텍스트 → 33매핑 위반 분석",
    dependencies=[Depends(require_api_key)],
)
def post_analyze(body: AnalyzeIn):
    bind_context(case=body.case_id)  # 로그 상관 — 이후 이 요청·잡의 모든 로그에 case 부착
    t0 = time.time()
    try:
        result = analyze_service.run(
            body.structured_data,
            business_size=body.business_size,
            worker_types=body.worker_types,
            legal_guidelines=body.legal_guidelines,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"분석 실패: {type(e).__name__}: {e}",
        )
    try:
        import json as _json

        from app.repositories.shared import analytics as _an

        _an.log_interaction(
            kind="근로계약서",
            model=get_llm_model(),
            input_text=_json.dumps(body.structured_data, ensure_ascii=False)[:4000],
            output_text=_json.dumps(result, ensure_ascii=False)[:8000],
            visitor="",
            case_id=body.case_id or None,
        )
    except Exception as e:
        log.warning("무시된 예외 — %s: %s", type(e).__name__, e)
    return AnalyzeOut(
        analysis_result=result,
        elapsed_sec=round(time.time() - t0, 2),
        model=get_llm_model(),
    )

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
