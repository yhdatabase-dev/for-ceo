'use client';

import { useCallback, useEffect, useMemo, useState, use } from 'react';
import { useRouter } from 'next/navigation';

import Button from '@/components/ui/Button';
import DistributionCard from '@/features/wr/components/DistributionCard';
import FilterBar, {
  type RiskFilter,
  type SortMode,
} from '@/features/wr/components/FilterBar';
import FindingCarousel from '@/features/wr/components/FindingCarousel';
import OptionalSection from '@/features/wr/components/OptionalSection';
import PriorityCard from '@/features/wr/components/PriorityCard';
import ResultHeader from '@/features/wr/components/ResultHeader';
import VerdictCard from '@/features/wr/components/VerdictCard';
import PrintLayout from '@/features/wr/components/print/PrintLayout';
import SiteHeader from '@/components/layout/SiteHeader';
import MobileReviewApp, {
  useIsMobileViewport,
  type MobileFinding,
} from '@/components/review/mobile/MobileReviewApp';

import { SAMPLE_RESULT } from '@/data/sample';
import { getCase, setCaseError } from '@/features/history/store';
import { updateWr } from '@/features/wr/store';
import { postWrGenerate } from '@/features/wr/api';
import { ApiCallError } from '@/lib/api/client';
import { RISK_ORDER } from '@/styles/tokens';
import type { ReviewResult } from '@/types/review';

import styles from './page.module.css';
import { routes } from '@/lib/routes';

/** 데모(/review/demo) 전용 샘플 원문 — '원문 보기·표준양식 만들기' 시연용. */
const DEMO_WR_TEXT = [
  '제24조(연장근로) 회사는 업무상 필요한 경우 근로자대표와 서면 합의에 따라 1주 16시간을 한도로 연장근로를 명할 수 있다.',
  '제38조(연차유급휴가) 회사는 1년간 80% 이상 출근한 근로자에게 15일의 유급휴가를 준다.',
  '제45조(출산전후휴가) 회사는 임신 중의 여성에게 출산 전후 90일의 휴가를 준다.',
  '제62조(징계절차) 회사는 징계 시 해당 근로자에게 소명할 기회를 줄 수 있다.',
  '제68조(정년) 근로자의 정년은 회사가 정하는 바에 따른다.',
].join('\n');

/**
 * 결과 대시보드 페이지.
 *
 * 시안 `screens-result.jsx` 의 사이드바 + 메인 2단 레이아웃을 이식.
 * 백엔드 연동 전이라 `SAMPLE_RESULT` mock 을 그대로 사용한다.
 * 추후 `GET /api/review/{id}` 호출 결과로 교체.
 */
