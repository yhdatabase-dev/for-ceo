/**
 * << 개정이력(Modification Information) >>
 * 수정일          수정자      수정 내용
 * ----------      ------      ---------------------------
 * 2026.05.28      kimzion77   최초 생성
 * 2026.10.01      이시영      버전 정렬 (Python 3.14.7·Node 24.21.0·Next 16.3.5)
 * 2026.10.07      이시영      화면 경로 /cgr·features 구조 이동, sync API 삭제, 업로드 원본 미저장
 * 2026.10.07      이시영      챗봇 기능 삭제
 * 2026.10.07      이시영      검토번호 서버 발급, 변경 사유 주석 추가
 *
 * Author: kimzion77
 * Since: 2026.05.28
 */
'use client';

// 프로그램명세서 LC-003-01 검토결과: 화면 URL /cgr/ec/[caseUid]/review (기존: /review/[id]/ec)

import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  use,
} from 'react';
import { createPortal } from 'react-dom';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

import { postEcGenerate } from '@/features/ec/api';
import { ApiCallError } from '@/lib/api/client';
import type {
  EcAnalysisItem,
  EcAnalysisResult,
  EcStructuredData,
} from '@/lib/api/types';
import SiteHeader from '@/components/layout/SiteHeader';
import MobileReviewApp, {
  useIsMobileViewport,
  type MobileFinding,
} from '@/components/review/mobile/MobileReviewApp';
import { lookupLawExcerpt, type LawExcerpt } from '@/data/lawExcerpts';
import { filterApplicableGroups } from '@/features/ec/workerTypeRequirements';
import { getCase, setCaseError } from '@/features/history/store';
import { updateEc } from '@/features/ec/store';
import { useTopicCorpus } from '@/features/topics/api';

import styles from './page.module.css';
import {
  APPROPRIATENESS_ORDER,
  buildMarkerHits,
  extractCandidateTokens,
  findingLabel,
  firstLaw,
  isLawDb,
  isLawName,
  lawArticleUrl,
  lookupForLawName,
  normalizeArticleLabel,
  parseMetaTags,
  shortNoteForFinding,
  statusForItem,
  toneOf,
} from '@/features/ec/reviewShared';
import type {
  ItemStatus,
  BoardGroupItem,
  BoardGroup,
  RequirementBoard,
  RequirementStats,
  VerdictBlockProps,
  ContractMarker,
  ContractPage,
  MarkerHit,
  MetaTag,
  MetaTagInfo,
} from '@/features/ec/reviewShared';
import { routes } from '@/lib/routes';

/**
 * Step3 — 33매핑 분석 결과 페이지 (B안).
 *
 * 좌·우 2분할 (1fr : 1.1fr).
 * 좌: 업로드 문서 패널 — 헤더 / 컴팩트 요약 / 본문 페이지 / 도트 페이지네이션
 * 우: 메타 + 종합 판정 카드(게이지) + 항목별 상세 스와이프 캐러셀
 */

const VERDICT_STYLES: Record<string, { card: string; text: string }> = {
  위험: { card: styles.verdictBad, text: styles.verdictTextBad },
  보완필요: { card: styles.verdictMid, text: styles.verdictTextMid },
  적정: { card: styles.verdictOk, text: styles.verdictTextOk },
};

