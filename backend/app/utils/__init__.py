"""utils — 순수 함수. DB·설정·네트워크 의존 없음.

Rule (docs/리팩토리 구조.md)
- 입력만 받아 결과를 낸다. DB·설정·네트워크 의존이 전혀 없다.
- core·services·repositories 를 import 하면 테스트 실패 처리.
- 의존이 생기면 core 또는 integrations 로 옮긴다.
"""