export default function ReviewResultPage(
  props: {
    params: Promise<{ caseUid: string }>;
  }
) {
  const params = use(props.params);
  const router = useRouter();

  // store 에서 실제 결과 로드. demo 또는 결과 없으면 SAMPLE_RESULT fallback.
  const [result, setResult] = useState<ReviewResult>(SAMPLE_RESULT);
  // case entry — 수정본 생성 와이어링(원문·userOverrides)에 사용.
  const [entry, setEntry] = useState<ReturnType<typeof getCase>>(null);

  useEffect(() => {
    if (params.caseUid === 'demo') return; // demo 는 항상 mock 사용
    const e = getCase(params.caseUid);
    if (!e) return;
    setEntry(e);
    // 근로계약서 풀 이식 — phase 에 따라 분기.
    if (e.documentType === 'employment-contract' || e.ec) {
      const phase = e.ec?.phase;
      if (phase === 'review' || phase === 'extracting' || phase === 'structuring') {
        router.replace(routes.ecContract(params.caseUid));
      } else if (phase === 'contract' && e.ec?.generatedContract) {
        router.replace(routes.ecPreview(params.caseUid));
      } else {
        router.replace(routes.ecReview(params.caseUid));
      }
      return;
    }
    // 취업규칙 (기존 흐름)
    if (e.status === 'done' && e.result?.doc === 'work-rules') {
      setResult(e.result.data);
    }
  }, [params.caseUid, router]);

  const { summary, findings } = result;

  const [filter, setFilter] = useState<RiskFilter>('all');
  const [sort, setSort] = useState<SortMode>('risk');

  const filtered = useMemo(() => {
    let list = filter === 'all' ? findings : findings.filter((f) => f.risk === filter);
    if (sort === 'article') {
      list = [...list].sort((a, b) => a.article.localeCompare(b.article, 'ko'));
    } else {
      const order = new Map(RISK_ORDER.map((k, i) => [k, i]));
      list = [...list].sort(
        (a, b) => (order.get(a.risk) ?? 99) - (order.get(b.risk) ?? 99),
      );
    }
    return list;
  }, [findings, filter, sort]);

  const skippedCount = summary.counts.skipped ?? 0;

  const openFinding = (findingId: string) => {
    router.push(routes.wrFinding(params.caseUid, findingId));
  };

  // 인쇄 / PDF 다운로드 — 동일하게 window.print() 호출
  const handlePrint = useCallback(() => {
    if (typeof window === 'undefined') return;
    window.print();
  }, []);

  // ─── 모바일 검토앱 (≤720px) — 공용 MobileReviewApp 으로 분기 ───
  const isMobile = useIsMobileViewport();
  // 문제 항목만 (적정 OK·추출실패 ERROR 제외).
  // tone — bucket 의미와 동일: 강행규정 미준수(VIOLATION·MISSING)=bad,
  // 임의규정·매칭모호(WARN·AMBIGUOUS)=warn.
  const mobileFindings = useMemo<MobileFinding[]>(
    () =>
      findings
        .filter(
          (f) =>
            f.status === 'VIOLATION' ||
            f.status === 'MISSING' ||
            f.status === 'AMBIGUOUS' ||
            f.status === 'WARN',
        )
        .map((f) => {
          // 벌칙 — 누락이면 미기재(omission) 쪽, 그 외엔 내용위반(violation) 쪽 우선.
          const pen = f.penalty
            ? f.status === 'MISSING'
              ? f.penalty.omission[0] ?? f.penalty.violation[0]
              : f.penalty.violation[0] ?? f.penalty.omission[0]
            : undefined;
          // 취업규칙은 부적절/보완필요 대신 기존 5-bucket 표현(누락·위반·주의·검토필요) 유지.
          const statusLabel =
            f.status === 'MISSING'
              ? '누락'
              : f.status === 'VIOLATION'
                ? '위반'
                : f.status === 'WARN'
                  ? '주의'
                  : '검토필요';
          return {
            key: f.id,
            tone:
              f.status === 'VIOLATION' || f.status === 'MISSING'
                ? ('bad' as const)
                : ('warn' as const),
            statusLabel,
            name: `${f.article} ${f.articleTitle}`.trim() || f.title,
            reason: f.title,
            why: f.reason,
            law: f.laws?.[0]?.name,
            pen,
            now: f.quote || '(본문에 규정 없음)',
            fix: f.suggested,
          };
        }),
    [findings],
  );
  // 종합 판정 — verdictKey(가장 강한 버킷) 로 톤, 분포 카운트로 한줄 요약.
  const mobileVerdict = useMemo(() => {
    const c = summary.counts;
    const tone: 'bad' | 'warn' | 'ok' =
      summary.verdictKey === 'missing' || summary.verdictKey === 'violation'
        ? 'bad'
        : summary.verdictKey === 'ok'
          ? 'ok'
          : 'warn';
    const severeParts: string[] = [];
    if (c.missing) severeParts.push(`누락 ${c.missing}건`);
    if (c.violation) severeParts.push(`위반 ${c.violation}건`);
    const extraParts: string[] = [];
    if (c.warn) extraParts.push(`주의 ${c.warn}건`);
    if (c.ambiguous) extraParts.push(`검토필요 ${c.ambiguous}건`);
    let text: string;
    if (severeParts.length === 0 && extraParts.length === 0) {
      text = '법정 기준에 모두 부합합니다. 추가 시정 없이 운영 가능합니다.';
    } else if (severeParts.length === 0) {
      text = `강행규정 위반은 없으나, ${extraParts.join(', ')}의 점검 권장 항목이 있습니다.`;
    } else {
      text = `${severeParts.join(', ')}의 강행규정 미준수가 발견되어 시정이 필요합니다.`;
      if (extraParts.length > 0) {
        text += ` 이외 ${extraParts.join(', ')}도 함께 점검해 주세요.`;
      }
    }
    return { word: summary.verdict, tone, summary: text };
  }, [summary]);

  // ─── 모바일 수정본 영속화 — 담은 항목만 userOverrides 로 저장 (EC 와 동일 패턴) ───
  const wrOverrides = entry?.wr?.userOverrides;
  const mobileInitialDrafts = useMemo(
    () => ({ ...(wrOverrides ?? {}) }),
    [wrOverrides],
  );
  const mobileInitialAdded = useMemo(() => {
    const m: Record<string, boolean> = {};
    for (const k of Object.keys(wrOverrides ?? {})) m[k] = true;
    return m;
  }, [wrOverrides]);
  const handleMobilePersist = useCallback(
    (drafts: Record<string, string>, added: Record<string, boolean>) => {
      const ov: Record<string, string> = {};
      for (const f of mobileFindings) {
        if (added[f.key]) ov[f.key] = drafts[f.key] ?? f.fix;
      }
      updateWr(params.caseUid, { userOverrides: ov });
    },
    [mobileFindings, params.caseUid],
  );

  // ─── 데스크톱 신구대조표 담기 — 항목별 담기 + 제안 일괄 담기 → wr.userOverrides 영속 ───
  // (모바일과 동일 저장소를 쓰며, 담은 항목만 신구대조표 행으로 나온다.)
  const [added, setAdded] = useState<Record<string, boolean>>({});
  useEffect(() => {
    const ov = entry?.wr?.userOverrides;
    if (ov && Object.keys(ov).length) {
      const m: Record<string, boolean> = {};
      for (const k of Object.keys(ov)) m[k] = true;
      setAdded(m);
    }
  }, [entry]);

  const suggestedById = useMemo(
    () =>
      Object.fromEntries(
        findings.map((f) => [f.id, (f.suggested || f.standard || '').trim()]),
      ),
    [findings],
  );

  const persistAdded = useCallback(
    (next: Record<string, boolean>) => {
      const existing = getCase(params.caseUid)?.wr?.userOverrides ?? {};
      const ov: Record<string, string> = {};
      for (const id of Object.keys(next)) {
        if (next[id]) ov[id] = existing[id] ?? suggestedById[id] ?? '';
      }
      updateWr(params.caseUid, { userOverrides: ov });
    },
    [params.caseUid, suggestedById],
  );

  const toggleAdd = useCallback(
    (id: string) => {
      setAdded((prev) => {
        const next = { ...prev };
        if (next[id]) delete next[id];
        else next[id] = true;
        persistAdded(next);
        return next;
      });
    },
    [persistAdded],
  );

  const addAllFlagged = useCallback(() => {
    setAdded(() => {
      const next: Record<string, boolean> = {};
      for (const f of mobileFindings) next[f.key] = true;
      persistAdded(next);
      return next;
    });
  }, [mobileFindings, persistAdded]);

  const addedCount = useMemo(
    () => Object.values(added).filter(Boolean).length,
    [added],
  );

  // 수정본 생성 — 원문은 그대로, 사용자가 담은 수정 항목만 반영해 전문 출력.
  // 원문 텍스트(wr.extractedText)가 있는 케이스에서만 노출 (레거시 케이스 보호).
  // 데모(/review/demo)는 원문이 없어 '원문 보기·표준양식 만들기'가 숨겨지므로,
  // 목업이 완전하게 보이도록 샘플 원문을 채워 두 기능을 모두 노출한다.
  const isDemo = params.caseUid === 'demo';
  const wrExtractedText = entry?.wr?.extractedText ?? (isDemo ? DEMO_WR_TEXT : undefined);
  const handleGenerate = () => {
    // 담은 항목은 onPersist 가 store 의 userOverrides 로 즉시 영속화 — 호출
    // 시점의 최신 값을 store 에서 읽는다 (EC handleGenerate 와 동일 패턴).
    const text = getCase(params.caseUid)?.wr?.extractedText ?? (isDemo ? DEMO_WR_TEXT : '');
    if (!text.trim()) {
      setCaseError(params.caseUid, '원문 텍스트가 없어 수정본을 만들 수 없어요.');
      return;
    }
    const overrides = getCase(params.caseUid)?.wr?.userOverrides ?? {};
    const corrections = mobileFindings
      .filter((f) => overrides[f.key] !== undefined)
      .map((f) => ({ name: f.name, now: f.now, fix: overrides[f.key] ?? f.fix }));

    updateWr(params.caseUid, { phase: 'generating', errorMessage: undefined });
    router.push(routes.wrLoading(params.caseUid));

    postWrGenerate(text, corrections)
      .then((out) => {
        updateWr(params.caseUid, { phase: 'contract', generatedText: out.revised_text });
      })
      .catch((err) => {
        const msg =
          err instanceof ApiCallError
            ? err.detail
            : err instanceof Error
              ? err.message
              : String(err);
        setCaseError(params.caseUid, msg);
      });
  };

  // ─── 모바일 — 결과 단계 전용 풀스크린 앱 (데스크톱 레이아웃 미렌더) ───
  // wr.extractedText 가 있으면(확인 단계 거친 케이스) 원문 화면·수정본 생성 활성.
  if (isMobile) {
    return (
      <MobileReviewApp
        docLabel="취업규칙"
        filename={summary.fileName}
        verdict={mobileVerdict}
        findings={mobileFindings}
        okCount={summary.counts.ok ?? 0}
        extractedText={wrExtractedText}
        initialDrafts={mobileInitialDrafts}
        initialAdded={mobileInitialAdded}
        onPersist={handleMobilePersist}
        onBack={() => router.push('/')}
        onGenerate={wrExtractedText ? handleGenerate : undefined}
        generateLabel="수정본 취업규칙 만들기"
      />
    );
  }

  return (
    <>
      {/* ── 화면용 ── */}
      <div className={`${styles.page} ${styles.screenOnly}`}>
        <SiteHeader />
        <ResultHeader summary={summary} onPrint={handlePrint} />

        {mobileFindings.length > 0 && (
          <div className={`${styles.cmpCta} noPrint`}>
            <div className={styles.cmpCtaText}>
              <strong>수정안을 담아 신구대조표를 만드세요</strong>
              <span>
                항목마다 <b>담기</b>를 누르거나 <b>제안 일괄 담기</b>로 한 번에 담은 뒤,
                담은 항목으로 신구대조표(개정 전·후)를 만들고 Word 로 내려받을 수 있어요.
                {addedCount > 0 && (
                  <>
                    {' · '}
                    <strong className={styles.cmpCount}>현재 {addedCount}건 담음</strong>
                  </>
                )}
              </span>
            </div>
            <div className={styles.cmpCtaBtns}>
              <Button variant="secondary" size="md" onClick={addAllFlagged}>
                ✨ 제안 일괄 담기
              </Button>
              <Button
                variant="primary"
                size="md"
                onClick={() => router.push(routes.wrComparison(params.caseUid))}
              >
                신구대조표 만들기{addedCount > 0 ? ` (${addedCount})` : ''}
              </Button>
            </div>
          </div>
        )}

        <div className={styles.layout}>
          <aside className={styles.sidebar}>
            <VerdictCard summary={summary} />
            <DistributionCard summary={summary} />
            <PriorityCard items={summary.topPriority} onOpenFinding={openFinding} />
          </aside>

          <main className={styles.main}>
            <FilterBar
              counts={summary.counts}
              filter={filter}
              onFilterChange={setFilter}
              sort={sort}
              onSortChange={setSort}
            />
            <FindingCarousel
              findings={filtered}
              onOpen={openFinding}
              addedMap={added}
              onToggleAdd={toggleAdd}
            />
            <OptionalSection count={skippedCount} />
          </main>
        </div>
      </div>

      {/* ── 인쇄용 (화면에서는 숨김) ── */}
      <PrintLayout summary={summary} findings={findings} />

    </>
  );
}
