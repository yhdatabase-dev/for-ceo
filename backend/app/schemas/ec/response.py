#
# 근로계약서(ec) 응답 스키마.
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.10.02      이시영      최초 생성 (구조 이행 — 기존 backend/cgr 코드를 분리·이동)
# 2026.10.06      이시영      API 경로 표준화 (/api/cgr)
# 2026.10.07      이시영      화면 경로 /cgr·features 구조 이동, sync API 삭제, 업로드 원본 미저장
# 2026.10.07      이시영      챗봇 기능 삭제
# 2026.10.07      이시영      검토번호 서버 발급, 변경 사유 주석 추가
#
# Author: 이시영
# Since: 2026.10.02
#
"""근로계약서(ec) 응답 스키마."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ─── 근로계약서 (EC) ─────────────────────────
class EcFindingOut(BaseModel):
    """근로계약서 검토 결과 1건 — 3-Bucket 분류 (적절/보완필요/부적절)."""

    slot_id: str
    field: str
    bucket: str  # 적절 / 보완필요 / 부적절
    severity: str  # CRITICAL/HIGH/MEDIUM/LOW
    present: bool
    extracted: str = ""
    reason: str = ""
    required_content: str = ""
    purpose: str = ""
    laws: list[str] = Field(default_factory=list)
    topic_meta: list[str] = Field(default_factory=list)
    fix_example: str = ""

class EcReviewOut(BaseModel):
    """근로계약서 검토 응답."""

    case_id: str
    filename: str
    doc: str = "employment_contract"
    overall_label: str  # 적절 / 보완필요 / 부적절 / 검토불가
    summary: dict[str, int]  # 3-Bucket 카운트
    n_findings: int
    skipped: int = 0
    elapsed_sec: float
    findings: list[EcFindingOut] = Field(default_factory=list)

# ─────────────────────────────────────────────
# 1) POST /api/cgr/ec/extractions
# ─────────────────────────────────────────────
class JobStartOut(BaseModel):
    job_id: str

# 프로그램명세서 AI-P02-001: 검토 건 번호(case_id)는 서버가 UUID 로 발급해 응답에 돌려준다.
#   비동기 잡이라 접수 응답에서 바로 돌려줘 화면이 그 번호로 진행한다. (기존: job_id 만 반환)
class ExtractStartOut(BaseModel):
    job_id: str
    case_id: str = Field(..., description="검토 건 식별자 (서버 생성 UUID)")

class ExtractResultOut(BaseModel):
    status: str = Field(..., description="pending | done | error")
    extracted_text: str | None = None
    filename: str = ""
    # 프로그램명세서 AI-P02-001: 검토 건 번호(case_id)는 서버가 UUID 로 발급해 응답에 돌려준다.
    case_id: str = ""
    error: str | None = None
    elapsed_sec: float = 0.0
    model: str = ""

class ClassifyResultOut(BaseModel):
    status: str = Field(..., description="pending | done | error")
    worker_types: list[str] | None = None
    doc_kind: str | None = None
    reason: str | None = None
    error: str | None = None
    elapsed_sec: float = 0.0

class StructureResultOut(BaseModel):
    status: str = Field(..., description="pending | done | error")
    structured_data: dict[str, Any] | None = None
    error: str | None = None
    elapsed_sec: float = 0.0
    model: str = ""

class ValidateFieldOut(BaseModel):
    적절성: str = Field(..., description="적절 | 보완필요 | 부적정")
    이유: str = ""
    작성예시: str = Field(default="", description="부적정·보완필요 시 그대로 쓸 수 있는 간단 예시")

# ─────────────────────────────────────────────
# 3-b) 비동기 분석 — 게이트웨이 타임아웃 우회 (start + poll)
#
#   POST /api/cgr/ec/analyses           → {job_id} 즉시 반환, 백그라운드 분석
#   GET  /api/cgr/ec/analyses/{job_id}  → {status, analysis_result, ...} 폴링
#
# 동기 /analyze 는 하위호환·로컬용으로 유지. 프론트는 start+poll 을 사용.
# (JobStartOut 은 위 extract 섹션에서 정의됨 — 재사용)
# ─────────────────────────────────────────────
class AnalyzeResultOut(BaseModel):
    status: str = Field(..., description="pending | done | error")
    analysis_result: dict[str, Any] | None = None
    error: str | None = None
    elapsed_sec: float = 0.0
    model: str = ""

class GenerateResultOut(BaseModel):
    status: str = Field(..., description="pending | done | error")
    contract_text: str | None = None
    error: str | None = None
    elapsed_sec: float = 0.0
    model: str = ""

