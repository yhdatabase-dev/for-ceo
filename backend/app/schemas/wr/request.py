"""취업규칙(wr) 요청 스키마."""
from __future__ import annotations

from pydantic import BaseModel, Field


# ─── 검토 ────────────────────────────────────
class WorkplaceContextIn(BaseModel):
    """사업장 정보 입력 (검토 시 슬롯 SKIP 판단용)."""

    shift_work_used: bool | None = Field(default=None, description="교대근로 도입 여부 (None=모름)")
    osha_applicable: bool | None = Field(default=True, description="산업안전보건법 적용 업종")
    chemical_handling: bool | None = Field(default=None, description="화학물질 취급")
    workenv_measurement: bool | None = Field(default=None, description="작업환경측정 대상")

# ─────────────────────────────────────────────
# 수정본 생성 — 원문 보존 + 사용자 수정 목록만 반영 (start + poll)
#
#   POST /api/cgr/wr/revisions                → {job_id} 즉시 반환, 백그라운드 생성
#   GET  /api/cgr/wr/revisions/{job_id}       → {status, revised_text, ...} 폴링
#   POST /api/cgr/wr/revision-documents       → 본문 → .docx 다운로드
#
# 철학: 문제없는 조항은 두고, 사용자가 담은 수정 항목만 교체·추가해 전문 출력.
# 주의: GET /review/{case_id} (단일 세그먼트) 보다 먼저 선언 — 경로 충돌 방지.
# ─────────────────────────────────────────────
class CorrectionIn(BaseModel):
    name: str = Field(..., description="항목명 (예: 제24조 연차유급휴가)")
    now: str = Field(default="", description="현재 표현 (원문 발견 내용)")
    fix: str = Field(..., description="수정 문구 (사용자 확정 표현)")

class GenerateIn(BaseModel):
    original_text: str = Field(..., description="추출된 취업규칙 원문 전체")
    corrections: list[CorrectionIn] = Field(
        ..., description="사용자가 수정본에 담은 항목 목록"
    )

class GenerateDocxIn(BaseModel):
    contract_text: str = Field(
        ..., description="이미 생성된 수정본 본문 (혹은 사용자가 편집한 내용)"
    )
    filename: str = Field(
        default="취업규칙_수정본.docx",
        description="다운로드 파일명 (Content-Disposition)",
    )

class ComparisonDocxIn(BaseModel):
    rows: list[dict] = Field(
        default_factory=list,
        description="신구대조표 행 목록 [{article,title,before,after,remark}]",
    )
    effective_date: str = Field(default="", description="개정 취업규칙 시행일")
    filename: str = Field(default="취업규칙_신구대조표.docx", description="다운로드 파일명")

class WrClassifyIn(BaseModel):
    extracted_text: str = Field(..., description="추출된 취업규칙 텍스트")