export default function EcResultPage(props: { params: Promise<{ caseUid: string }> }) {
  const params = use(props.params);
  const router = useRouter();
  const caseId = params.caseUid;

  // ─── HOOK ORDER — 모든 훅은 조기 return 보다 위에서 호출 ───
  // React 규칙: 매 렌더 같은 순서·같은 개수의 훅을 호출해야 함.
  // mount 가드/notFound 분기는 훅이 모두 실행된 뒤에 둔다.

  const [entry, setEntry] = useState<ReturnType<typeof getCase>>(null);
  const [mounted, setMounted] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  /** "제안 모두 반영" 결과 안내 메시지 (잠깐 표시). */
  const [bulkMsg, setBulkMsg] = useState<string | null>(null);
  const bulkTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** 좌(요약 칩·본문 마크) ↔ 우(상세 카드) 동기화용 focus 인덱스 (0-based, sortedResults 기준). */
  const [focusedIndex, setFocusedIndex] = useState(0);
  // 핸들러는 안정적 identity 로 — 안 그러면 자식 effect 가 매 렌더 재실행돼
  // scrollIntoView 가 반복 호출되며 화면이 떨린다(버벅임).
  const handleFocus = useCallback((i: number) => {
    setFocusedIndex(i);
  }, []);
  /** 보기 모드 — 'split'(나란히: 좌 계약서+우 상세) / 'wide'(검토 보기: 전체폭+거터). */
  const [reviewMode, setReviewMode] = useState<'split' | 'wide'>('split');
  // 노무사회 주제 코퍼스 lazy fetch — 호버 chip 의 본문 발췌용.
  // 페이지 mount 즉시 백엔드 1회 호출. 적재 완료 시 자동 re-render.
  useTopicCorpus();

  useEffect(() => {
    setMounted(true);
    setEntry(getCase(caseId));
  }, [caseId]);

  const analysis: EcAnalysisResult | null =
    entry?.ec?.analysisResult ?? null;

  // 파생 값들은 훅이 끝난 뒤 계산 — 단, requirementBoard 는 useMemo 라 훅이라 위에서.
  const businessSize = entry?.ec?.businessSize ?? '';
  const workerTypes = entry?.ec?.workerTypes ?? [];

  const sortedResults = useMemo(() => {
    if (!analysis) return [];
    return [...analysis.results].sort((a, b) => {
      const aOrder = APPROPRIATENESS_ORDER[a.적절성] ?? 9;
      const bOrder = APPROPRIATENESS_ORDER[b.적절성] ?? 9;
      return aOrder - bOrder;
    });
  }, [analysis]);

  const requirementBoard = useMemo(
    () => buildRequirementBoard(businessSize, workerTypes, sortedResults),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [businessSize, workerTypes.join(','), sortedResults],
  );

  // 위반·보완만 단일 목록으로 — 칩·본문 마크·우측 카드가 모두 이 목록을 공유해
  // 번호·내용이 100% 일치한다. (적절 항목은 통계에만 노출, 본문/카드엔 미표시)
  const violations = useMemo(
    () => sortedResults.filter((r) => r.적절성 !== '적절'),
    [sortedResults],
  );

  // 검토 결과 문서 패널은 원본 이미지 + 추출 텍스트만 — 표준 양식(폼) 뷰는
  // 사용자 요청으로 제거함(결과 화면에선 원본과 비교가 핵심). 표준 양식은
  // 'ec/contract'(표준 계약서 만들기) 화면에서만 보여준다.

  // ─── 모바일 검토앱 (≤720px) — 공용 MobileReviewApp 으로 분기 ───
  const isMobile = useIsMobileViewport();
  const mobileFindings = useMemo<MobileFinding[]>(
    () =>
      violations.map((r) => ({
        key: r.항목,
        tone: r.적절성 === '부적절' ? ('bad' as const) : ('warn' as const),
        name: r.항목,
        reason: `${(r.발견내용 || '').trim().slice(0, 38) || '미기재'} · ${r.적절성}`,
        why: (r.판단이유 || '').replace(/<meta[^>]*\/>/g, '').trim(),
        law: r.법적근거 || undefined,
        pen: undefined,
        now: r.발견내용 || '(기재 없음)',
        fix: r.개선권고 || '',
      })),
    [violations],
  );
  const ecOverrides = entry?.ec?.userOverrides;
  const mobileInitialDrafts = useMemo(
    () => ({ ...(ecOverrides ?? {}) }),
    [ecOverrides],
  );
  const mobileInitialAdded = useMemo(() => {
    const m: Record<string, boolean> = {};
    for (const k of Object.keys(ecOverrides ?? {})) m[k] = true;
    return m;
  }, [ecOverrides]);
  // 담은 항목만 userOverrides 로 저장 — 기존 "표준 계약서 생성" 흐름에 그대로 연결.
  const handleMobilePersist = useCallback(
    (drafts: Record<string, string>, added: Record<string, boolean>) => {
      const ov: Record<string, string> = {};
      for (const f of mobileFindings) {
        if (added[f.key]) ov[f.key] = drafts[f.key] ?? f.fix;
      }
      updateEc(caseId, { userOverrides: ov });
    },
    [mobileFindings, caseId],
  );

  // ─── 훅 호출 끝. 이제 조기 return / 일반 분기 가능 ───
  if (!mounted) {
    // 서버·client 첫 페인트가 동일하도록 빈 컨테이너만.
    return <main className={styles.page} aria-hidden />;
  }

  if (!analysis) {
    return (
      <main className={styles.page}>
        <SiteHeader />
        <div className={styles.layout}>
          <div className={styles.notFound}>
            <div style={{ fontSize: 48, marginBottom: 12, opacity: 0.4 }}>🔍</div>
            <h1 className={styles.title}>검토 결과를 찾을 수 없어요</h1>
            <p style={{ marginBottom: 24, color: 'var(--color-text-muted)', lineHeight: 1.7 }}>
              아래 중 한 가지일 수 있어요:
              <br />
              <br />
              • 이 검토는 다른 브라우저·기기에서 진행된 것일 수 있어요
              <br />
              • 검토 이력에서 직접 삭제됐어요
              <br />
              • 링크가 오래되어 만료됐어요
            </p>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
              <Link
                href="/"
                style={{
                  background: 'var(--color-brand)',
                  color: '#fff',
                  padding: '10px 18px',
                  borderRadius: 8,
                  fontWeight: 700,
                  textDecoration: 'none',
                }}
              >
                ↺ 새로 검토 시작
              </Link>
              <Link
                href="/history"
                style={{
                  background: 'var(--color-surface)',
                  color: 'var(--color-text)',
                  border: '1px solid var(--color-border)',
                  padding: '10px 18px',
                  borderRadius: 8,
                  fontWeight: 600,
                  textDecoration: 'none',
                }}
              >
                📋 내 검토 보기
              </Link>
            </div>
          </div>
        </div>
      </main>
    );
  }

  const verdictKey = (analysis.overallStatus || '보완필요').trim();
  const verdictStyle = VERDICT_STYLES[verdictKey] ?? VERDICT_STYLES.보완필요;

  // 제안 모두 반영 — 모든 위반·보완 항목의 제안 표현(개선권고 또는 이미 담은 표현)을
  // 한 번에 userOverrides 에 저장. 항목별 '문서에 반영'을 일일이 누르지 않아도 됨.
  const handleApplyAll = () => {
    const prev = getCase(caseId)?.ec?.userOverrides ?? {};
    const next = { ...prev };
    let n = 0;
    for (const v of violations) {
      const sug = (next[v.항목] ?? v.개선권고 ?? '').trim();
      if (sug) {
        next[v.항목] = sug;
        n += 1;
      }
    }
    updateEc(caseId, { userOverrides: next });
    setEntry(getCase(caseId)); // 카드(SuggestBlock)가 '반영됨'으로 갱신되도록 재읽기
    setBulkMsg(
      n > 0
        ? `✓ ${n}개 항목의 제안을 모두 반영했어요 — '표준 계약서 생성' 시 본문에 그대로 사용됩니다.`
        : '반영할 제안 표현이 없어요.',
    );
    if (bulkTimerRef.current) clearTimeout(bulkTimerRef.current);
    bulkTimerRef.current = setTimeout(() => setBulkMsg(null), 4500);
  };

  // 표준 계약서 생성 — 데스크톱 CTA 와 모바일 '내 수정본 → 표준 계약서 만들기' 가 공유.
  const handleGenerate = () => {
    setGenerating(true);
    setGenError(null);
    updateEc(caseId, { phase: 'generating', errorMessage: undefined });
    router.push(routes.ecLoading(caseId));

    // 사용자가 "문서에 반영"(데스크톱)/"수정본에 담기"(모바일)로 저장한 보완 표현:
    //  1) analysis.results 의 `개선권고` 를 덮어쓰기 (LLM 이 분석 컨텍스트에서 보도록)
    //  2) 동시에 user_overrides 를 별도로 전달 → 백엔드 generate 프롬프트의
    //     "사용자 직접 작성 보완 표현 (반드시 그대로 사용)" 섹션에 강조 노출.
    const overrides = getCase(caseId)?.ec?.userOverrides ?? {};
    const mergedAnalysis: EcAnalysisResult = {
      ...analysis,
      results: analysis.results.map((r) =>
        overrides[r.항목]
          ? { ...r, 개선권고: overrides[r.항목] }
          : r,
      ),
    };

    postEcGenerate(mergedAnalysis, { userOverrides: overrides })
      .then((out) => {
        updateEc(caseId, {
          phase: 'contract',
          generatedContract: out.contract_text,
        });
      })
      .catch((err) => {
        const msg =
          err instanceof ApiCallError
            ? err.detail
            : err instanceof Error
              ? err.message
              : String(err);
        setCaseError(caseId, msg);
        updateEc(caseId, { phase: 'result', errorMessage: msg });
      });
  };

  // ─── 모바일 — 결과 단계 전용 풀스크린 앱 (데스크톱 레이아웃 미렌더) ───
  if (isMobile) {
    const mobileTone: 'bad' | 'warn' | 'ok' =
      verdictKey === '위험' ? 'bad' : verdictKey === '적정' ? 'ok' : 'warn';
    return (
      <MobileReviewApp
        docLabel="근로계약서"
        filename={entry?.originalFilename || '근로계약서'}
        verdict={{
          word: verdictKey,
          tone: mobileTone,
          summary: (analysis.overallOpinion || '')
            .replace(/<meta[^>]*>/g, '')
            .replace(/\s{2,}/g, ' ')
            .trim(),
        }}
        findings={mobileFindings}
        okCount={requirementBoard.stats.ok}
        extractedText={entry?.ec?.extractedText}
        imageUrl={entry?.originalKind === 'image' ? entry?.originalUrl : undefined}
        initialDrafts={mobileInitialDrafts}
        initialAdded={mobileInitialAdded}
        onPersist={handleMobilePersist}
        onBack={() => router.push('/')}
        onGenerate={handleGenerate}
        generateLabel="표준 계약서 만들기"
      />
    );
  }

  const elapsedSec = 0; // 백엔드에 누적값이 따로 없어 메타에 보조 라벨로 둠

  return (
    <main className={styles.page}>
      <SiteHeader />
      <div className={`${styles.layout} printAvoidBreak`}>
        <div
          className={`${styles.split} ${reviewMode === 'wide' ? styles.splitWide : ''} printStack`}
        >
          {/* ─── 좌: 업로드된 문서 패널 ─── */}
          <DocPanel
            filename={entry?.originalFilename || '근로계약서'}
            imageUrl={
              entry?.originalKind === 'image' ? entry?.originalUrl : undefined
            }
            extractedText={entry?.ec?.extractedText ?? ''}
            findings={violations}
            board={requirementBoard}
            focusedIndex={focusedIndex}
            onFocus={handleFocus}
            mode={reviewMode}
            onChangeMode={setReviewMode}
            structured={entry?.ec?.structuredData ?? null}
          />

          {/* ─── 우: 결과 패널 (검토 보기 모드에선 숨김 — 좌측이 전체폭) ─── */}
          <section
            className={styles.resultPanel}
            aria-label="검토 결과"
            hidden={reviewMode === 'wide'}
          >
            <header className={styles.metaRow}>
              <span className={styles.stepBadge}>근로계약서 · Step 3</span>
              <span className={styles.metaFilename}>
                {entry?.originalFilename || ''}
              </span>
              <span className={styles.metaTiming}>
                검토 완료{elapsedSec ? ` · ${elapsedSec}초` : ''}
              </span>
              <span
                className={styles.privacyChip}
                title="이름·사번·주민번호·전화·이메일·사업자번호 등 PII는 외부 LLM 호출 직전 자동 마스킹되어 전송됩니다"
              >
                🔒 비식별 처리됨
              </span>
              <button
                type="button"
                className={`${styles.printBtn} noPrint`}
                onClick={() => window.print()}
                aria-label="검토 결과 인쇄 또는 PDF 저장"
                title="브라우저 인쇄로 PDF 저장 가능"
              >
                📄 인쇄·PDF
              </button>
            </header>

            <VerdictBlock
              analysis={analysis}
              verdictStyle={verdictStyle}
              stats={requirementBoard.stats}
            />

            <FindingCarousel
              findings={violations}
              caseId={caseId}
              initialOverrides={entry?.ec?.userOverrides ?? {}}
              controlledIndex={focusedIndex}
              onIndexChange={handleFocus}
            />

            <div className={`${styles.ctaBar} noPrint`}>
              <Link
                href={routes.ecContract(caseId)}
                className={styles.btnSecondary}
              >
                ← 검토 페이지로
              </Link>
              <button
                type="button"
                className={styles.btnSecondary}
                onClick={handleApplyAll}
                disabled={generating || violations.length === 0}
                title="모든 위반·보완 항목의 제안 표현을 한 번에 반영합니다"
              >
                ✨ 제안 모두 반영
              </button>
              <button
                type="button"
                className={styles.btnPrimary}
                onClick={handleGenerate}
                disabled={generating}
              >
                {generating ? '계약서 생성 중…' : '표준 계약서 생성'}
              </button>
            </div>

            {bulkMsg && (
              <div
                className="noPrint"
                role="status"
                aria-live="polite"
                style={{
                  marginTop: 10,
                  padding: '10px 14px',
                  borderRadius: 10,
                  background: 'rgba(5, 150, 105, 0.08)',
                  border: '1px solid rgba(5, 150, 105, 0.35)',
                  color: '#065f46',
                  fontSize: 13,
                  fontWeight: 600,
                  lineHeight: 1.55,
                }}
              >
                {bulkMsg}
              </div>
            )}

            {genError && (
              <div className={styles.error}>
                <strong>생성 실패:</strong> {genError}
              </div>
            )}

            {/* 인쇄 전용 푸터 */}
            <div className={`${styles.printFooter} printOnly`}>
              <hr />
              <p>
                <strong>영세사업장 자율점검 서비스</strong> · 근로계약서 검토 결과 ·
                인쇄 시각 {new Date().toLocaleString('ko-KR')}
              </p>
              <p>
                ※ 이 보고서는 AI 기반 자율점검 도구의 분석 결과입니다.
                법적 효력은 사업장·노무사의 검토를 통해 확정됩니다.
              </p>
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}

/* ════════════════════════════════════════════════════════
 * 좌측 컬럼 — 업로드된 문서 패널
 * ════════════════════════════════════════════════════════ */

/** 데모용 mock 페이지 — 추후 OCR 좌표 매핑으로 대체. */
function buildMockPages(): ContractPage[] {
  const M = (
    no: number,
    text: string,
    tone: ContractMarker['tone'],
    note?: string,
  ) => (
    <CircleMarker key={`m${no}`} no={no} tone={tone} text={text} note={note} />
  );
  return [
    {
      title: '제 1 ~ 5 조',
      body: (
        <div className={styles.docText}>
          <h4 className={styles.docDocTitle}>근 로 계 약 서</h4>
          <p>
            본 계약은 주식회사 ㅇㅇㅇ(이하 &ldquo;회사&rdquo;라 함)와 근로자{' '}
            {M(1, '김원대', 'ok')} (이하 &ldquo;사원&rdquo;이라 함)는
            근로기준법 및 회사 제반 규정을 성실히 준수할 것을 약정하고 다음과
            같이 근로계약을 체결한다.
          </p>
          <p>
            <strong>제 1 조</strong> [근무지 및 담당업무]
            <br />
            {M(2, '덕왕왓갯됱', 'ok')}
          </p>
          <p>
            2. 회사의 업무 사정에 따른 <strong>전직(轉職)</strong>·전보(轉補) 등을 할 수
            있으며, &ldquo;사원&rdquo;은 이에 따른다.
          </p>
          <p>
            <strong>제 2 조</strong> [계약기간]
            <br />
            쌍방의 근로 계약기간은 {M(3, '2022-04-02 ~ 04-30', 'ok')} 로 근로
            계약기간 만료로 인한 근로 관계는 당연 만료된다.
          </p>
          <p>
            <strong>제 3 조</strong> [근로시간]
            <br />
            1. 1주 소정근로일은 1일, 일 소정근로시간은 8시간으로 하며,
            &ldquo;사원&rdquo;의 동의를 얻어 변경될 수 있다.
          </p>
          <table className={styles.docTable}>
            <tbody>
              <tr>
                <td>근무 일자 및 요일</td>
                <td>2022-04-02 / {M(4, '토요일', 'partial', '근로일별 표기 모호')}</td>
              </tr>
              <tr>
                <td>시업시각</td>
                <td>{M(5, '09:00', 'ok')}</td>
              </tr>
              <tr>
                <td>종업시각</td>
                <td>{M(6, '20:30', 'ok')}</td>
              </tr>
              <tr>
                <td>휴게시간</td>
                <td>{M(7, '12:00~13:00', 'ok')}</td>
              </tr>
            </tbody>
          </table>
        </div>
      ),
    },
    {
      title: '제 6 ~ 11 조',
      body: (
        <div className={styles.docText}>
          <p>
            <strong>제 4 조</strong> [임금]
            <br />
            1. &ldquo;사원&rdquo;의 시급액은{' '}
            {M(8, '9,160', 'bad', '임금 총액·구성항목·계산방법 누락')}원으로 한다.
          </p>
          <p>
            2. 임금 지급일은 매월 5일이며, 본인 명의 예금계좌로 입금한다(소득세
            및 이체수수료 제외 후 지급).
          </p>
          <p>
            <strong>제 5 조</strong> [퇴직금]
            <br />
            {M(9, '퇴직금', 'bad', '퇴직금 조항 누락')} 관련 사항은 별도로
            규정한다.
          </p>
          <p>
            <strong>제 6 조</strong> [사회보험]
            <br />
            {M(10, '4대보험', 'bad', '4대보험 가입 여부 누락')} 가입 여부에
            관한 별도 약정이 없다.
          </p>
          <p>
            <strong>제 7 조</strong> [연차유급휴가]
            <br />
            연차는 법령에 따라{' '}
            {M(11, '연차', 'partial', '연차 구체적 기재 필요')} 부여한다.
          </p>
          <p>
            <strong>제 8 조</strong> [기타]
            <br />
            본 계약서에 정하지 아니한 사항은 근로기준법 및 회사 취업규칙에
            따른다.
          </p>
        </div>
      ),
    },
    {
      title: '작성일자·서명란',
      body: (
        <div className={styles.docText}>
          <p>
            본 계약을 증명하기 위하여 본 계약서를 2부 작성하여 각자 서명·날인 후
            1부씩 보관한다.
          </p>
          <p className={styles.docDate}>
            작성일: {M(12, '____ 년 __ 월 __ 일', 'bad', '계약서 작성일 미기재')}
          </p>
          <div className={styles.docSign}>
            <div>
              <div className={styles.docSignLabel}>(사용자)</div>
              <div>회사명: 주식회사 ㅇㅇㅇ</div>
              <div>대표자: __________________ (서명/날인)</div>
            </div>
            <div>
              <div className={styles.docSignLabel}>(근로자)</div>
              <div>성명: __________________ (서명/날인)</div>
              <div>주민번호: __________-_______</div>
            </div>
          </div>
        </div>
      ),
    },
  ];
}

interface DocPanelProps {
  filename: string;
  imageUrl?: string;
  extractedText: string;
  /** 공식 표준계약서 양식 뷰 노드(읽기 전용) — 있으면 첫 페이지로 노출. */
  formNode?: ReactNode;
  /** 분석 결과 — 본문에서 위반 위치를 찾아 Circle 마커로 강조하기 위함. */
  findings: EcAnalysisItem[];
  board: RequirementBoard;
  /** 현재 focus 된 항목 인덱스(0-based, findings 기준) — 본문 마크·칩 강조. */
  focusedIndex: number;
  /** 칩·본문 마크 클릭 시 부모에 focus 알림. */
  onFocus: (index: number) => void;
  /** 보기 모드 — 'split'(나란히) / 'wide'(검토 보기, 전체폭+거터). */
  mode: 'split' | 'wide';
  onChangeMode: (m: 'split' | 'wide') => void;
  /** 현재 근로계약서 구조화 데이터 — 있으면 HTML 표(첫·유일 페이지)로 노출. */
  structured?: EcStructuredData | null;
}

/**
 * 추출 텍스트 + findings → 마커 포함 인라인 본문 ReactNode.
 *
 * 매칭된 finding 마다 그 위치에 CircleMarker 삽입, 매칭 안 된 finding 은 skip
 * (어차피 우측 캐러셀에 다 있음).
 */
function renderTextWithMarkers(
  text: string,
  findings: EcAnalysisItem[],
): ReactNode {
  const hits = buildMarkerHits(text, findings);
  if (hits.length === 0) {
    return <span>{text}</span>;
  }
  const out: ReactNode[] = [];
  let cur = 0;
  hits.forEach((h, idx) => {
    // 1) marker 직전까지의 일반 텍스트
    if (h.index > cur) {
      out.push(<Fragment key={`t-${cur}`}>{text.slice(cur, h.index)}</Fragment>);
    }
    // 2) 번호 동그라미(vnum) — data-vno 로 focus 토글·클릭을 effect 에서 처리.
    //    인라인 라벨(Note)은 제거 — 요약은 상단 칩 줄띠 + 우측 카드가 담당(가독성↑).
    const tone = toneOf(h.finding.적절성);
    const toneCls =
      tone === 'bad' ? 'bad' : tone === 'partial' ? 'warn' : 'ok';
    out.push(
      <span
        key={`vn-${idx}-${h.index}`}
        className={`${styles.vnum} ${styles[`vnum_${toneCls}`]}`}
        data-vno={h.no}
      >
        {h.no}
      </span>,
    );
    // 3) 매칭된 본문 토큰을 색 하이라이트(mark)로 감싸 위치를 보이게. 라벨은 없음.
    out.push(
      <mark
        key={`mk-${idx}-${h.index}`}
        className={`${styles.vioMark} ${styles[`vioMark_${toneCls}`]}`}
        data-vno={h.no}
      >
        {text.slice(h.index, h.index + h.length)}
      </mark>,
    );
    cur = h.index + h.length;
  });
  if (cur < text.length) {
    out.push(<Fragment key={`t-${cur}`}>{text.slice(cur)}</Fragment>);
  }
  return out;
}

/**
 * 실 데이터 기반 페이지 빌더 — 추출 텍스트/이미지가 있으면 그것으로,
 * 둘 다 없을 때만 mock 페이지로 fallback.
 */
const EC_SECTION_ORDER = [
  '기본정보',
  '계약사항',
  '근로시간',
  '휴일휴가',
  '임금',
  '퇴직급여',
  '사회보험',
  '계약체결',
];

/**
 * 현재 근로계약서를 HTML 표로 — 8섹션 구조화 데이터(이미 보유)를 표로 렌더.
 * 항목명이 지적과 매칭되는 행에 ⚠ + data-vno → 기존 focus-sync 로 우측 상세 연동.
 */
function buildEcContractTablePage(
  sd: EcStructuredData,
  findings: EcAnalysisItem[],
): ContractPage {
  const norm = (s: string) => (s || '').replace(/\s/g, '');
  const findNo = (fieldKey: string): number | null => {
    const fk = norm(fieldKey);
    if (fk.length < 2) return null;
    const i = findings.findIndex((f) => {
      const a = norm(f.항목 || '');
      return !!a && (a.includes(fk) || fk.includes(a));
    });
    return i >= 0 ? i + 1 : null;
  };

  const sections = [
    ...EC_SECTION_ORDER.filter(
      (s) => sd[s] && typeof sd[s] === 'object' && !Array.isArray(sd[s]),
    ),
    ...Object.keys(sd).filter(
      (k) =>
        !EC_SECTION_ORDER.includes(k) &&
        k !== '기타사항' &&
        sd[k] &&
        typeof sd[k] === 'object' &&
        !Array.isArray(sd[k]),
    ),
  ];

  return {
    title: '서식(표)',
    body: (
      <div className={styles.ecTblWrap}>
        <table className={styles.ecTbl}>
          <colgroup>
            <col style={{ width: '32%' }} />
            <col />
          </colgroup>
          <tbody>
            {sections.map((sec) => {
              const obj = sd[sec] as Record<
                string,
                { value: string; note: string }
              >;
              const keys = Object.keys(obj || {});
              if (!keys.length) return null;
              return (
                <Fragment key={sec}>
                  <tr className={styles.ecTblSection}>
                    <td colSpan={2}>{sec}</td>
                  </tr>
                  {keys.map((fk) => {
                    const f = obj[fk] || { value: '', note: '' };
                    const no = findNo(fk);
                    return (
                      <tr
                        key={sec + fk}
                        className={`${styles.ecTblRow} ${no ? styles.ftRowFlag : ''}`}
                        data-vno={no || undefined}
                      >
                        <th>
                          {fk}
                          {no ? (
                            <span className={styles.ftWarn} title="지적 항목 — 클릭하면 상세"> ⚠</span>
                          ) : null}
                        </th>
                        <td>
                          {f.value || '(미기재)'}
                          {f.note ? <div className={styles.ecTblNote}>{f.note}</div> : null}
                        </td>
                      </tr>
                    );
                  })}
                </Fragment>
              );
            })}
            {Array.isArray(sd.기타사항) && sd.기타사항.length ? (
              <Fragment>
                <tr className={styles.ecTblSection}>
                  <td colSpan={2}>기타사항</td>
                </tr>
                <tr>
                  <td colSpan={2}>
                    <ul className={styles.ecTblEtc}>
                      {sd.기타사항.map((t, i) => (
                        <li key={i}>{t}</li>
                      ))}
                    </ul>
                  </td>
                </tr>
              </Fragment>
            ) : null}
          </tbody>
        </table>
      </div>
    ),
  };
}

function buildRealPages(
  imageUrl: string | undefined,
  extractedText: string,
  filename: string,
  findings: EcAnalysisItem[],
  onImageError?: () => void,
  formNode?: ReactNode,
  structured?: EcStructuredData | null,
): ContractPage[] {
  // 구조화 표가 준비되면 **표만** 보여준다(원본 텍스트·이미지 페이지 제거). 없으면 폴백.
  if (structured && typeof structured === 'object') {
    return [buildEcContractTablePage(structured, findings)];
  }
  const pages: ContractPage[] = [];
  // 원본 이미지를 첫 페이지(기본)로 — 검토 중 원본과 비교하는 게 핵심.
  if (imageUrl) {
    pages.push({
      title: '원본 이미지',
      body: (
        <div className={styles.docImageScroll}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={imageUrl}
            alt={filename}
            className={styles.docImage}
            onError={onImageError}
            draggable={false}
            onDragStart={(e) => e.preventDefault()}
          />
        </div>
      ),
    });
  }
  // 표준 양식(구조화 + 보완 칩) — 원본 다음 페이지.
  if (formNode) {
    pages.push({
      title: '표준 양식',
      body: <div className={styles.docFormScroll}>{formNode}</div>,
    });
  }
  if (extractedText.trim()) {
    pages.push({
      title: '추출 텍스트',
      body: (
        <div className={styles.docExtractedScroll}>
          <pre className={styles.docExtractedText}>
            {renderTextWithMarkers(extractedText, findings)}
          </pre>
        </div>
      ),
    });
  }
  if (pages.length === 0) return buildMockPages();
  return pages;
}

function DocPanel({
  filename,
  imageUrl,
  extractedText,
  formNode,
  findings,
  board,
  focusedIndex,
  onFocus,
  mode,
  onChangeMode,
  structured,
}: DocPanelProps) {
  // blob: URL 이 만료(새로고침 등) 되면 img 가 onError 발생 → 그때부터 이미지 페이지 제거.
  const [imageBroken, setImageBroken] = useState(false);
  const effectiveImageUrl = imageBroken ? undefined : imageUrl;

  const pages = useMemo(
    () =>
      buildRealPages(
        effectiveImageUrl,
        extractedText,
        filename,
        findings,
        () => setImageBroken(true),
        formNode,
        structured,
      ),
    [effectiveImageUrl, extractedText, filename, findings, formNode, structured],
  );
  const [pageIdx, setPageIdx] = useState(0);
  const safeIdx = Math.min(pageIdx, pages.length - 1);
  const prev = () =>
    setPageIdx((i) => (i - 1 + pages.length) % pages.length);
  const next = () => setPageIdx((i) => (i + 1) % pages.length);

  // 본문 마크/번호 ↔ focus 동기화 (데모 방식: DOM classList 토글 + 클릭 핸들러 + 스크롤).
  // 본문은 메모이즈된 정적 노드라 onClick 을 effect 에서 위임 — 매 렌더 재생성 안 함.
  const docBodyRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const root = docBodyRef.current;
    if (!root) return;
    const nodes = root.querySelectorAll<HTMLElement>('[data-vno]');
    const focusNo = focusedIndex + 1;
    nodes.forEach((el) => {
      const n = Number(el.dataset.vno);
      el.classList.toggle(styles.vnumFocus, el.tagName === 'SPAN' && n === focusNo);
      el.classList.toggle(styles.vioMarkFocus, el.tagName === 'MARK' && n === focusNo);
      // 표(서식) 행 — 지적 항목 클릭 시 우측 상세 연동 + 현재 focus 행 하이라이트.
      el.classList.toggle(
        styles.ftRowFocus,
        (el.tagName === 'TR' || el.tagName === 'TD') && n === focusNo,
      );
      // 클릭 → 부모에 focus 통보 (idempotent — 매번 재할당해도 OK)
      el.onclick = () => onFocus(n - 1);
    });
    // 현재 focus 된 마크를 가운데로 스크롤 (나란히 모드에서만 — wide 는 전체 흐름)
    if (mode !== 'wide') {
      const target = root.querySelector<HTMLElement>(`mark[data-vno="${focusNo}"]`);
      if (target) target.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  }, [focusedIndex, safeIdx, findings, onFocus, mode]);

  // 검토 보기(wide) — 본문 각 번호의 Y 위치를 읽어 우측 거터에 라벨을 줄별 정렬.
  const [gutter, setGutter] = useState<
    { no: number; top: number; tone: 'bad' | 'warn'; label: string }[]
  >([]);
  useEffect(() => {
    const root = docBodyRef.current;
    if (!root || mode !== 'wide') {
      setGutter([]);
      return;
    }
    const compute = () => {
      const rootRect = root.getBoundingClientRect();
      const placed: number[] = [];
      const items: { no: number; top: number; tone: 'bad' | 'warn'; label: string }[] = [];
      findings.forEach((f, i) => {
        const el = root.querySelector<HTMLElement>(`.${styles.vnum}[data-vno="${i + 1}"]`);
        if (!el) return;
        let top = el.getBoundingClientRect().top - rootRect.top + root.scrollTop;
        // 40px 미만 겹침이면 아래로 밀어 분리
        for (const p of [...placed].sort((a, b) => a - b)) {
          if (Math.abs(top - p) < 40) top = p + 40;
        }
        placed.push(top);
        items.push({
          no: i + 1,
          top,
          tone: f.적절성 === '부적절' ? 'bad' : 'warn',
          label: shortNoteForFinding(f),
        });
      });
      setGutter(items);
    };
    // 레이아웃 안정화 후 측정 (폰트·이미지 로드 반영)
    const raf = requestAnimationFrame(compute);
    window.addEventListener('resize', compute);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', compute);
    };
  }, [mode, findings, safeIdx]);

  // 좌측 문서 스와이프 — 페이지(이미지↔텍스트) 넘김.
  // 핵심: 수평 드래그를 "감지한 순간"에만 텍스트 선택을 끄고 캡처 → 클릭/세로
  // 스크롤/텍스트선택과 충돌하지 않으면서 수평 스와이프만 페이지 전환.
  const dragRef = useRef<{ x: number; y: number; active: boolean; pid: number } | null>(
    null,
  );
  const onDocPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    dragRef.current = { x: e.clientX, y: e.clientY, active: false, pid: e.pointerId };
  };
  const onDocPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const d = dragRef.current;
    if (!d || pages.length < 2) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (!d.active && Math.abs(dx) > 12 && Math.abs(dx) > Math.abs(dy)) {
      d.active = true; // 수평 드래그 확정
      try {
        e.currentTarget.setPointerCapture(d.pid);
      } catch {
        /* noop */
      }
      if (docBodyRef.current) docBodyRef.current.style.userSelect = 'none';
      window.getSelection()?.removeAllRanges?.();
    }
  };
  const onDocPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    const d = dragRef.current;
    dragRef.current = null;
    if (docBodyRef.current) docBodyRef.current.style.userSelect = '';
    if (!d || !d.active || pages.length < 2) return;
    const dx = e.clientX - d.x;
    if (Math.abs(dx) < 50) return;
    if (dx < 0) next();
    else prev();
  };

  return (
    <aside className={styles.docPanel} aria-label="업로드된 문서">
      <header className={styles.docHead}>
        <span className={styles.docHeadTitle}>업로드된 문서</span>
        <div className={styles.docHeadRight}>
          <span className={styles.docHeadFilename} title={filename}>
            {filename}
          </span>
          {pages.length > 1 && (
            <>
              <span className={styles.docHeadCounter}>
                {safeIdx + 1} / {pages.length}
              </span>
              <button
                type="button"
                className={styles.docHeadNav}
                onClick={prev}
                aria-label="이전 페이지"
              >
                ‹
              </button>
              <button
                type="button"
                className={styles.docHeadNav}
                onClick={next}
                aria-label="다음 페이지"
              >
                ›
              </button>
            </>
          )}
          {/* 나란히 / 검토 보기 토글 */}
          <div className={styles.viewToggle}>
            <button
              type="button"
              className={`${styles.viewToggleBtn} ${mode === 'split' ? styles.viewToggleOn : ''}`}
              onClick={() => onChangeMode('split')}
            >
              나란히
            </button>
            <button
              type="button"
              className={`${styles.viewToggleBtn} ${mode === 'wide' ? styles.viewToggleOn : ''}`}
              onClick={() => onChangeMode('wide')}
            >
              검토 보기
            </button>
          </div>
        </div>
      </header>

      <ViolationChipStrip
        findings={findings}
        board={board}
        focusedIndex={focusedIndex}
        onFocus={onFocus}
      />

      <div
        className={`${styles.docBody} ${mode === 'wide' ? styles.docBodyWide : ''}`}
        ref={docBodyRef}
        onPointerDown={onDocPointerDown}
        onPointerMove={onDocPointerMove}
        onPointerUp={onDocPointerUp}
      >
        {pages[safeIdx].title === '원본 이미지' ||
        pages[safeIdx].title === '추출 텍스트' ||
        pages[safeIdx].title === '서식(표)' ? (
          /* 실데이터: 페이지 자체가 스크롤 컨테이너를 갖고 있음 */
          pages[safeIdx].body
        ) : (
          /* mock 페이지: 종이 카드로 감쌈 */
          <div className={styles.docPaper}>{pages[safeIdx].body}</div>
        )}
        {/* 검토 보기 거터 — 각 번호 줄에 라벨 정렬 */}
        {mode === 'wide' &&
          gutter.map((g) => (
            <button
              key={g.no}
              type="button"
              className={`${styles.gutItem} ${styles[`gutItem_${g.tone}`]} ${
                g.no === focusedIndex + 1 ? styles.gutItemActive : ''
              }`}
              style={{ top: g.top }}
              onClick={() => onFocus(g.no - 1)}
            >
              <span className={`${styles.gutNum} ${styles[`gutNum_${g.tone}`]}`}>
                {g.no}
              </span>
              {g.label}
            </button>
          ))}
      </div>

      {pages.length > 1 && (
        <DocDots count={pages.length} active={safeIdx} onJump={setPageIdx} />
      )}
    </aside>
  );
}

