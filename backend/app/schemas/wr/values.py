"""슬롯·추출·판정 결과 데이터 모델 (pydantic)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
Comparator = Literal[">=", "<=", "==", "object_match", "presence", "interpret", "embed_match"]
Verdict = Literal["OK", "VIOLATION", "AMBIGUOUS"]
Status = Literal["OK", "VIOLATION", "MISSING", "ERROR", "AMBIGUOUS"]


class MasterValue(BaseModel):
    """슬롯의 기준값. 수치/객체/boolean 모두 표현."""
    value: Any | None = None
    unit: str | None = None
    note: str | None = None
    # object_match 용 추가 키 자유롭게 들어갈 수 있음
    model_config = {"extra": "allow"}


class ExampleViolation(BaseModel):
    text: str
    reason: str
    severity: Severity


class SlotDef(BaseModel):
    """원자 슬롯 정의 (atomic_slots_v0.yaml 1 entry)."""
    slot_id: str
    article: int
    parent_clause: str | None = None
    required: bool = False
    topic_meta: list[str] = Field(default_factory=list)
    extract_target: str
    extract_schema: dict[str, Any]
    master_value: MasterValue
    comparator: Comparator
    violation_severity: Severity | None = None
    missing_severity: Severity | None = None
    penalty: list[str] = Field(default_factory=list)
    master_db_ref: dict[str, Any] = Field(default_factory=dict)
    example_compliant: str | None = None
    example_violation: list[ExampleViolation] = Field(default_factory=list)
    fix_example: str | None = Field(
        default=None,
        description="부적합 시 사용자에게 표시할 시정 예시 문구 (취업규칙에 그대로 인용 가능)",
    )
    interpret_criteria: str | None = Field(
        default=None,
        description="comparator='interpret' 슬롯 전용 — LLM에게 적정/부적정 판단 기준을 제공",
    )
    # embed_match comparator 전용
    search_phrases: list[str] = Field(
        default_factory=list,
        description="comparator='embed_match' 슬롯 전용 — 사업장 본문에서 검출하려는 한국어 표현 1~5개",
    )
    threshold_ok: float | None = Field(
        default=None,
        description="embed_match: 코사인 유사도 ≥ 이면 OK (기본 0.65)",
    )
    threshold_violation: float | None = Field(
        default=None,
        description="embed_match: 코사인 유사도 < 이면 VIOLATION (기본 0.50, 그 사이 AMBIGUOUS)",
    )


class Catalog(BaseModel):
    version: str
    description: str | None = None
    slots: list[SlotDef]


class Extraction(BaseModel):
    """LLM 추출 결과 (슬롯 1개)."""
    slot_id: str
    extracted_value: Any | None = None     # 추출된 수치/문자/boolean/object
    quote: str | None = None               # 사업장 취업규칙에서 인용한 원문
    found: bool                            # 본문에서 명시적으로 찾았는지
    confidence: float | None = None        # LLM 자기 확신도 0~1
    # interpret 슬롯 전용 — LLM 의 적정성 판단
    verdict: Verdict | None = None
    verdict_reason: str | None = None


class Finding(BaseModel):
    """슬롯 단위 판정 결과."""
    slot_id: str
    article: int
    item_name: str
    extracted: Extraction
    expected: MasterValue
    comparator: Comparator
    status: Status
    severity: Severity = "INFO"
    reason: str = ""           # 코드 룰이 산출한 기술적 사유 (디버그용)
    user_reason: str | None = None  # LLM 이 감독관용으로 풀어쓴 평이한 사유
    fix_example: str | None = None  # 슬롯 정의에서 가져온 시정 예시 (부적합 시만)
    penalty: list[str] = Field(default_factory=list)


class ArticleResult(BaseModel):
    article: int
    title: str
    findings: list[Finding]
    article_text: str = ""
    scope: Literal["필수", "선택", "필수,선택"] | None = None


class OptionalDisplay(BaseModel):
    """선택 조 — 검사 안 함, 사용자에게 참고로만 표시."""
    article: int
    title: str
    scope: str = "선택"
    master_body: str = ""        # 마스터 D열 (취업규칙 안)
    master_guide: str = ""       # 마스터 E열 (작성시 착안사항)
    master_note: str = ""        # 마스터 F열 (참고)
    user_quote: str | None = None  # 사업장 본문에서 추출한 인용 (있으면)
    user_present: bool = False     # 사업장 본문에 관련 조항 존재 여부


class WorkplaceContext(BaseModel):
    """사업장 정보 — 검토 시작 시 사용자가 입력하면 N/A 슬롯 자동 SKIP.

    None 값은 '모름' — 슬롯이 활성 (보수적으로 검사).
    True/False 가 명시되면 그에 따라 SKIP 또는 활성.
    5인 이상 사업장은 디폴트 가정 (대부분 사업장에 해당).

    문서 종류별로 다른 필드를 사용:
      - 취업규칙(work_rules): shift_work·osha·chemical·workenv
      - 근로계약서(employment_contract): business_size·worker_types
      - 임금명세서(pay_statement): business_size·worker_types
    프론트 통합 폼은 모든 필드를 받고, 각 모듈이 자기 필드만 사용.
    """
    # ── 취업규칙용 ─────────────────────────────
    shift_work_used: bool | None = None    # 교대근로 도입
    osha_applicable: bool = True           # 산안법 적용 (시행령 별표1 비대상)
    chemical_handling: bool | None = None  # 화학물질 취급 (MSDS)
    workenv_measurement: bool | None = None  # 작업환경측정 대상

    # ── 근로계약서·임금명세서용 ────────────────
    business_size: Literal["5+", "5-", "any"] | None = None
    """사업장 규모: '5+' (5인이상) / '5-' (5인미만) / 'any' (모름) / None (미지정)."""

    worker_types: list[str] = Field(default_factory=list)
    """근로자 유형 다중 선택 — 정규직/기간제/단시간/일용직/연소자/외국인/외국인-농축어업.
    빈 배열이면 정규직만 가정."""


class Report(BaseModel):
    case_id: str
    source_file: str
    overall_label: Literal["적정", "부적정", "검토불가"] = "적정"
    article_results: list[ArticleResult]
    optional_displays: list[OptionalDisplay] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)  # severity별 count
    generated_at: str = ""
