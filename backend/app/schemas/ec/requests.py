"""ec 도메인 요청 DTO — 4단계 파이프라인.

원본 매핑 (cgr/api/routes/ec.py)
- POST /ec/extract         (Form + File)     → 스키마 없음 (라우터에서 UploadFile 직접 받음)
- POST /ec/classify/start  → ClassifyIn
- POST /ec/structure       → StructureIn
- POST /ec/analyze         → AnalyzeIn
- POST /ec/validate-field  → ValidateFieldIn
- POST /ec/generate        → GenerateIn
- POST /ec/generate-docx   → GenerateDocxIn
- POST /ec/chat            → ChatIn
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ClassifyIn(BaseModel):
    extracted_text: str = Field(..., description="`/ec/extract` 응답에서 받은 텍스트")


class StructureIn(BaseModel):
    extracted_text: str = Field(..., description="`/ec/extract` 응답에서 받은 텍스트")


class AnalyzeIn(BaseModel):
    """33-매핑 위반 분석 요청.

    - structured_data: `/ec/structure` 응답 (사용자가 검토·수정 완료한 8섹션 dict)
    - business_size:   '5인이상' / '5인미만' / '' (미지정 시 규모 무관 규칙만 적용)
    - worker_types:    ['정규직','기간제', ...]
    - legal_guidelines: RAG 검색으로 채울 상세 가이드라인 (선택)
    - case_id:         프론트 리뷰 세션 id (관리자 열람용)
    """

    structured_data: dict[str, Any]
    business_size: str = ""
    worker_types: list[str] = Field(default_factory=list)
    legal_guidelines: str = ""
    case_id: str = ""


class ValidateFieldIn(BaseModel):
    """단일 항목 즉시 재검토 (칸 편집 후)."""

    field: str = Field(..., description="재검토할 항목명 (analysis 의 '항목')")
    value: str = Field(default="", description="사용자가 입력·수정한 값")
    business_size: str = ""
    worker_types: list[str] = Field(default_factory=list)


class GenerateIn(BaseModel):
    """표준 계약서 텍스트 생성 요청."""

    analysis_result: dict[str, Any]
    user_overrides: dict[str, str] = Field(
        default_factory=dict,
        description="사용자가 직접 작성한 보완 표현 (항목명 → 텍스트, LLM 에게 '그대로 사용' 지시)",
    )


class GenerateDocxIn(BaseModel):
    """생성 완료 텍스트를 .docx 로 다운로드."""

    contract_text: str
    filename: str = "표준_근로계약서.docx"


class ChatHistoryTurn(BaseModel):
    role: str  # user | assistant
    content: str


class ChatIn(BaseModel):
    """EC 검토 결과 화면의 챗봇."""

    message: str = Field(..., description="사용자 질문")
    analysis_result: dict[str, Any] | None = Field(
        default=None, description="현재 보고 있는 분석 결과"
    )
    focused_item: str | None = Field(
        default=None, description="캐러셀에서 포커스 중인 항목명"
    )
    history: list[ChatHistoryTurn] = Field(default_factory=list)
