"""도메인별 프롬프트 (기본값).

===============================================================================
원본 대비 주요 변경
===============================================================================
원본
- `data/prompts/*.md, *.txt, ec_prompts.json` 파일에 저장.
- 관리자 UI 편집.

v2
- 코드에 기본값 (default), 오버라이드는 PG `cgr_admin.prompt` 테이블.
- integrations 중 유일하게 도메인 하위 폴더 허용 (규칙 §2.3).
- 각 도메인 폴더의 파일들이 default 문자열 상수 export.
- 관리자 편집은 `services/admin/prompts.py` 에서 처리 (PG upsert).
- 서비스 코드는 `resolve_prompt("wr_extractor")` 로 조회
  → DB 조회 → 없으면 default 반환.
"""
from __future__ import annotations

from .resolver import resolve_prompt

__all__ = ["resolve_prompt"]
