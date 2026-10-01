"""services — 업무 로직 계층.

Rule (docs/리팩토리 구조.md)
- 넣는 것: 판정·계산·흐름 제어, repository 조합, integrations 호출
- 넣지 않는 것: SQL, HTTP 상태코드, Request/Response 객체
- 다른 도메인의 services 를 import 하지 않는다 (도메인 격리)
- 각 도메인 폴더의 __init__.py 가 공개 인터페이스. 밖에서는 이것만 import.
"""
