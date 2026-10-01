"""shared 리포지토리 — 2개 이상 도메인 공용."""
from __future__ import annotations

from .audit_repo import AuditRepo
from .history_repo import HistoryRepo
from .log_repo import AccessLogRepo, InteractionLogRepo, UploadRepo, VisitRepo
from .admin_repo import PromptRepo, SettingRepo

__all__ = [
    "AuditRepo",
    "HistoryRepo",
    "VisitRepo",
    "UploadRepo",
    "InteractionLogRepo",
    "AccessLogRepo",
    "PromptRepo",
    "SettingRepo",
]
