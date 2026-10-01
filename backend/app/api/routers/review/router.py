"""review(WR) 라우터 — 원본 `cgr/api/routes/review.py` + `wr_classify.py` 이관.

핵심 라우트 (동기 위주)
- POST /review              : 취업규칙 검토 (파일 → 판정)
- POST /review/classify     : 근로환경 1차 분류
- POST /review/generate     : 수정본 생성 (동기)
- POST /review/generate-docx: 수정본 → .docx 다운로드
- POST /review/comparison-docx : 대비표 .docx
- GET  /review/{case_id}    : 이력 상세

예외 처리 규칙 (원본 스타일 → v2 도메인 예외)
- 서비스 호출부: `try/except CgrError → raise` + `except Exception → CgrError` 로 감쌈
    · 하위 도메인 예외(LLMError 502·NotFoundError 404 등) 는 그대로 흘려보내고
    · 예상 못한 예외만 500 으로 감싸서 detail 보존
- 부수 작업(임시 파일 삭제 등): `except Exception → log.warning` 로 조용히 넘어감
- 로그: `app.core.logging.get_logger(__name__)` 사용

TODO(하위 호환): 원본의 /review/start · /result/{job_id} 비동기 잡 라우트는
                 별도 파일 (`review_jobs.py`) 로 분리.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

import psycopg
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response

from app.api.deps import get_db, get_visitor, require_user
from app.core.exceptions import CgrError, NotFoundError, UploadError
from app.core.logging import get_logger
from app.integrations.parsers.docx_writer import text_to_docx, wr_comparison_to_docx
from app.repositories.shared import HistoryRepo
from app.schemas.review import (
    ComparisonDocxIn,
    GenerateDocxIn,
    GenerateIn,
    GenerateOut,
    ReviewFullOut,
    ReviewSummaryOut,
    WrClassifyIn,
    WrClassifyOut,
)
from app.schemas.shared import WorkplaceContextIn
from app.services.review import WrClassifyService, WrReviewService, WrReviseService

log = get_logger(__name__)

# 라우터 전체에 인증 적용 — 원본은 라우트마다 dependencies=[Depends(require_api_key)]
# v2 는 라우터 레벨 dependencies 로 일괄 적용 (모든 하위 라우트에 자동 상속)
router = APIRouter(
    prefix="/review",
    tags=["review"],
    dependencies=[Depends(require_user)],
)


# ─── 검토 ─────────────────────────────────────────
@router.post("",
            response_model=ReviewFullOut,
            summary="취업 규칙 검토",
            description=(
                "- `work_rules` (기본): 취업규칙 → 5-Bucket (누락·위반·주의·검토필요·적정)\n"
                "사업장 정보 폼은 통합 — 각 문서가 자기에게 필요한 필드만 사용.\n"
                "- 취업규칙: shift_work·osha·chemical·workenv\n"
            )
)
async def review(
    file: UploadFile = File(..., description="검토 대상 파일 (.docx/.hwp/.hwpx/.pdf/.txt)"),
    document_type: str = Form("work_rules"), # 취업규칙 문서 타입
    shift_work_used: bool | None = Form(None, description="교대근로 도입여부"),
    osha_applicable: bool | None = Form(True, description="산업안전보건법 적용 업종"),
    chemical_handling: bool | None = Form(None, description="화학물질 취급"),
    workenv_measurement: bool | None = Form(None, description="작업환경측정 대상"),
    business_size: str = Form("", description="사업장 규모(5인이상 / 5인미만 / (빈 문자열))"),
    worker_types: str = Form("", description="근로자 유형(정규직/기간제/단시간/일용직/연소자/외국인)"),   # CSV 문자열
    summary_only: bool = Form(default=False, description="true면 finding 상세 제외하고 summary 만"),
    db: psycopg.Connection = Depends(get_db), # DB 커넥션
) -> ReviewFullOut:
    """취업규칙 검토.

    document_type='work_rules' 만 지원 (EC 는 `/ec/*` 로 분리).
    """
    if not file.filename:
        raise UploadError("filename 이 비어있습니다.")

    ctx = WorkplaceContextIn(
        shift_work_used=shift_work_used, 
        osha_applicable=osha_applicable,
        chemical_handling=chemical_handling,
        workenv_measurement=workenv_measurement, 
        business_size=business_size, 
        worker_types=[w.strip() for w in worker_types.split(",") if w.strip()], # 정규직/기간제/단시간/일용직/연소자/외국인
    )

    # 임시 파일 저장
    suffix = Path(file.filename).suffix.lower()
    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        try:
            # 취업규칙 검토 진행
            return WrReviewService(db).review_file(
                tmp_path, context=ctx, summary_only=summary_only
            )
        except CgrError:
            # 도메인 예외 (LLMError · ParseError 등) 는 그대로 → 전역 핸들러가 알맞은 status 응답
            raise
        except Exception as e:
            # 예상 못한 예외 → 500 으로 감쌈 (원인 e 는 __cause__ 로 보존)
            raise CgrError(
                f"취업규칙 검토 실패: {type(e).__name__}: {e}",
            ) from e
    finally:
        # 임시 파일 삭제
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception as e:
            log.warning("무시된 예외 — %s: %s", type(e).__name__, e)


# ─── 근로환경 분류 ────────────────────────────────
@router.post(
    "/classify",
    response_model=WrClassifyOut,
    summary="근로환경 1차 분류 (LLM)",
    description="취업규칙 텍스트로부터 교대근로·산안법 적용·화학물질·작업환경측정 여부 자동 판별.",
)
def classify(payload: WrClassifyIn, db: psycopg.Connection = Depends(get_db)) -> WrClassifyOut:
    try:
        return WrClassifyService(db).run(payload)
    except CgrError:
        raise
    except Exception as e:
        raise CgrError(
            f"근로환경 분류 실패: {type(e).__name__}: {e}",
        ) from e


# ─── 수정본 생성 ──────────────────────────────────
@router.post(
    "/generate",
    response_model=GenerateOut,
    summary="취업규칙 수정본 생성",
    description=(
        "사용자가 지정한 수정 목록만 반영해 취업규칙 원문을 재생성. "
        "표준 취업규칙이 있으면 준용 기준으로 사용. "
        "변경 위치는 【수정】…【/수정】 마커로 표시."
    ),
)
def generate(payload: GenerateIn, db: psycopg.Connection = Depends(get_db)) -> GenerateOut:
    # TODO: 표준 취업규칙 텍스트 로드 (원본은 data/standards/표준취업규칙_2026.txt)
    standard_text = None
    try:
        return WrReviseService(db).run(payload, standard_text=standard_text)
    except CgrError:
        raise
    except Exception as e:
        raise CgrError(
            f"수정본 생성 실패: {type(e).__name__}: {e}",
        ) from e


@router.post("/generate-docx", summary="수정 취업규칙 → .docx 다운로드")
def generate_docx(payload: GenerateDocxIn) -> Response:
    try:
        content = text_to_docx(payload.contract_text, title="수정 취업규칙")
    except CgrError:
        raise
    except Exception as e:
        raise CgrError(
            f"DOCX 변환 실패: {type(e).__name__}: {e}",
        ) from e
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{payload.filename}"'},
    )


@router.post("/comparison-docx", summary="조별 원문/수정본 대비표 → .docx 다운로드")
def comparison_docx(payload: ComparisonDocxIn) -> Response:
    try:
        content = wr_comparison_to_docx(payload.rows, effective_date=payload.effective_date)
    except CgrError:
        raise
    except Exception as e:
        raise CgrError(
            f"대비표 DOCX 변환 실패: {type(e).__name__}: {e}",
        ) from e
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{payload.filename}"'},
    )


# ─── 이력 상세 ────────────────────────────────────
@router.get(
    "/{case_uid}",
    response_model=ReviewSummaryOut,
    summary="검토 이력 상세 조회 (case_uid)",
)
def get_by_case(case_uid: str, db: psycopg.Connection = Depends(get_db)) -> ReviewSummaryOut:
    row = HistoryRepo(db).get_by_case_uid(case_uid)
    if not row:
        raise NotFoundError(f"case_uid={case_uid} 이력을 찾을 수 없습니다.")
    return ReviewSummaryOut(
        case_id=row["case_uid"],
        filename=row.get("filename") or "",
        overall_label=row.get("overall_label") or "",
        summary=row.get("by_bucket") or {},
        n_findings=row.get("n_findings") or 0,
        elapsed_sec=0.0,
        llm_model=row.get("llm_model") or "",
    )
