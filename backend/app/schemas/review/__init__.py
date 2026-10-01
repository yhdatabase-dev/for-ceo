"""review 도메인 스키마 — 취업규칙 (WR) 5-Bucket 판정."""
from __future__ import annotations

from .requests import (
    ComparisonDocxIn,
    CorrectionIn,
    GenerateDocxIn,
    GenerateIn,
    WrClassifyIn,
)
from .responses import (
    ArticleResultOut,
    FindingOut,
    GenerateOut,
    ReviewFullOut,
    ReviewSummaryOut,
    WrClassifyOut,
)

__all__ = [
    "CorrectionIn",
    "GenerateIn",
    "GenerateDocxIn",
    "ComparisonDocxIn",
    "WrClassifyIn",
    "FindingOut",
    "ArticleResultOut",
    "ReviewSummaryOut",
    "ReviewFullOut",
    "GenerateOut",
    "WrClassifyOut",
]
