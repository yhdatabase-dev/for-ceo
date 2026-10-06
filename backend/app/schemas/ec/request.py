"""근로계약서(ec) 요청 스키마."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# 1-c) 비동기 분류 — AI 1차 근로자 유형 판별 (사용자는 확인만)
# ─────────────────────────────────────────────
class ClassifyIn(BaseModel):
    extracted_text: str = Field(..., description="추출된 계약서 텍스트")

# ─────────────────────────────────────────────
# 2) POST /api/cgr/ec/structures
# ─────────────────────────────────────────────
class StructureIn(BaseModel):
    extracted_text: str = Field(..., description="`/ec/extractions` 의 응답에서 받은 텍스트")

# ─────────────────────────────────────────────
# 3) POST /api/cgr/ec/analyses
# ─────────────────────────────────────────────
class AnalyzeIn(BaseModel):
    structured_data: dict[str, Any] = Field(
        ..., description="Step2 에서 사용자가 검토·수정 완료한 8섹션 dict"
    )
    business_size: str = Field(default="", description="5인이상 / 5인미만 / (빈 문자열)")
    worker_types: list[str] = Field(
        default_factory=list,
        description="정규직 / 기간제 / 단시간 / 일용직 / 연소자 / 외국인 / 외국인(농축어업)",
    )
    legal_guidelines: str = Field(
        default="",
        description="(선택) RAG 검색으로 채울 상세 가이드라인. 추후 단계에서 자동 주입.",
    )
    case_id: str = Field(
        default="",
        description="프론트 리뷰 세션 id — 업로드 원본 파일과 로그를 연결(관리자 열람용).",
    )

# ─────────────────────────────────────────────
# 3-c) POST /api/cgr/ec/field-validations — 단일 항목 즉시 재검토 (칸 편집 후)
# ─────────────────────────────────────────────
class ValidateFieldIn(BaseModel):
    field: str = Field(..., description="재검토할 항목명 (analysis 의 '항목')")
    value: str = Field(default="", description="사용자가 입력·수정한 칸 값")
    business_size: str = Field(default="")
    worker_types: list[str] = Field(default_factory=list)

# ─────────────────────────────────────────────
# 4) POST /api/cgr/ec/drafts
# ─────────────────────────────────────────────
class GenerateIn(BaseModel):
    analysis_result: dict[str, Any] = Field(
        ..., description="`/ec/analyses` 의 응답 dict 전체"
    )
    user_overrides: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "사용자가 결과 페이지에서 SuggestBlock 을 통해 직접 작성한 보완 표현. "
            "항목명 → 본인 입력 텍스트. LLM 에게 '그대로 사용' 으로 강조 전달."
        ),
    )

# ─────────────────────────────────────────────
# 4-b) POST /api/cgr/ec/documents — 표준 계약서 .docx 다운로드
# ─────────────────────────────────────────────
class GenerateDocxIn(BaseModel):
    contract_text: str = Field(
        ..., description="이미 생성된 본문 (혹은 사용자가 편집한 내용)"
    )
    filename: str = Field(
        default="표준_근로계약서.docx",
        description="다운로드 파일명",
    )

# ─────────────────────────────────────────────
# 5) POST /api/cgr/ec/chat-messages — 대화형 챗봇 (SFR-001)
# ─────────────────────────────────────────────
class ChatHistoryTurn(BaseModel):
    role: str  # "user" | "assistant"
    content: str

class ChatIn(BaseModel):
    message: str = Field(..., description="사용자 질문 (자연어)")
    analysis_result: dict[str, Any] | None = Field(
        default=None,
        description="현재 사용자가 보고 있는 분석 결과 (있으면 컨텍스트로 활용)",
    )
    focused_item: str | None = Field(
        default=None,
        description="사용자가 캐러셀에서 보고 있는 항목명 (예: '임금')",
    )
    history: list[ChatHistoryTurn] = Field(
        default_factory=list,
        description="이전 대화 (role/content). 최근 6턴까지만 활용.",
    )
