"""guide 도메인 공개 인터페이스.

원본
- `cgr/api/routes/guide.py` 라우터에 로직이 인라인.

v2
- 조회 로직은 GuideService (repository 얇게 감쌈).
- 챗봇 로직은 GuideChatService (RAG 컨텍스트 조립 + LLM 호출).
"""
from __future__ import annotations

from .chat_service import GuideChatService
from .guide_service import GuideService

__all__ = ["GuideService", "GuideChatService"]