/* ════════════════════════════════════════════════════════
 * ViolationChipStrip — 계약서 위 "요약 칩 줄띠" (위반 한눈에 보기)
 *   본문 중간 라벨을 없애는 대신, 위반·보완을 번호순 칩으로 상단에 나열.
 *   칩 클릭 → 본문 마크 강조·스크롤 + 우측 카드 연동.
 * ════════════════════════════════════════════════════════ */
function ViolationChipStrip({
  findings,
  board,
  focusedIndex,
  onFocus,
}: {
  findings: EcAnalysisItem[];
  board: RequirementBoard;
  focusedIndex: number;
  onFocus: (index: number) => void;
}) {
  const [folded, setFolded] = useState(false);
  // findings 는 sortedResults(부적절→보완필요→적절). 번호 = 인덱스+1 (본문 마크와 동일).
  const chips = findings
    .map((f, i) => ({ f, i }))
    .filter(({ f }) => f.적절성 !== '적절');
  if (chips.length === 0) {
    return <CompactSummary board={board} />;
  }
  const badN = chips.filter(({ f }) => f.적절성 === '부적절').length;
  const warnN = chips.filter(({ f }) => f.적절성 === '보완필요').length;
  return (
    <div className={styles.vchipStrip}>
      <div className={styles.vchipHead}>
        <span className={styles.vchipTitle}>
          이 계약서의 위반·보완 {chips.length}건
        </span>
        <span className={styles.vchipCount}>
          · 부적절 <strong className={styles.vchipCountBad}>{badN}</strong> · 보완필요{' '}
          <strong className={styles.vchipCountWarn}>{warnN}</strong>
        </span>
        <button
          type="button"
          className={styles.vchipFold}
          onClick={() => setFolded((v) => !v)}
        >
          {folded ? '펼치기 ▸' : '접기 ▾'}
        </button>
      </div>
      {!folded && (
        <div className={styles.vchipList}>
          {chips.map(({ f, i }) => {
            const toneCls = f.적절성 === '부적절' ? 'bad' : 'warn';
            return (
              <button
                key={f.항목 + i}
                type="button"
                className={`${styles.vchip} ${styles[`vchip_${toneCls}`]} ${
                  i === focusedIndex ? styles.vchipActive : ''
                }`}
                onClick={() => onFocus(i)}
              >
                <span className={`${styles.vchipNum} ${styles[`vchipNum_${toneCls}`]}`}>
                  {i + 1}
                </span>
                {shortNoteForFinding(f)}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function CircleMarker({
  no,
  tone,
  text,
  note,
  compact = false,
}: {
  no: number;
  tone: 'ok' | 'partial' | 'bad';
  text: string;
  note?: string;
  /** compact=true 면 본문엔 번호 동그라미만 (항목명 칩 숨김) — 가독성 ↑ */
  compact?: boolean;
}) {
  // compact 모드 — 작은 번호 배지만 (본문 흐름 안 깨짐). 항목명은 줄 끝 Note 가 담당.
  if (compact) {
    return (
      <span
        className={`${styles.circleNum} ${styles[`circleNum_${tone}`]}`}
        aria-label={`${no}번 표시: ${text}`}
        title={text}
      >
        {no}
      </span>
    );
  }
  return (
    <span className={styles.circleWrap}>
      <span
        className={`${styles.circle} ${styles[`circle_${tone}`]}`}
        aria-label={`${no}번 표시`}
      >
        <span className={`${styles.circleBadge} ${styles[`circleBadge_${tone}`]}`}>
          {no}
        </span>
        <span className={styles.circleText}>{text}</span>
      </span>
      {note && (
        <span className={`${styles.circleNote} ${styles[`circleNote_${tone}`]}`}>
          ← {note}
        </span>
      )}
    </span>
  );
}

function DocDots({
  count,
  active,
  onJump,
}: {
  count: number;
  active: number;
  onJump: (i: number) => void;
}) {
  return (
    <div className={styles.docDots} role="tablist">
      {Array.from({ length: count }).map((_, i) => {
        const isActive = i === active;
        return (
          <button
            key={i}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onJump(i)}
            className={`${styles.docDot} ${isActive ? styles.docDotActive : ''}`}
            aria-label={`${i + 1}번째 페이지`}
          />
        );
      })}
    </div>
  );
}

/* ════════════════════════════════════════════════════════
 * 컴팩트 요약 (DocPanel 상단)
 * ════════════════════════════════════════════════════════ */

function CompactSummary({ board }: { board: RequirementBoard }) {
  const { stats } = board;
  const denom = stats.total - stats.na;
  const pct = (n: number) =>
    stats.total === 0 ? 0 : (n / stats.total) * 100;
  return (
    <section className={styles.compact} aria-label="필수 기재사항 요약">
      <div className={styles.compactRow}>
        <span className={styles.compactTitle}>이 사업장에 필요한 필수 기재사항</span>
        <span className={styles.compactCounter}>
          <span className={styles.compactCounterNum}>
            {stats.ok}
          </span>
          <span className={styles.compactCounterSep}> / </span>
          <span className={styles.compactCounterNum}>{denom}</span>
          <span className={styles.compactCounterLabel}> 기재완료</span>
        </span>
      </div>
      <div className={styles.compactBar} aria-hidden>
        <div
          className={`${styles.compactSeg} ${styles.compactSegOk}`}
          style={{ width: `${pct(stats.ok)}%` }}
        />
        <div
          className={`${styles.compactSeg} ${styles.compactSegPartial}`}
          style={{ width: `${pct(stats.partial)}%` }}
        />
        <div
          className={`${styles.compactSeg} ${styles.compactSegBad}`}
          style={{ width: `${pct(stats.bad)}%` }}
        />
      </div>
      <div className={styles.compactCountsRow}>
        <span className={styles.compactCountItem}>
          <span className={`${styles.compactDot} ${styles.dotBad}`} aria-hidden />
          <span className={styles.compactCountLabel}>미기재</span>
          <span className={styles.compactCountNum}>{stats.bad}</span>
        </span>
        <span className={styles.compactCountItem}>
          <span
            className={`${styles.compactDot} ${styles.dotPartial}`}
            aria-hidden
          />
          <span className={styles.compactCountLabel}>보완</span>
          <span className={styles.compactCountNum}>{stats.partial}</span>
        </span>
        <span className={styles.compactCountItem}>
          <span className={`${styles.compactDot} ${styles.dotOk}`} aria-hidden />
          <span className={styles.compactCountLabel}>적절</span>
          <span className={styles.compactCountNum}>{stats.ok}</span>
        </span>
      </div>
    </section>
  );
}

/* ════════════════════════════════════════════════════════
 * 단일 데이터 소스 — Requirement Board
 * ════════════════════════════════════════════════════════ */

function buildRequirementBoard(
  businessSize: string,
  workerTypes: string[],
  results: EcAnalysisItem[],
): RequirementBoard {
  const rawGroups = filterApplicableGroups(businessSize, workerTypes);
  const groups: BoardGroup[] = rawGroups.map((g) => ({
    key: g.key,
    label: g.label,
    description: g.description,
    items: g.items.map((it) => ({ name: it, status: statusForItem(it, results) })),
  }));
  const stats: RequirementStats = { ok: 0, partial: 0, bad: 0, na: 0, total: 0 };
  for (const g of groups) {
    for (const it of g.items) {
      stats.total += 1;
      if (it.status === '적절') stats.ok += 1;
      else if (it.status === '보완필요') stats.partial += 1;
      else if (it.status === '부적절') stats.bad += 1;
      else stats.na += 1;
    }
  }
  return { groups, stats };
}

/* ════════════════════════════════════════════════════════
 * 종합 판정 카드 (게이지 + 우측 텍스트 + 통계 3분할)
 * ════════════════════════════════════════════════════════ */

function VerdictBlock({ analysis, verdictStyle, stats }: VerdictBlockProps) {
  const { text } = useMemo(
    () => parseMetaTags(analysis.overallOpinion || ''),
    [analysis.overallOpinion],
  );
  const riskLevel = (analysis.riskLevel || '').trim();
  const riskTone: 'high' | 'mid' | 'low' =
    riskLevel === '상' ? 'high' : riskLevel === '중' ? 'mid' : 'low';
  return (
    <div className={styles.verdictCard}>
      <div className={styles.verdictDash}>
        <GaugeArc tone={riskTone} level={riskLevel} />
        <div className={styles.verdictDashBody}>
          <div className={styles.verdictLabel}>종합 판정</div>
          <div className={`${styles.verdictText} ${verdictStyle.text}`}>
            {analysis.overallStatus}
          </div>
          {text && (
            <div className={styles.verdictSummary} title={text}>
              {emphasize(text)}
            </div>
          )}
          <div className={styles.statRow}>
            <StatCard tone="bad" label="부적절" value={stats.bad} />
            <StatCard tone="mid" label="보완필요" value={stats.partial} />
            <StatCard tone="ok" label="적절" value={stats.ok} />
          </div>
        </div>
      </div>
    </div>
  );
}

function GaugeArc({
  tone,
  level,
}: {
  tone: 'high' | 'mid' | 'low';
  level: string;
}) {
  const COLOR: Record<typeof tone, string> = {
    high: '#dc2626',
    mid: '#d97706',
    low: '#059669',
  };
  const ENG: Record<typeof tone, string> = {
    high: 'HIGH',
    mid: 'MID',
    low: 'LOW',
  };
  const RATIO: Record<typeof tone, number> = {
    high: 0.8,
    mid: 0.5,
    low: 0.2,
  };
  const ratio = RATIO[tone];
  const r = 70;
  const circumference = Math.PI * r;
  const offset = circumference * (1 - ratio);
  return (
    <div className={styles.gaugeWrap} role="img" aria-label={`위험도 ${level}`}>
      <div className={styles.gaugeTopLabel} aria-hidden>
        위험도
      </div>
      <svg
        viewBox="0 0 180 110"
        width="180"
        height="110"
        className={styles.gaugeSvg}
        aria-hidden
      >
        <path
          d="M 20 95 A 70 70 0 0 1 160 95"
          fill="none"
          stroke="#f1f5f9"
          strokeWidth="14"
          strokeLinecap="round"
        />
        <path
          d="M 20 95 A 70 70 0 0 1 160 95"
          fill="none"
          stroke={COLOR[tone]}
          strokeWidth="14"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
        {[0, 25, 50, 75, 100].map((t) => {
          const a = (Math.PI * (180 - (180 * t) / 100)) / 180;
          return (
            <line
              key={t}
              x1={90 + Math.cos(a) * 78}
              y1={95 - Math.sin(a) * 78}
              x2={90 + Math.cos(a) * 86}
              y2={95 - Math.sin(a) * 86}
              stroke="#94a3b8"
              strokeWidth={1.5}
              strokeLinecap="round"
            />
          );
        })}
      </svg>
      <div className={styles.gaugeLevelWrap} aria-hidden>
        <span className={styles.gaugeLevel} style={{ color: COLOR[tone] }}>
          {level || '—'}
        </span>
      </div>
      <div className={styles.gaugeBottomLabel} aria-hidden>
        {ENG[tone]}
      </div>
    </div>
  );
}

function StatCard({
  tone,
  label,
  value,
}: {
  tone: 'bad' | 'mid' | 'ok';
  label: string;
  value: number;
}) {
  const COLOR: Record<typeof tone, string> = {
    bad: '#dc2626',
    mid: '#d97706',
    ok: '#059669',
  };
  return (
    <div className={styles.statCard}>
      <div className={styles.statHead}>
        <span
          className={styles.statDot}
          style={{ background: COLOR[tone] }}
          aria-hidden
        />
        <span className={styles.statLabel}>{label}</span>
      </div>
      <div className={styles.statValue} style={{ color: COLOR[tone] }}>
        {value}
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════
 * 항목별 상세 — 스와이프 캐러셀
 * ════════════════════════════════════════════════════════ */

const SWIPE_THRESHOLD = 40;

interface FindingCarouselProps {
  findings: EcAnalysisItem[];
  caseId: string;
  initialOverrides: Record<string, string>;
  /** 외부 focus(좌측 칩·본문) 와 동기화할 인덱스. 바뀌면 캐러셀이 그 항목으로 이동. */
  controlledIndex?: number;
  /** 활성 항목 인덱스를 부모에게 알림 — 좌측 focus 동기화용. */
  onIndexChange?: (index: number) => void;
}

function FindingCarousel({
  findings,
  caseId,
  initialOverrides,
  controlledIndex,
  onIndexChange,
}: FindingCarouselProps) {
  // remount(제안 일괄 담기 시 key 변경) 시 index 를 controlledIndex 로 초기화 — 0 으로
  // 리셋하면 두 동기화 effect 가 서로 밀어내며 무한 진동(WS 에서 수정된 것과 동일).
  const [index, setIndex] = useState(() =>
    typeof controlledIndex === 'number' && controlledIndex >= 0 ? controlledIndex : 0,
  );
  const startXRef = useRef<number | null>(null);
  // 부모로 인덱스 통보
  useEffect(() => {
    onIndexChange?.(index);
  }, [index, onIndexChange]);
  // 외부 focus(좌측 칩·본문 클릭)로 인덱스 동기화
  useEffect(() => {
    if (
      typeof controlledIndex === 'number' &&
      controlledIndex >= 0 &&
      controlledIndex !== index
    ) {
      setIndex(controlledIndex);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [controlledIndex]);

  if (findings.length === 0) return null;
  const cur = findings[Math.min(index, findings.length - 1)];

  // 주의: setPointerCapture 를 쓰지 않는다. 캡처하면 카드 안의 법령 링크·버튼
  // 클릭이 스테이지 div 로 먹혀 <a> 가 navigate 하지 않는다. startX 만 기록하고
  // pointerup 의 이동량으로 스와이프를 판정 — 이동이 작으면(=클릭) 아무것도 안 해서
  // 자식 요소의 클릭이 자연스럽게 발생한다.
  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    startXRef.current = e.clientX;
  };
  const onPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (startXRef.current == null) return;
    const dx = e.clientX - startXRef.current;
    startXRef.current = null;
    if (Math.abs(dx) < SWIPE_THRESHOLD) return; // 클릭 — 자식(링크/버튼)에 맡김
    setIndex((i) => {
      const total = findings.length;
      if (dx < 0) return (i + 1) % total;
      return (i - 1 + total) % total;
    });
  };

  const goPrev = () =>
    setIndex((i) => (i - 1 + findings.length) % findings.length);
  const goNext = () => setIndex((i) => (i + 1) % findings.length);

  return (
    <section className={styles.carouselSection} aria-label="항목별 상세">
      <header className={styles.carouselHead}>
        <h2 className={styles.carouselTitle}>항목별 상세</h2>
        <span className={styles.carouselCounter}>
          {String(index + 1).padStart(2, '0')} /{' '}
          {String(findings.length).padStart(2, '0')}
        </span>
        <div className={styles.carouselNav}>
          <button
            type="button"
            className={styles.carouselNavBtn}
            onClick={goPrev}
            aria-label="이전 항목"
          >
            ‹
          </button>
          <button
            type="button"
            className={styles.carouselNavBtn}
            onClick={goNext}
            aria-label="다음 항목"
          >
            ›
          </button>
        </div>
      </header>

      <div
        className={styles.carouselStage}
        onPointerDown={onPointerDown}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <FindingCardA
          key={cur.항목 + index}
          item={cur}
          caseId={caseId}
          initialOverride={initialOverrides[cur.항목]}
        />
      </div>

      <CarouselDots
        count={findings.length}
        active={index}
        items={findings}
        onJump={setIndex}
      />
    </section>
  );
}

function FindingCardA({
  item,
  caseId,
  initialOverride,
}: {
  item: EcAnalysisItem;
  caseId: string;
  initialOverride?: string;
}) {
  const tone = toneOf(item.적절성);
  // parseMetaTags 의 metas 중:
  //   - 법령(예: DB_근로기준법) → '법적근거' 줄에 이미 LawHover 가 노출되므로 중복 제거
  //   - 주제 DB(예: DB_임금체불, DB_퇴직금) → '참고 자료' 줄에 MetaHoverChip
  const { text, metas } = useMemo(
    () => parseMetaTags(item.판단이유 || ''),
    [item.판단이유],
  );
  const topicMetas = useMemo(
    () => metas.filter((m) => !isLawDb(m.db)),
    [metas],
  );
  const law = firstLaw(item.법적근거);
  const label = findingLabel(item);
  return (
    <article className={`${styles.findingCardA} ${styles[`findingCardA_${tone}`]}`}>
      <div
        className={`${styles.findingSide} ${styles[`findingSide_${tone}`]}`}
        aria-hidden
      />
      <div className={styles.findingBody}>
        <div className={styles.findingTitleRow}>
          <span className={`${styles.findingChip} ${styles[`findingChip_${tone}`]}`}>
            {label}
          </span>
          <span className={styles.findingName}>{item.항목}</span>
          {item.적용조건 && (
            <span className={styles.findingTag}>{item.적용조건}</span>
          )}
          {item.서면명시의무 && (
            <span className={styles.findingTag} title="서면명시의무">
              {item.서면명시의무}
            </span>
          )}
        </div>
        {text && (
          <div className={styles.findingDesc}>{emphasize(text)}</div>
        )}

        <div className={styles.findingDivider} />

        <div className={styles.findingFactRow}>
          <span className={styles.findingFactLabel}>발견내용</span>
          <span className={styles.findingFactValue}>
            <strong>{(item.발견내용 || '없음').trim() || '없음'}</strong>
          </span>
        </div>
        <div className={styles.findingFactRow}>
          <span className={styles.findingFactLabel}>법적근거</span>
          <span className={styles.findingFactValue}>
            {law ? <LawHover lawName={law} /> : '—'}
          </span>
        </div>
        {topicMetas.length > 0 && (
          <div className={styles.findingFactRow}>
            <span className={styles.findingFactLabel}>참고 자료</span>
            <span className={styles.findingFactValue}>
              <MetaHoverChipsRow metas={topicMetas} />
            </span>
          </div>
        )}

        <SuggestBlock
          tone={tone}
          itemName={item.항목}
          caseId={caseId}
          current={(item.발견내용 || '').trim() || '없음'}
          initialSuggest={
            (initialOverride ?? item.개선권고 ?? '').trim()
          }
          hasOverride={Boolean(initialOverride)}
          suggestLabel={`「${item.항목}」 보완 예시`}
        />
      </div>
    </article>
  );
}

function CarouselDots({
  count,
  active,
  items,
  onJump,
}: {
  count: number;
  active: number;
  items: EcAnalysisItem[];
  onJump: (i: number) => void;
}) {
  return (
    <div className={styles.dots} role="tablist" aria-label="항목 페이지">
      {Array.from({ length: count }).map((_, i) => {
        const tone = toneOf(items[i].적절성);
        const isActive = i === active;
        return (
          <button
            key={i}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-label={`${i + 1}번째 항목 — ${items[i].항목}`}
            onClick={() => onJump(i)}
            className={`${styles.dot} ${isActive ? `${styles.dotActive} ${styles[`dotActive_${tone}`]}` : ''}`}
          />
        );
      })}
    </div>
  );
}

/* ════════════════════════════════════════════════════════
 * SuggestBlock — 현재 / 제안 2단 + 풋터
 * ════════════════════════════════════════════════════════ */

/**
 * SuggestBlock — 제안 표현은 사용자가 자유롭게 편집 가능.
 *
 * - 우측 "제안 표현" 박스는 `<textarea>` 로 사용자가 직접 손볼 수 있다.
 * - "문서에 반영 →" 버튼을 누르면 그 항목명을 키로 store 의 `userOverrides` 에 저장.
 * - Step4 (표준 계약서 생성) 호출 시 analysis.results 의 `개선권고` 를 이 값으로 덮어쓰기.
 *   = LLM 이 표준 계약서 본문을 작성할 때 사용자 표현을 그대로 활용.
 */
function SuggestBlock({
  tone,
  itemName,
  caseId,
  current,
  initialSuggest,
  hasOverride,
  suggestLabel,
}: {
  tone: 'bad' | 'partial' | 'ok';
  itemName: string;
  caseId: string;
  current: string;
  initialSuggest: string;
  hasOverride: boolean;
  suggestLabel: string;
}) {
  const [draft, setDraft] = useState(initialSuggest);
  const [copied, setCopied] = useState(false);
  const [applied, setApplied] = useState(hasOverride);
  // 반영 진행 표시 — 클릭 시 잠깐 스피너 돌고 체크로 전환 (사용자 가시 피드백)
  const [applying, setApplying] = useState(false);
  const applyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // 마지막으로 "문서에 반영" 된 값 — dirty 판정 기준. 원본(initialSuggest)이 아니라
  // 이 값과 비교해야, 사용자가 표현을 직접 수정해 반영한 뒤에도 "✓ 반영됨" 이 뜬다.
  const [appliedValue, setAppliedValue] = useState<string | null>(
    hasOverride ? initialSuggest : null,
  );
  // hasOverride 가 부모 갱신으로 바뀌면 applied 도 sync — 캐러셀에서 항목 이동 시
  // 같은 SuggestBlock 인스턴스가 다른 항목으로 props 만 바뀌는 경우 대응.
  useEffect(() => {
    setApplied(hasOverride);
    setAppliedValue(hasOverride ? initialSuggest : null);
  }, [hasOverride, initialSuggest]);
  // 언마운트(카드 전환) 시 진행 중 타이머 정리 — setState-after-unmount 방지
  useEffect(() => {
    return () => {
      if (applyTimerRef.current) clearTimeout(applyTimerRef.current);
    };
  }, []);
  // 클릭 즉시 사용자에게 보일 토스트 — 풋터 색 변화만으론 안 보이는 케이스 대비.
  const [toast, setToast] = useState<null | { msg: string; tone: 'ok' | 'info' }>(
    null,
  );
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pushToast = (msg: string, tone: 'ok' | 'info' = 'ok') => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setToast({ msg, tone });
    toastTimerRef.current = setTimeout(() => setToast(null), 2400);
  };

  if (!initialSuggest && !hasOverride) return null;

  const handleCopy = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(draft);
      } else {
        // 비-secure 컨텍스트 등 — execCommand 폴백
        const ta = document.createElement('textarea');
        ta.value = draft;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        ta.remove();
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (e) {
      console.warn('clipboard copy failed', e);
      setCopied(true); // 시각 응답이라도 표시
      setTimeout(() => setCopied(false), 1500);
    }
  };

  const handleApply = () => {
    console.log('[SuggestBlock] handleApply fired', { itemName, caseId });
    const value = draft.trim();
    if (!value) {
      pushToast('빈 내용은 반영할 수 없어요', 'info');
      return;
    }
    // store 갱신 — ensureCaseEntry 가 case 없으면 minimal entry 자동 생성하므로
    // 새로고침·hot reload 직후에도 silent fail 안 함.
    const prev = getCase(caseId)?.ec?.userOverrides ?? {};
    const next = { ...prev, [itemName]: value };
    console.log('[SuggestBlock] before updateEc', { prev, next });
    updateEc(caseId, { userOverrides: next });
    // 갱신 검증 — store layer 가 자동 복구하므로 항상 성공해야 함
    const after = getCase(caseId)?.ec?.userOverrides ?? {};
    console.log('[SuggestBlock] after updateEc', { after });
    if (after[itemName] !== value) {
      // 여기까지 오면 storage write 자체가 실패 (QuotaExceeded 등) — 디버그 정보 노출
      console.error(
        '[SuggestBlock] updateEc 후에도 값이 반영 안 됨 — storage write 실패 가능',
        {
          caseId,
          itemName,
          expected: value,
          after: after[itemName],
          allOverrides: after,
        },
      );
      pushToast(
        `저장 실패 — 브라우저 저장공간이 가득 찼거나 차단됐어요. 시크릿모드/다른 브라우저로 시도해 주세요.`,
        'info',
      );
      return;
    }
    // 저장은 즉시 끝났지만, 사용자가 "반영됨"을 눈으로 확인할 수 있게
    // 짧게 스피너를 돌린 뒤 체크로 전환한다.
    setApplying(true);
    if (applyTimerRef.current) clearTimeout(applyTimerRef.current);
    applyTimerRef.current = setTimeout(() => {
      setApplying(false);
      setApplied(true);
      setAppliedValue(value);
      pushToast(`✓ 「${itemName}」 표준 계약서에 반영됨`, 'ok');
    }, 600);
  };

  const handleReset = () => {
    setDraft(initialSuggest);
    const prev = getCase(caseId)?.ec?.userOverrides ?? {};
    const next = { ...prev };
    delete next[itemName];
    updateEc(caseId, { userOverrides: next });
    setApplied(false);
    setAppliedValue(null);
    pushToast('초안으로 되돌렸어요', 'info');
  };

  // 반영 완료 상태 = 반영된 적 있고 현재 draft 가 마지막 반영값과 동일.
  // needsReapply = 반영 후 표현을 또 고쳐서 다시 눌러야 하는 상태.
  const isApplied =
    applied && appliedValue !== null && draft.trim() === appliedValue.trim();
  const needsReapply =
    applied && appliedValue !== null && draft.trim() !== appliedValue.trim();

  return (
    <div className={styles.suggestBlock}>
      {/* 토스트는 body 로 portal — 캐러셀의 transform/overflow 안에 갇혀 안 보이던 문제 해결.
          (transform 된 조상은 position:fixed 의 기준이 되어 화면 밖으로 밀려남) */}
      {toast &&
        typeof document !== 'undefined' &&
        createPortal(
          <div
            className={`${styles.suggestToast} ${styles[`suggestToast_${toast.tone}`]}`}
            role="status"
            aria-live="polite"
          >
            {toast.msg}
          </div>,
          document.body,
        )}
      <div className={styles.suggestHead}>
        <span
          className={`${styles.suggestSparkle} ${styles[`suggestSparkle_${tone}`]}`}
        >
          ✦
        </span>
        <span className={styles.suggestTitle}>이렇게 고쳐보세요</span>
        <span className={styles.suggestLabel}>{suggestLabel}</span>
        <button
          type="button"
          className={styles.suggestCopy}
          onClick={handleCopy}
          aria-label="제안 표현 복사"
        >
          {copied ? '✓ 복사됨' : '📋 복사'}
        </button>
      </div>
      <div className={styles.suggestCompare}>
        <div className={styles.suggestColCurrent}>
          <div className={styles.suggestColHead}>
            <span
              className={`${styles.suggestColDot} ${styles.suggestColDotCurrent}`}
              aria-hidden
            />
            <span className={styles.suggestColLabelCurrent}>현재 표현</span>
          </div>
          <div className={styles.suggestColBodyCurrent}>{current}</div>
        </div>
        <div className={styles.suggestColSuggest}>
          <div className={styles.suggestColHead}>
            <span
              className={`${styles.suggestColDot} ${styles.suggestColDotSuggest}`}
              aria-hidden
            />
            <span className={styles.suggestColLabelSuggest}>
              제안 표현 <span className={styles.suggestColEditable}>(직접 수정 가능)</span>
            </span>
          </div>
          <textarea
            className={styles.suggestColTextarea}
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              if (applied) setApplied(false);
            }}
            rows={Math.min(8, Math.max(3, Math.ceil(draft.length / 32)))}
            placeholder="제안 표현을 자유롭게 수정해 보세요."
            spellCheck={false}
          />
        </div>
      </div>
      {/* 적용 직후 인라인 confirmation — toast 못 봐도 카드 안에서 확실히 인지. */}
      {isApplied && (
        <div
          className={styles.suggestAppliedBanner}
          role="status"
          aria-live="polite"
        >
          <span className={styles.suggestAppliedIcon} aria-hidden>✓</span>
          <div className={styles.suggestAppliedText}>
            <div className={styles.suggestAppliedTitle}>
              <strong>「{itemName}」</strong> 보완 표현이 저장되었습니다.
            </div>
            <div className={styles.suggestAppliedDesc}>
              아래 <strong>“표준 계약서 생성”</strong> 단계에서 이 표현이 본문에 그대로 반영됩니다.
            </div>
          </div>
          <button
            type="button"
            className={styles.suggestAppliedReset}
            onClick={handleReset}
          >
            되돌리기
          </button>
        </div>
      )}
      <div
        className={`${styles.suggestFooter} ${
          isApplied ? styles.suggestFooterApplied : ''
        }`}
      >
        <span className={styles.suggestFooterInfo}>
          {needsReapply ? (
            <>📝 표현이 수정되었어요. 다시 <strong>“문서에 반영”</strong> 을 눌러 갱신해 주세요.</>
          ) : isApplied ? (
            <>✓ <strong>이 항목은 이미 반영됨</strong> — 표현을 더 다듬어도 다시 누르면 갱신돼요.</>
          ) : (
            <>ⓘ 표현을 다듬은 뒤 <strong>“문서에 반영”</strong> 을 누르면 표준 계약서 본문에 사용돼요.</>
          )}
        </span>
        <button
          type="button"
          className={`${styles.suggestFooterCta} ${
            isApplied ? styles.suggestFooterCtaApplied : ''
          }`}
          onClick={handleApply}
          disabled={!draft.trim() || isApplied || applying}
        >
          {applying ? (
            <>
              <span className={styles.suggestSpinner} aria-hidden /> 반영 중…
            </>
          ) : isApplied ? (
            '✓ 반영됨'
          ) : (
            '문서에 반영 →'
          )}
        </button>
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════
 * LawHover — 법령 태그(brandSoft 칩) + 다크 툴팁
 * ════════════════════════════════════════════════════════ */

/**
 * 법조 칩 — 클릭하면 국가법령정보센터의 해당 조문으로 새 탭 이동.
 * (호버 툴팁은 제거 — 사용자 요청대로 클릭 only)
 *
 * 법령+제N조 패턴이 인식되면 anchor, 아니면 plain span (시각만 일치).
 */
function LawHover({ lawName }: { lawName: string }) {
  const cleanedName = useMemo(() => stripMarkdownChars(lawName), [lawName]);

  /**
   * 항상 외부 URL 반환:
   *   1순위 — 법령+제N조 패턴이면 국가법령정보센터의 해당 조문 직접 링크
   *   2순위 — 매칭 실패 시 통합검색 URL (시행령·다른 형식도 사용자가 직접 찾을 수 있게)
   *
   * cleanedName 이 비어있을 때만 null. 그 외엔 항상 클릭 가능.
   */
  const externalUrl = useMemo(() => {
    if (!cleanedName) return null;
    const m = cleanedName.match(/^(.+?(?:법률|법))\s*(.*)$/);
    if (m) {
      const direct = lawArticleUrl({ db: `DB_${m[1]}`, n: m[2].trim() });
      if (direct) return direct;
    }
    // fallback — 국가법령정보센터 통합검색
    return `https://www.law.go.kr/LSW/lsSc.do?menuId=1&subMenuId=15&tabMenuId=81&query=${encodeURIComponent(cleanedName)}`;
  }, [cleanedName]);

  const chipContent = (
    <>
      {cleanedName}
      <span className={styles.lawHoverIcon} aria-hidden>
        ↗
      </span>
    </>
  );

  if (externalUrl) {
    return (
      <a
        className={styles.lawHoverChip}
        href={externalUrl}
        target="_blank"
        rel="noopener noreferrer"
        title="국가법령정보센터에서 보기 — 새 탭"
      >
        {chipContent}
      </a>
    );
  }
  return <span className={styles.lawHoverChip}>{chipContent}</span>;
}

/* ─── MetaHoverChip — 주제 DB 메타 (DB_임금체불 3.1.1 등) 호버 칩 ─── */

function MetaHoverChipsRow({ metas }: { metas: MetaTagInfo[] }) {
  const { loaded } = useTopicCorpus();
  // 같은 내용(여러 주제가 동일 정의를 엮은 경우)이 여러 칩으로 중복되면 하나만 — 중복 표시 방지.
  const unique = useMemo(() => {
    const seen = new Set<string>();
    const out: MetaTagInfo[] = [];
    for (const m of metas) {
      const body = (lookupLawExcerpt(m.db, m.n).body || '').trim();
      const key = body || `${m.db}|${m.n}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(m);
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [metas, loaded]);
  return (
    <span className={styles.metaHoverRow}>
      {unique.map((m, i) => (
        <MetaHoverChip key={`${m.db}-${m.n}-${i}`} meta={m} />
      ))}
    </span>
  );
}

function MetaHoverChip({ meta }: { meta: MetaTagInfo }) {
  const [open, setOpen] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // 코퍼스가 lazy fetch — 적재 완료 시점에 useMemo 재실행 되도록 loaded 를 의존성에.
  const { loaded } = useTopicCorpus();
  const excerpt: LawExcerpt = useMemo(
    () => lookupLawExcerpt(meta.db, meta.n),
    [meta.db, meta.n, loaded],
  );
  const cleanDb = meta.db.replace(/^DB_/, '');
  const label = `${cleanDb} ${meta.n}`.trim();

  const cancelClose = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };
  const show = () => {
    cancelClose();
    setOpen(true);
  };
  const scheduleClose = () => {
    cancelClose();
    timerRef.current = setTimeout(() => setOpen(false), 600);
  };

  return (
    <span
      className={styles.metaHoverWrap}
      onMouseEnter={show}
      onMouseLeave={scheduleClose}
      onFocus={show}
      onBlur={scheduleClose}
      tabIndex={0}
      role="note"
      aria-label={excerpt.title}
    >
      <span className={styles.metaHoverChip}>
        {label}
        <span className={styles.metaHoverIcon} aria-hidden>
          ⓘ
        </span>
      </span>
      {open && (
        <span
          className={styles.lawHoverTooltip}
          role="tooltip"
          onMouseEnter={show}
          onMouseLeave={scheduleClose}
        >
          <span className={styles.lawHoverTooltipTitle}>{excerpt.title}</span>
          <span className={styles.lawHoverTooltipBody}>{excerpt.body}</span>
          {excerpt.penalty && excerpt.penalty !== '—' && (
            <>
              <span className={styles.lawHoverTooltipDivider} />
              <span className={styles.lawHoverTooltipPenalty}>
                <span className={styles.lawHoverTooltipPenaltyLabel}>제재</span>{' '}
                <span className={styles.lawHoverTooltipPenaltyValue}>
                  {excerpt.penalty}
                </span>
              </span>
            </>
          )}
        </span>
      )}
    </span>
  );
}

/* ════════════════════════════════════════════════════════
 * 메타 태그 파서 + 본문 강조
 * ════════════════════════════════════════════════════════ */

const EMPHASIZE_PATTERN = new RegExp(
  [
    '필수\\s*기재(?:사항)?',
    '서면\\s*명시(?:의무)?',
    '서면\\s*교부(?:\\s*의무)?',
    '미기재',
    '판독불가',
    '누락(?:되어|되었|된)?\\s*있?',
    '보완(?:이)?\\s*필요(?:합니다|함)?',
    '위반\\s*가능성(?:이\\s*있습니다)?',
    '위반(?:\\s*우려|\\s*소지)?',
    '검토(?:가|를)?\\s*필요(?:합니다|해\\s*보|해|함)?',
    '부적절',
    '적정',
    '적절',
    '명백히',
    '불명확',
    '명확히',
    '사용자\\s*정보',
    '근로자\\s*정보',
    '근로개시일',
    '근로계약기간',
    '근무\\s*장소',
    '업무\\s*내용',
    '소정근로시간',
    '시업\\s*시각',
    '종업\\s*시각',
    '휴게시간',
    '근무일',
    '주휴일',
    '연차\\s*유급\\s*휴가',
    '연차수당',
    '임금\\s*총액',
    '임금총액',
    '기본급',
    '제수당',
    '각종\\s*수당',
    '상여금',
    '성과금',
    '임금\\s*구성항목',
    '임금\\s*계산방법',
    '임금\\s*지급(?:일|방법|시기)',
    '연장근로(?:수당|시간)?',
    '야간근로(?:수당|시간)?',
    '휴일근로(?:수당|시간)?',
    '퇴직금',
    '퇴직급여',
    '4\\s*대\\s*보험',
    '사회보험',
    '수습기간',
    '근로계약서\\s*교부',
    '계약서\\s*작성일',
    '당사자\\s*서명(?:날인)?',
    '근로일별\\s*근로시간',
    '근로일\\s*및\\s*근로일별\\s*근로시간',
    '일당',
    '체류자격',
    '숙식\\s*제공(?:\\s*여부)?',
    '연령증명서',
    '친권자\\s*동의서',
    '근로시간\\s*제한',
    '야간[·\\s]*휴일근로\\s*제한',
    '5인\\s*이상',
    '5인\\s*미만',
    '정규직',
    '기간제(?:\\s*근로자)?',
    '단시간(?:\\s*근로자)?',
    '일용직',
    '연소자',
    '외국인(?:\\s*\\(농축어업\\))?',
    '근로기준법\\s*제\\d+조(?:\\s*제\\d+항)?(?:\\s*제\\d+호)?',
    '기간제\\s*및\\s*단시간근로자\\s*보호\\s*등에\\s*관한\\s*법률\\s*제\\d+조',
    '최저임금법\\s*제\\d+조(?:\\s*제\\d+항)?',
    '근로자퇴직급여\\s*보장법\\s*제\\d+조',
    '국민연금법',
    '국민건강보험법',
    '고용보험법',
    '산업재해보상보험법',
    '외국인근로자의\\s*고용\\s*등에\\s*관한\\s*법률',
    '\\d+(?:,\\d{3})+\\s*원',
    '\\d{1,4}\\s*년\\s*\\d{1,2}\\s*월\\s*\\d{1,2}\\s*일',
    '\\d{1,2}\\s*시\\s*\\d{1,2}\\s*분',
    '\\d{1,2}\\s*시간',
    '\\d{1,2}\\s*일',
    '\\d{1,2}\\s*개월',
  ]
    .map((p) => `(?:${p})`)
    .join('|'),
  'g',
);

function emphasize(input: string): ReactNode[] {
  if (!input) return [];
  const out: ReactNode[] = [];
  let lastIndex = 0;
  let m: RegExpExecArray | null;
  const re = new RegExp(EMPHASIZE_PATTERN.source, EMPHASIZE_PATTERN.flags);
  while ((m = re.exec(input)) !== null) {
    if (m.index > lastIndex) {
      out.push(
        <Fragment key={`t-${lastIndex}`}>
          {input.slice(lastIndex, m.index)}
        </Fragment>,
      );
    }
    out.push(<strong key={`s-${m.index}`}>{m[0]}</strong>);
    lastIndex = m.index + m[0].length;
  }
  if (lastIndex < input.length) {
    out.push(
      <Fragment key={`t-${lastIndex}`}>{input.slice(lastIndex)}</Fragment>,
    );
  }
  return out;
}

/**
 * 마크다운 강조 부호(`**`·`*`·`__`·`_`) 제거 — LawHover 칩·URL 에 raw 가 새 나가지 않게.
 */
function stripMarkdownChars(s: string): string {
  return s.replace(/\*+|_+/g, '').replace(/\s+/g, ' ').trim();
}
