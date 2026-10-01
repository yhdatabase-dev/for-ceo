"""review(WR) 도메인 리포지토리 — 원본 Excel 마스터 DB 는 v2 에서 PG check_item 으로 이관."""
from __future__ import annotations

from .catalog_repo import WrCatalogRepo

__all__ = ["WrCatalogRepo"]
