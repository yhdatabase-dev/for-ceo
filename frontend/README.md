# Frontend — 사용자 화면

Next.js 14 App Router · TypeScript · CSS Modules · Pretendard.

검토 대상 3 문서: **취업규칙 · 근로계약서 · 임금명세서**.

## 빠른 시작

```bash
npm install
npm run dev    # http://localhost:18091 (CGR_FRONTEND_PORT)
```

## 환경 변수 (저장소 루트 `.env` — 백엔드와 같은 파일, 설명은 `.env.example`)

| 변수 | 기본 | 설명 |
|---|---|---|
| `CGR_API_BASE` | `http://localhost:18081` | 백엔드 FastAPI 주소 (서버측 fetch, 브라우저 비노출) |
| `CGR_API_KEY` | — | server-only. BFF 가 X-API-Key 헤더에 주입. 클라이언트 노출 X |
| `CGR_FRONTEND_PORT` | `18091` | 로컬 dev 서버 포트 |
| `NEXT_PUBLIC_BASE_PATH` | — | 하위 경로 배포 접두어 (예: `/cgr`) |

> 클라이언트에 API 키 노출 없도록 — BFF (`src/app/api/cgr/[...path]/route.ts`) 가 서버측 주입.

## 디렉토리 구조

```
src/
├── app/                            # Next.js App Router
│   ├── layout.tsx                  # 루트 — Pretendard preload
│   ├── page.tsx                    # 홈 — 문서 선택·업로드·사업장 정보
│   ├── review/[id]/
│   │   ├── loading/                # 진행률 화면 (단계 카드)
│   │   ├── ec/                     # 근로계약서
│   │   │   ├── page.tsx            #   Step3 결과 (게이지·캐러셀·SuggestBlock·챗봇)
│   │   │   ├── review/page.tsx     #   Step2 구조화 표 편집
│   │   │   └── contract/page.tsx   #   Step4 표준 계약서
│   │   ├── ws/                     # 임금명세서 (베타)
│   │   │   ├── page.tsx            #   결과 (EC 동일 디자인)
│   │   │   └── contract/page.tsx   #   표준 임금명세서
│   │   └── findings/[findingId]/   # 취업규칙 상세
│   └── api/cgr/[...path]/route.ts  # BFF — X-API-Key 주입
│
├── components/
│   ├── home/                       # DocTypePicker · FileDropzone · WorkplaceForm · Hero
│   ├── layout/                     # SiteHeader
│   ├── review/                     # FindingCarousel · VerdictCard · LoadingScreen 등
│   │   └── detail/                 #   상세 4탭
│   └── ui/                         # Button · Card · Icon · RiskBadge · LawHover 등
│
├── lib/
│   ├── api/
│   │   ├── client.ts               # fetch wrapper
│   │   ├── ec.ts · ws.ts · review.ts · topics.ts
│   │   ├── mappers.ts              # 백엔드 → 프론트 타입 변환
│   │   └── types.ts
│   ├── reviewStore.ts              # 메모리 + sessionStorage (EC·WS·WR 워크플로 상태)
│   └── markdownBold.tsx
│
├── data/
│   └── lawExcerpts.ts              # 법령·주제 발췌 (코퍼스는 백엔드 lazy fetch)
│
├── styles/
│   ├── globals.css                 # civic 디자인 토큰
│   └── tokens.ts                   # TypeScript 토큰
│
└── types/
    └── review.ts                   # WorkplaceContext · Finding · DocumentType
```

## 디자인 시스템

`src/styles/globals.css` — civic 팔레트 + Pretendard.

### 색
| 토큰 | 값 |
|---|---|
| `--color-brand` | `#0B3D91` 네이비 |
| `--color-brand-soft` | `#E5ECF8` |
| `--color-bg` | `#F5F7FA` |
| `--color-surface` | `#FFFFFF` |

### 위험도 (5단계)
| key | 색 | 용도 |
|---|---|---|
| missing | `#dc2626` red | 미기재·부적절 |
| violation | `#ea580c` orange | 위반 |
| warn | `#facc15` yellow | 보완필요 |
| ambiguous | `#a855f7` purple | 모호 |
| ok | `#22c55e` green | 적절 |

### 라운드·그림자
| 토큰 | 값 |
|---|---|
| `--r-md` / `--r-lg` / `--r-pill` | 10px / 14px / 999px |
| `--shadow-sm` / `--shadow-md` | hover 시 강조 |

## BFF 패턴

브라우저는 `/api/cgr/*` 만 호출. `src/app/api/cgr/[...path]/route.ts`:
1. 서버측에서 `X-API-Key` 헤더 주입 (`CGR_API_KEY` env)
2. `CGR_API_BASE` 로 forward
3. 응답·헤더 그대로 반환

→ 브라우저 코드에 API 키 노출 X.

## API 클라이언트

| 클라이언트 | 백엔드 |
|---|---|
| `lib/api/ec.ts` | `/api/v1/ec/*` (extract·structure·analyze·chat·generate) |
| `lib/api/ws.ts` | `/api/v1/ws/*` (extract·analyze·inspect·generate·catalog) |
| `lib/api/review.ts` | `/api/v1/review` (취업규칙) |
| `lib/api/topics.ts` | `/api/v1/topics/corpus` (lazy fetch + 모듈 캐시) |

## 새 페이지·문서 추가

1. `src/app/review/[id]/<doc>/page.tsx` + `page.module.css`
2. `reviewStore` 에 워크플로 phase 타입 추가 (예: `WsWorkflow`)
3. `components/review/LoadingScreen.tsx` 라우팅 분기 추가
4. `lib/api/<doc>.ts` 클라이언트 함수

## 스크립트

```bash
npm run dev          # 개발 서버
npm run build        # 프로덕션 빌드
npm run start        # 빌드 결과 서빙
npm run lint
npm run type-check   # tsc --noEmit
```

## 알려진 이슈·노트

- Windows + 한국어 경로: 별도 처리 없이 동작
- `.next/` 캐시 손상 시 `rm -rf .next && npm run dev`
- Pretendard CDN 차단 시 시스템 폰트로 자동 폴백
