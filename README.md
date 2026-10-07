# 영세사업장 자율점검 서비스

노동법 자율점검 AI — **취업규칙 · 근로계약서 · 임금명세서 · 노무제공자 계약서** 4 문서 + 가이드 챗봇 + 통상임금/퇴직금 계산기.

> 사장님이 문서를 올리면 누락·위반·보완사항을 분석하고, 시정 권고와 표준 양식을 제공.

## 셋업

### 1) 환경변수 (최초 1회)

```bash
cp .env.example .env
# .env 를 열어 DB 접속 정보·CGR_API_KEY 를 채운다 (백엔드·프론트가 같은 파일을 쓴다)
```

`OPENAI_API_KEY` 가 비어 있으면 내장 가짜 LLM 으로 동작한다(로컬·테스트는 실호출 없음).

### 2) Python 의존성

```bash
cd backend
pip install -r requirements.txt
```

### 3) 프론트 의존성

```bash
cd frontend
npm install
```

### 4) 마스터 DB 시드 (최초 1회 또는 데이터 변경 시)

```bash
cd backend && python scripts/seed_master_db.py --drop-first
```

> `master.db` 파일은 repo 에 포함돼 있어 일반적으로 재시드 불요. 다만 시드 입력 (`data/영세사업주를 위한 꿀팁.xlsx`, `data/slots/atomic_slots_*.yaml`, `data/topic_corpus.json` 등) 을 변경했다면 위 명령으로 재시드.

## 실행

2개 서버 — 각자 다른 터미널에서 (포트는 .env 의 CGR_BACKEND_PORT · CGR_FRONTEND_PORT):

```bash
cd backend  && python launch_api.py     # FastAPI 백엔드 — http://127.0.0.1:18081
cd frontend && npm run dev              # Next.js 사용자 — http://localhost:18091
```

상세 트러블슈팅 — [`docs/06_개발_가이드.md`](docs/06_개발_가이드.md)

## 폴더 구조

```
backend/                  # Python (FastAPI + Streamlit 관리자)
  ├── cgr/                # 핵심 패키지 (ec/ws/wr/sc 도메인 + 가이드 + 룰엔진)
  ├── data/               # SQLite (master.db) + 시드 입력 + 폼 파일 + 캐시
  │   ├── slots/          # 슬롯 카탈로그 YAML (EC 35 + WR 115 + WS 11 + SC 16)
  │   ├── forms/          # 표준 양식 hwp/pdf (사용자 직접 다운로드용)
  │   ├── prompts/        # LLM 프롬프트 JSON
  │   └── 영세사업주를 위한 꿀팁.xlsx  # 가이드 DB 시드 입력
  ├── scripts/            # 시드 스크립트 (seed_master_db.py 가 메인)
frontend/                 # Next.js 14 — 사용자 화면 (Pretendard · civic 디자인)
  ├── src/app/            # 페이지 (홈 · 검토 · 가이드 · 이력)
  ├── src/components/     # 공용 컴포넌트 (FindingCard · ChatPanel 등)
  └── src/lib/            # API 클라이언트 + reviewStore (sessionStorage 기반)
docs/                     # 시스템 문서
```

## 핵심 문서

| 문서 | 내용 |
|---|---|
| [`docs/00_INDEX.md`](docs/00_INDEX.md) | 전체 인덱스 |
| [`docs/01_시스템_개요.md`](docs/01_시스템_개요.md) | 서비스 전체상·아키텍처 |
| [`docs/02_데이터_파이프라인.md`](docs/02_데이터_파이프라인.md) | 입력→처리→출력 흐름 |
| [`docs/04_자료사전.md`](docs/04_자료사전.md) | SQLite 38 테이블 + 4 뷰 명세 |
| [`docs/05_모듈_가이드.md`](docs/05_모듈_가이드.md) | `cgr.*` 패키지 책임 분리 |
| [`docs/06_개발_가이드.md`](docs/06_개발_가이드.md) | 실행·재시드·트러블슈팅 |

## 주요 기능

- **검토** — EC(근로계약서) · WS(임금명세서) · WR(취업규칙) · SC(노무제공자 계약서)
- **가이드 챗봇** — 가이드 DB(의무·용어·기관·서류·라이프사이클) 컨텍스트 + LLM
- **계산기** — 통상임금(임금 항목별 입력 + 자동 산입 토글) + 퇴직금 + 출산·육아 급여
- **표준 양식 다운로드** — 31건 카탈로그, 우리 서버에 보관된 양식은 직접 다운로드, 그 외는 정부 사이트로 redirect
- **노무 가이드 자료실** — 시기·규모별 의무, 용어 사전, 기관, 비치 서류

## 핵심 기술

- **Frontend**: Next.js 14 · React 18 · TypeScript · Pretendard Variable · civic 디자인 토큰
- **Backend**: FastAPI · Pydantic · SQLite (vector(1024)) · OpenAI (gpt-5.4-mini)
- **Admin**: Streamlit (관리자 대시보드 + 슬롯 편집 + 프롬프트 편집)
- **결정성**: temperature=0 + LLM 캐시 (SHA-256 키) + ruleset_version 스탬핑

## 보안·자율점검 원칙

- **PII 마스킹**: LLM 호출 전 성명·사번·주민번호·전화·이메일·사업자번호 등 자동 마스킹
- **분쟁 데이터 시드 제외**: 진정서·구제신청서 등 분쟁 양식은 시드 단계에서 완전 제외
- **공인노무사 안내**: 회색지대·LLM 일반지식 답변에만 공인노무사 상담 권유

## 라이선스

내부 사용. 외부 배포 시 별도 협의 필요.
