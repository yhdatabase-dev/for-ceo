"""근로계약서 검토 엔진.

흐름:
  1. parsers/dispatcher.py 로 파일 → 텍스트
  2. WorkplaceContext (business_size + worker_types) 로 슬롯 필터
  3. 각 슬롯에 대해 텍스트에서 키워드/내용 검색 (1차: 단순 presence)
  4. classify_ec() 로 3-Bucket 분류
  5. 종합 리포트 반환

본 1단계는 LLM 호출 없이 키워드 매칭만 수행하는 baseline.
2단계에서 LLM 추출 (cgr.extract 패턴) 을 ec 슬롯용으로 추가 가능.
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.repositories.ec.catalog import EcSlot, load_ec_catalog
from app.services.ai.ec.verdict import ECBucket, classify_ec, overall_label
from app.schemas.wr.values import WorkplaceContext
from app.integrations.parsers.dispatcher import parse_to_text


class EcFinding(BaseModel):
    """근로계약서 검토 결과 1건."""

    slot_id: str
    field: str
    bucket: ECBucket
    severity: str
    present: bool
    """본문에 항목이 기재되어 있는지."""

    extracted: str = ""
    """본문에서 추출된 표현 (있으면)."""

    reason: str = ""
    """판정 사유 (사람용)."""

    required_content: str = ""
    """기재되어야 할 내용 (가이드)."""

    purpose: str = ""
    laws: list[str] = Field(default_factory=list)
    topic_meta: list[str] = Field(default_factory=list)
    fix_example: str = ""


class EcReport(BaseModel):
    """근로계약서 검토 리포트."""

    case_id: str
    source_file: str
    doc: Literal["employment_contract"] = "employment_contract"
    overall_label: str = "적절"
    """종합 판정 — 적절 / 보완필요 / 부적절."""

    findings: list[EcFinding] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
    """3-Bucket 카운트: {'적절': N, '보완필요': N, '부적절': N}."""

    skipped: int = 0
    """사업장 컨텍스트로 SKIP된 슬롯 수."""

    elapsed_sec: float = 0.0
    generated_at: str = ""


# ─────────────────────────────────────────────
# 1차 baseline: 본문 텍스트에 슬롯 field/required_content 의 키워드가 있는지
# 단순 정규식 매칭 (LLM 미사용). 2단계에서 LLM 추출로 정교화.
# ─────────────────────────────────────────────
def _search_in_text(text: str, slot: EcSlot) -> tuple[bool, str]:
    """
    슬롯 항목이 본문에 등장하는지 + 인접 표현 추출.

    검색 키:
      1. field (예: '사용자 정보', '근로개시일') — 가장 직접적
      2. required_content 의 단어들 — 보조 신호

    반환: (present, extracted)
    """
    text_norm = text.replace(" ", "")
    field_norm = slot.field.replace(" ", "")

    if field_norm in text_norm:
        # field 가 등장 — 그 주변 100자 추출
        idx = text.find(slot.field[0])
        # field 의 첫 글자 위치 찾고 거기서부터 80자
        start = max(0, idx - 10)
        end = min(len(text), idx + 100)
        return True, text[start:end].strip().replace("\n", " ")

    # required_content 의 단어들 부분 매칭 (콤마 분리 단어)
    keywords = [k.strip() for k in slot.required_content.split(",") if k.strip()]
    for kw in keywords:
        kw_norm = kw.replace(" ", "")
        if len(kw_norm) >= 2 and kw_norm in text_norm:
            idx = text.find(kw[0])
            start = max(0, idx - 10)
            end = min(len(text), idx + 100)
            return True, text[start:end].strip().replace("\n", " ")

    return False, ""


def _make_case_id(file_path: Path) -> str:
    """파일명 + 시각 기반 case_id."""
    seed = f"{file_path.name}|{datetime.now().isoformat()}"
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"ec-{h}"


def _reason_for(slot: EcSlot, present: bool, content_ok: bool | None) -> str:
    """사람용 사유 한 줄."""
    if not present:
        return (
            f"본문에서 '{slot.field}' 항목을 찾지 못했습니다. "
            f"{slot.purpose or '필수 기재 항목'}이므로 추가 작성이 필요합니다."
        )
    if content_ok is False:
        return f"'{slot.field}' 항목이 기재되어 있으나 법정 기준에 미달합니다."
    return f"'{slot.field}' 항목이 본문에 기재되어 있습니다."


def review_ec_file(
    file_path: Path | str,
    context: WorkplaceContext | None = None,
) -> EcReport:
    """근로계약서 1건 검토."""
    fp = Path(file_path)
    t0 = time.time()

    # ── 텍스트 추출
    text = parse_to_text(fp)
    if not text or len(text.strip()) < 20:
        return EcReport(
            case_id=_make_case_id(fp),
            source_file=fp.name,
            overall_label="검토불가",
            findings=[],
            summary={},
            elapsed_sec=round(time.time() - t0, 2),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    # ── 카탈로그 + 컨텍스트
    catalog = load_ec_catalog()
    ctx = context or WorkplaceContext()
    business_size = ctx.business_size
    worker_types = ctx.worker_types or ["정규직"]

    findings: list[EcFinding] = []
    skipped = 0
    summary: dict[str, int] = {"적절": 0, "보완필요": 0, "부적절": 0}

    # ── 슬롯별 검토
    for slot in catalog.slots:
        if not slot.applies_to(business_size, worker_types):
            skipped += 1
            continue

        present, extracted = _search_in_text(text, slot)
        # 1차 baseline 은 LLM 미사용이라 content_ok 는 None (LLM 미판단)
        content_ok: bool | None = None
        bucket = classify_ec(
            present=present,
            content_ok=content_ok,
            severity=slot.violation_severity,
        )

        findings.append(
            EcFinding(
                slot_id=slot.slot_id,
                field=slot.field,
                bucket=bucket,
                severity=slot.violation_severity,
                present=present,
                extracted=extracted,
                reason=_reason_for(slot, present, content_ok),
                required_content=slot.required_content,
                purpose=slot.purpose,
                laws=slot.laws,
                topic_meta=slot.topic_meta,
                fix_example=slot.fix_example,
            )
        )
        summary[bucket] = summary.get(bucket, 0) + 1

    elapsed = round(time.time() - t0, 2)

    return EcReport(
        case_id=_make_case_id(fp),
        source_file=fp.name,
        overall_label=overall_label(summary),
        findings=findings,
        summary=summary,
        skipped=skipped,
        elapsed_sec=elapsed,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
