"""for-ceo.v2 백엔드 애플리케이션 루트 패키지.

레이어 규칙 (docs/리팩토리 구조.md):
    api → services → repositories → models
                  ↘                ↗
                    integrations
                    core (앱 전역)
                    utils (순수 함수)

- api: HTTP 진입점. 요청 검증 · 서비스 호출 · 응답 변환만.
- services: 업무 로직. repositories 조합 + integrations 호출.
- repositories: DB 접근. SQL/ORM 은 여기에서만.
- models: SQLAlchemy Entity. repositories 내부에서만 사용.
- integrations: 외부 시스템 어댑터 (LLM, 파서 등).
- core: 앱 부팅 시 한 번만 설치되는 것 (config, database, logging).
- utils: DB·설정·네트워크 의존 없는 순수 함수.
"""
