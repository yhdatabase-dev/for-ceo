"""guide 조회 서비스 — 리포지토리 얇게 감쌈.

라우터가 DB 커넥션을 직접 만지지 않게 하는 목적.
비즈니스 로직이 거의 없어 리포지토리 pass-through 이지만,
- 앞으로 "excluded_from_service 강제"·"권한별 필터링" 등이 추가될 여지 확보.
"""
from __future__ import annotations

import psycopg

from app.repositories.guide import GuideRepo
from app.schemas.guide.responses import (
    FormListOut,
    FormOut,
    GlossaryListOut,
    GuideItemListOut,
    GuideItemOut,
    GuideOverviewOut,
    ObligationTimelineListOut,
    SizeThresholdDutyListOut,
)


class GuideService:
    def __init__(self, db: psycopg.Connection) -> None:
        self.repo = GuideRepo(db)

    # ── 가이드 항목 ────────────────────────────
    def list_guide_items(
        self, *, audience: str | None = None, category: str | None = None
    ) -> GuideItemListOut:
        items = self.repo.list_guide_items(audience=audience, category=category)
        return GuideItemListOut(items=items)

    def get_guide_item(self, code: str) -> GuideItemOut | None:
        return self.repo.get_guide_item(code)

    # ── 용어 사전 ─────────────────────────────
    def list_glossary(self) -> GlossaryListOut:
        return GlossaryListOut(items=self.repo.list_glossary())

    # ── 규모별 의무 ───────────────────────────
    def list_size_threshold_duties(self, min_size: str) -> SizeThresholdDutyListOut:
        """원본 `/guide/by-size/{min_size}` — Python 필터로 rank 비교."""
        all_ = self.repo.list_size_threshold_duties()
        target = _size_rank(min_size)
        # Pydantic DTO 필드 접근 → 그대로 attribute 접근 OK
        selected = [d for d in all_ if _size_rank(d.min_size) <= target]
        return SizeThresholdDutyListOut(size=min_size, rank=target, duties=selected)

    # ── 타임라인 ──────────────────────────────
    def list_timeline(self) -> ObligationTimelineListOut:
        return ObligationTimelineListOut(items=self.repo.list_timeline())

    def list_by_stage(self, stage: str) -> ObligationTimelineListOut:
        return ObligationTimelineListOut(items=self.repo.list_by_stage(stage))

    # ── 서식 ──────────────────────────────────
    def list_forms(
        self, *, category: str | None = None, audience: str | None = None
    ) -> FormListOut:
        return FormListOut(items=self.repo.list_forms(category=category, audience=audience))

    def get_form(self, code: str) -> FormOut | None:
        row = self.repo.get_form_row(code)   # dict 반환 (예외적)
        if not row:
            return None
        return FormOut(
            code=row["code"],
            form_name=row["form_name"],
            has_local=bool(row.get("local_filename")),
            download_url=row.get("download_url"),
        )

    # ── 임금 계산식·기관·기타 ─────────────────
    def list_wage_calc(self, *, violation_code: str | None = None) -> list[dict]:
        return self.repo.list_wage_calc(violation_code=violation_code)

    def list_orgs(self) -> list[dict]:
        return self.repo.list_orgs()

    def list_audit_guide(self) -> dict[str, list[dict]]:
        return self.repo.list_audit_guide()

    def list_required_docs(self) -> list[dict]:
        return self.repo.list_required_docs()

    def list_lifecycle(self) -> list[dict]:
        return self.repo.list_lifecycle()

    def list_recruit(self) -> list[dict]:
        return self.repo.list_recruit()

    # ── 오버뷰 ────────────────────────────────
    def overview(self) -> GuideOverviewOut:
        return self.repo.overview()


# ─── 순수 함수: 사업장 규모 랭크 ───────────────────
def _size_rank(size_str: str) -> int:
    """'5', '5인', '5인 이상', '30인 미만' 등 → 정수 랭크.

    원본 `cgr/api/routes/guide.py:_size_rank` 이관.
    """
    if not size_str:
        return 0
    s = size_str.strip()
    digits = "".join(c for c in s if c.isdigit())
    return int(digits) if digits else 0
