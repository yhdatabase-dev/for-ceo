# Frontend — 사용자 화면

Next.js 14 App Router · TypeScript · CSS Modules · Pretendard.

검토 대상 3 문서: **취업규칙 · 근로계약서 · 임금명세서**.

## 빠른 시작

```bash
npm install
npm run dev    # http://localhost:18091/cgr (포트 CGR_FRONTEND_PORT)
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

화면 주소는 모두 `/cgr` 아래(basePath, `next.config.mjs`). 화면 경로는 `src/lib/routes.ts` 한 곳에서 정의.

```
src/
├── app/                                 # 화면·라우팅 (App Router)
│   ├── layout.tsx
│   ├── page.tsx                         # /cgr — 문서 선택 + 업로드
│   ├── ec/                              # 근로계약서
│   │   ├── page.tsx                     #   /cgr/ec — 업로드
│   │   └── [caseUid]/
│   │       ├── loading/                 #   진행률 화면
│   │       ├── contract/                #   2. 계약서 내용 확인 (구조화 표 편집)
│   │       ├── review/                  #   3. 검토결과
│   │       └── preview/                 #   4. 개선안 미리보기 (표준 계약서)
│   ├── wr/                              # 취업규칙
│   │   ├── page.tsx                     #   /cgr/wr — 업로드
│   │   └── [caseUid]/
│   │       ├── loading/                 #   진행률 화면
│   │       ├── text/                    #   추출 텍스트 확인
│   │       ├── review/                  #   검토결과
│   │       ├── findings/[findingId]/    #   검토결과 상세
│   │       └── comparison/              #   신구대조표
│   ├── history/                         # /cgr/history — 검토 이력
│   └── api/cgr/[...path]/route.ts       # BFF — X-API-Key 주입
│
├── features/                            # 업무 기능 (백엔드 도메인과 같은 이름)
│   ├── ec/                              # api.ts · store.ts · components/ · reviewShared.ts
│   ├── wr/                              # api.ts · store.ts · mappers.ts · components/(detail·print)
│   ├── history/                         # store.ts — 검토 건 보관(브라우저 저장소)·이력 목록
│   └── topics/                          # api.ts — 노무 주제 해설
│
├── components/                          # 공통 UI
│   ├── home/                            # HomeScreen(업로드) · DocTypePicker · FileDropzone · WorkplaceForm 등
│   ├── layout/                          # SiteHeader
│   ├── review/                          # LoadingScreen · ChatPanel · mobile/ (근로계약서·취업규칙 공용)
│   └── ui/                              # Button · Card · Icon · RiskBadge 등
│
├── lib/                                 # 기술 유틸 — api/client.ts · api/types.ts · routes.ts · basePath.ts
├── data/ · hooks/ · styles/ · types/
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
| `features/ec/api.ts` | `/api/cgr/ec/*` (extractions·structures·classifications·analyses·field-validations·drafts·documents·chat-messages) |
| `features/wr/api.ts` | `/api/cgr/wr/*` (reviews·revisions·revision-documents·comparison-documents·review-summaries·classifications) |
| `features/topics/api.ts` | `/api/cgr/topics/sections` (lazy fetch + 모듈 캐시) |

## 새 화면 추가

1. `src/app/<도메인>/[caseUid]/<화면>/page.tsx` + `page.module.css`
2. `src/lib/routes.ts` 에 경로 추가
3. 단계 상태가 필요하면 `features/<도메인>/store.ts` 에 phase 추가, `components/review/LoadingScreen.tsx` 라우팅 분기 추가
4. API 호출은 `features/<도메인>/api.ts`

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
