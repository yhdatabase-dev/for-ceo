"""EC 원샷 검토 서비스 — 원본 `cgr/ec/run.py:review_ec_file` 이관.

===============================================================================
원본 이관
===============================================================================
원본
- 파일 → 텍스트 파싱 (parse_to_text)
- EC 카탈로그 로드 (load_ec_catalog · YAML/SQL)
- WorkplaceContext (business_size + worker_types) 로 슬롯 필터
- 각 슬롯: 본문 키워드 매칭 (`_search_in_text`) — LLM 미사용 baseline
- classify_ec (3-Bucket) + overall_label (종합)
- EcReport 반환

변경점
- `cgr.ec.catalog.load_ec_catalog` → `EcCatalogRepo(db).load()` (PG)
- `cgr.parsers.dispatcher.parse_to_text` → `app.integrations.parsers.parse_document`
- `EcReport` → `EcReviewOut` (프론트 계약)
- `EcSlot.applies_to(bs, wt)` → `slot_applies_to(applicability, bs, wt)` (VO 는 dict 라 함수화)
- `_search_in_text`, `_reason_for`, `_make_case_id` 원본 그대로 이관
- `_search_in_text` 는 v1 baseline — LLM 미사용, 후속 청크에서 LLM 로 교체 가능
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from app.core.exceptions import CgrError, ParseError
from app.core.logging import get_logger
from app.integrations.parsers.dispatcher import parse_document
from app.repositories.ec.catalog_repo import EcCatalogRepo
from app.schemas.ec.responses import EcFindingOut, EcReviewOut
from app.schemas.ec.values import EcSlotVO
from app.schemas.shared import WorkplaceContextIn
from app.services.ec.verdict import classify_ec, overall_label, slot_applies_to

log = get_logger(__name__)


def _make_case_id(file_path: Path) -> str:
    """파일명 + 시각 기반 case_id (원본 그대로)."""
    seed = f"{file_path.name}|{datetime.now().isoformat()}"
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"ec-{h}"


def _search_in_text(text: str, slot: EcSlotVO) -> tuple[bool, str]:
    """슬롯 항목이 본문에 등장하는지 + 인접 표현 추출 (원본 로직 그대로).

    1) slot.field (예: '사용자 정보', '근로개시일') 매칭
    2) required_content 의 콤마 분리 단어 매칭
    """
    text_norm = text.replace(" ", "")
    field_norm = slot.field.replace(" ", "")

    if field_norm in text_norm:
        idx = text.find(slot.field[0])
        start = max(0, idx - 10)
        end = min(len(text), idx + 100)
        return True, text[start:end].strip().replace("\n", " ")

    keywords = [
        k.strip() for k in (slot.required_content or "").split(",") if k.strip()
    ]
    for kw in keywords:
        kw_norm = kw.replace(" ", "")
        if len(kw_norm) >= 2 and kw_norm in text_norm:
            idx = text.find(kw[0])
            start = max(0, idx - 10)
            end = min(len(text), idx + 100)
            return True, text[start:end].strip().replace("\n", " ")

    return False, ""


def _reason_for(
    slot: EcSlotVO, present: bool, content_ok: bool | None
) -> str:
    """사람용 사유 한 줄 (원본 그대로)."""
    if not present:
        return (
            f"본문에서 '{slot.field}' 항목을 찾지 못했습니다. "
            f"{slot.purpose or '필수 기재 항목'}이므로 추가 작성이 필요합니다."
        )
    if content_ok is False:
        return f"'{slot.field}' 항목이 기재되어 있으나 법정 기준에 미달합니다."
    return f"'{slot.field}' 항목이 본문에 기재되어 있습니다."


class ReviewService:
    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db
        self.catalog_repo = EcCatalogRepo(db)

    def review_file(
        self,
        file_path: Path,
        *,
        context: WorkplaceContextIn | None = None,
    ) -> EcReviewOut:
        """근로계약서 1건 검토 (baseline · LLM 미사용)."""
        t0 = time.time()

        # 1) 파싱
        try:
            text = parse_document(file_path)
        except ParseError:
            raise
        except Exception as e:  # noqa: BLE001
            raise CgrError(
                f"EC 파일 파싱 실패: {type(e).__name__}: {e}",
                meta={"path": str(file_path)},
            ) from e

        if not text or len(text.strip()) < 20:
            return EcReviewOut(
                case_id=_make_case_id(file_path),
                filename=file_path.name,
                overall_label="검토불가",
                summary={},
                n_findings=0,
                skipped=0,
                elapsed_sec=round(time.time() - t0, 2),
                findings=[],
            )

        # 2) 카탈로그
        catalog = self.catalog_repo.load()
        ctx = context or WorkplaceContextIn()
        business_size = ctx.business_size
        worker_types = ctx.worker_types or ["정규직"]

        # 3) 슬롯 필터 + 판정
        findings: list[EcFindingOut] = []
        skipped = 0
        summary: dict[str, int] = {"적절": 0, "보완필요": 0, "부적절": 0}

        for slot in catalog.slots:
            if not slot_applies_to(slot.applicability, business_size, worker_types):
                skipped += 1
                continue

            present, extracted = _search_in_text(text, slot)
            content_ok: bool | None = None  # baseline — LLM 미사용
            bucket = classify_ec(
                present=present,
                content_ok=content_ok,
                severity=slot.violation_severity,
            )
            findings.append(
                EcFindingOut(
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
        return EcReviewOut(
            case_id=_make_case_id(file_path),
            filename=file_path.name,
            overall_label=overall_label(summary),
            summary=summary,
            n_findings=len(findings),
            skipped=skipped,
            elapsed_sec=elapsed,
            findings=findings,
        )
