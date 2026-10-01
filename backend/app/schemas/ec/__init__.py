"""ec 도메인 스키마."""
from __future__ import annotations

from .requests import (
    AnalyzeIn,
    ChatIn,
    ChatHistoryTurn,
    ClassifyIn,
    GenerateDocxIn,
    GenerateIn,
    StructureIn,
    ValidateFieldIn,
)
from .responses import (
    AnalyzeOut,
    ChatOut,
    ClassifyOut,
    EcFindingOut,
    EcReviewOut,
    ExtractOut,
    GenerateOut,
    StructureOut,
    ValidateFieldOut,
)

__all__ = [
    # requests
    "AnalyzeIn", "ChatIn", "ChatHistoryTurn", "ClassifyIn",
    "GenerateDocxIn", "GenerateIn", "StructureIn", "ValidateFieldIn",
    # responses
    "AnalyzeOut", "ChatOut", "ClassifyOut", "EcFindingOut", "EcReviewOut",
    "ExtractOut", "GenerateOut", "StructureOut", "ValidateFieldOut",
]
