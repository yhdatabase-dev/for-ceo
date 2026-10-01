"""ec 라우터 — 원본 `cgr/api/routes/ec.py` 이관.

v2 는 비동기 잡(start + poll) 패턴을 제거하고 동기 호출로 통일.
프론트가 start+poll 을 이미 쓴다면 여기 라우트를 추가해야 함 (아래 TODO 표시).

핵심 라우트 (동기)
- POST /ec/extract          : 파일 → 텍스트
- POST /ec/classify         : 텍스트 → 근로자 유형
- POST /ec/structure        : 텍스트 → 8섹션
- POST /ec/analyze          : 8섹션 → 33-매핑 위반 분석
- POST /ec/validate-field   : 단일 항목 재검토
- POST /ec/generate         : 표준 계약서 생성
- POST /ec/generate-docx    : 텍스트 → .docx 다운로드
- POST /ec/chat             : 챗봇

예외 처리 규칙 (review 라우터와 동일)
- 서비스 호출부: `try/except CgrError → raise / except Exception → CgrError(...) from e`
- 부수 작업(임시 파일 삭제): `except Exception → log.warning`
- 로그: `app.core.logging.get_logger(__name__)`

TODO(하위 호환): 원본의 /ec/*/start · /ec/*/result/{job_id} 비동기 잡 라우트는
                별도 파일 (`ec_jobs.py`) 로 분리.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from time import perf_counter

import psycopg
from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response

from app.api.deps import get_db, get_visitor, require_user
from app.core.exceptions import CgrError, UploadError
from app.core.logging import get_logger
from app.integrations.parsers import parse_document
from app.schemas.ec import (
    AnalyzeIn,
    AnalyzeOut,
    ChatIn,
    ChatOut,
    ClassifyIn,
    ClassifyOut,
    ExtractOut,
    GenerateDocxIn,
    GenerateIn,
    GenerateOut,
    StructureIn,
    StructureOut,
    ValidateFieldIn,
    ValidateFieldOut,
)
from app.services.ec import (
    AnalyzeService,
    ChatService,
    ClassifyService,
    GenerateService,
    StructureService,
    ValidateFieldService,
)

log = get_logger(__name__)

# 라우터 전체에 인증 적용
router = APIRouter(
    prefix="/ec",
    tags=["ec"],
    dependencies=[Depends(require_user)],
)


# ─── extract ─────────────────────────────────────
@router.post("/extract", response_model=ExtractOut, summary="파일 → 텍스트 추출")
async def extract(
    file: UploadFile = File(..., description="추출 대상 파일"),
) -> ExtractOut:
    """파일 업로드 → 텍스트 추출.

    지원 확장자: .docx, .pdf, .txt, .hwp, .hwpx, 이미지(Vision OCR).
    """
    if not file.filename:
        raise UploadError("filename 이 비어있습니다.")

    t0 = perf_counter()
    suffix = Path(file.filename).suffix.lower()
    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        try:
            text = parse_document(tmp_path)
        except CgrError:
            raise
        except Exception as e:
            raise CgrError(
                f"파일 추출 실패: {type(e).__name__}: {e}",
            ) from e
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception as e:
            log.warning("무시된 예외 — %s: %s", type(e).__name__, e)

    elapsed = perf_counter() - t0
    return ExtractOut(
        extracted_text=text,
        filename=file.filename,
        elapsed_sec=elapsed,
        model="",
    )


# ─── classify ────────────────────────────────────
@router.post("/classify", response_model=ClassifyOut, summary="근로자 유형 분류")
def classify(payload: ClassifyIn, db: psycopg.Connection = Depends(get_db)) -> ClassifyOut:
    try:
        return ClassifyService(db).run(payload)
    except CgrError:
        raise
    except Exception as e:
        raise CgrError(f"근로자 유형 분류 실패: {type(e).__name__}: {e}") from e


# ─── structure ───────────────────────────────────
@router.post("/structure", response_model=StructureOut, summary="계약서 8섹션 구조화")
def structure(payload: StructureIn, db: psycopg.Connection = Depends(get_db)) -> StructureOut:
    try:
        return StructureService(db).run(payload)
    except CgrError:
        raise
    except Exception as e:
        raise CgrError(f"계약서 구조화 실패: {type(e).__name__}: {e}") from e


# ─── analyze ─────────────────────────────────────
@router.post("/analyze", response_model=AnalyzeOut, summary="위반 항목 분석 (33-매핑)")
def analyze(
    payload: AnalyzeIn,
    request: Request,
    db: psycopg.Connection = Depends(get_db),
) -> AnalyzeOut:
    try:
        return AnalyzeService(db).run(payload, visitor=get_visitor(request))
    except CgrError:
        raise
    except Exception as e:
        raise CgrError(f"위반 항목 분석 실패: {type(e).__name__}: {e}") from e


# ─── validate-field ──────────────────────────────
@router.post("/validate-field", response_model=ValidateFieldOut, summary="단일 항목 재검토")
def validate_field(
    payload: ValidateFieldIn, db: psycopg.Connection = Depends(get_db)
) -> ValidateFieldOut:
    try:
        return ValidateFieldService(db).run(payload)
    except CgrError:
        raise
    except Exception as e:
        raise CgrError(f"항목 재검토 실패: {type(e).__name__}: {e}") from e


# ─── generate ────────────────────────────────────
@router.post("/generate", response_model=GenerateOut, summary="표준 계약서 생성")
def generate(payload: GenerateIn, db: psycopg.Connection = Depends(get_db)) -> GenerateOut:
    try:
        return GenerateService(db).run(payload)
    except CgrError:
        raise
    except Exception as e:
        raise CgrError(f"계약서 생성 실패: {type(e).__name__}: {e}") from e


@router.post("/generate-docx", summary="계약서 텍스트 → .docx 다운로드")
def generate_docx(payload: GenerateDocxIn) -> Response:
    from app.integrations.parsers.docx_writer import text_to_docx

    try:
        content = text_to_docx(
            payload.contract_text,
            title="표준 근로계약서",
            subtitle="",
            footer_note="",
        )
    except CgrError:
        raise
    except Exception as e:
        raise CgrError(f"DOCX 변환 실패: {type(e).__name__}: {e}") from e

    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{payload.filename}"'
        },
    )


# ─── chat ────────────────────────────────────────
@router.post("/chat", response_model=ChatOut, summary="EC 챗봇")
def chat(
    payload: ChatIn,
    request: Request,
    db: psycopg.Connection = Depends(get_db),
) -> ChatOut:
    try:
        return ChatService(db).run(payload, visitor=get_visitor(request))
    except CgrError:
        raise
    except Exception as e:
        raise CgrError(f"EC 챗봇 응답 실패: {type(e).__name__}: {e}") from e
