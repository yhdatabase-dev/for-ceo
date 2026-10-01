"""repositories — DB 접근 유일 계층 (DAO).

Rule (docs/리팩토리 구조.md)
- 넣는 것: SQL·ORM 질의, 결과를 Pydantic 객체로 변환
- 넣지 않는 것: 업무 판정, 외부 API 호출, HTTP 관심사
- 반환 금지: dict / SQLAlchemy Row / ORM Entity
- 반환은 반드시 Pydantic VO (schemas/*/values.py)
"""
