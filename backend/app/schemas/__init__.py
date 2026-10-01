"""schemas — DTO(외부 계약) · VO(내부 값 객체) 정의.

Rule (docs/리팩토리 구조.md):
- 1개 라우터에서만 쓰는 스키마 → 그 라우터 파일 안에 정의
- 2개 이상 라우터가 공유 → 이 패키지의 도메인 파일에 정의
- 라우터 로컬 스키마가 나중에 공유 필요해지면 → 이 패키지로 이동

도메인
- common     : 페이지네이션·에러 응답 (업무 개념 없음)
- review/    : 취업규칙 (WR) DTO/VO
- ec/        : 근로계약서 (EC) DTO/VO
- guide/     : 가이드 DTO/VO
- shared/    : 2개 이상 도메인이 함께 쓰는 업무 객체

각 도메인 폴더:
- requests.py   : 외부 → 서버 요청 DTO (프론트 계약)
- responses.py  : 서버 → 외부 응답 DTO (프론트 계약)
- values.py     : 내부 파이프라인 VO (자유롭게 리팩)
"""
from __future__ import annotations

from .common import ErrorResponse, HealthResponse

__all__ = ["ErrorResponse", "HealthResponse"]
