'use client';

import { useCallback, useEffect, useMemo, useState, use } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

import { getCase, setCaseError, updateSc } from '@/lib/reviewStore';
import { postScGenerate } from '@/lib/api/sc';
import type { ScAnalysisFinding, ScAnalysisResult } from '@/lib/api/sc';
import { ApiCallError } from '@/lib/api/client';
import ChatPanel from '@/components/review/ChatPanel';
import MobileReviewApp, {
  useIsMobileViewport,
  type MobileFinding,
} from '@/components/review/mobile/MobileReviewApp';

import styles from '../ec/page.module.css';

/**
 * 노무제공자 계약서 — 결과 페이지 (Phase 17).
 *
 * `/review/[id]/sc` — sc.analysisResult 가 있으면 16 슬롯 검토 결과를 렌더.
 * EC 와 결과 스키마가 유사하지만 SC 는 단일 트랙이라 카드형 리스트 1단 레이아웃.
 */

const STATUS_STYLE: Record<
  ScAnalysisFinding['적절성'],
  { bg: string; border: string; text: string; label: string }
> = {
  적절: { bg: '#dcfce7', border: '#22c55e', text: '#14532d', label: '✅ 적절' },
  보완필요: { bg: '#fef9c3', border: '#facc15', text: '#854d0e', label: '⚠️ 보완필요' },
  부적절: { bg: '#fee2e2', border: '#ef4444', text: '#7f1d1d', label: '🚨 부적절' },
};

const SEV_STYLE: Record<
  ScAnalysisFinding['심각도'],
  { bg: string; text: string }
> = {
  HIGH: { bg: '#fee2e2', text: '#991b1b' },
  MEDIUM: { bg: '#fef9c3', text: '#854d0e' },
  LOW: { bg: '#e0f2fe', text: '#0c4a6e' },
};

export default function ScResultPage(props: { params: Promise<{ id: string }> }) {
  const params = use(props.params);
  const router = useRouter();
  const caseId = params.id;
  const [mounted, setMounted] = useState(false);
  const [entry, setEntry] = useState<ReturnType<typeof getCase>>(null);

  useEffect(() => {
    setMounted(true);
    setEntry(getCase(caseId));
  }, [caseId]);

  const result: ScAnalysisResult | undefined = entry?.sc?.analysisResult;
  const workerSubtype = entry?.sc?.workerSubtype ?? '';
  const businessSize = entry?.sc?.businessSize ?? '';

  // 적절성 분포 집계
  const stats = useMemo(() => {
    if (!result?.results) return { 적절: 0, 보완필요: 0, 부적절: 0 };
    const out = { 적절: 0, 보완필요: 0, 부적절: 0 };
    for (const r of result.results) {
      if (r.적절성 in out) out[r.적절성] += 1;
    }
    return out;
  }, [result]);

  // ─── 모바일 검토앱 (≤720px) — 공용 MobileReviewApp 으로 분기 ───
  // 훅 순서 고정: 조기 return 보다 위에서 항상 호출.
  const isMobile = useIsMobileViewport();
  const mobileFindings = useMemo<MobileFinding[]>(() => {
    const rs = result?.results ?? [];
    return rs
      .filter((r) => r.적절성 !== '적절')
      .map((r) => ({
        key: r.슬롯ID || r.항목,
        tone: r.적절성 === '부적절' ? ('bad' as const) : ('warn' as const),
        name: r.항목,
        reason: `${(r.발견내용 || '').trim().slice(0, 38) || '미기재'} · ${r.적절성}`,
        why: (r.판단이유 || '').replace(/<meta[^>]*\/>/g, '').trim(),
        law: r.법적근거 || undefined,
        pen: undefined,
        now: r.발견내용 || '(기재 없음)',
        fix: r.개선권고 || '',
      }));
  }, [result]);

  // ─── 모바일 수정본 영속화 — 담은 항목만 userOverrides 로 저장 (EC 와 동일 패턴) ───
  const scOverrides = entry?.sc?.userOverrides;
  const mobileInitialDrafts = useMemo(
    () => ({ ...(scOverrides ?? {}) }),
    [scOverrides],
  );
  const mobileInitialAdded = useMemo(() => {
    const m: Record<string, boolean> = {};
    for (const k of Object.keys(scOverrides ?? {})) m[k] = true;
    return m;
  }, [scOverrides]);
  const handleMobilePersist = useCallback(
    (drafts: Record<string, string>, added: Record<string, boolean>) => {
      const ov: Record<string, string> = {};
      for (const f of mobileFindings) {
        if (added[f.key]) ov[f.key] = drafts[f.key] ?? f.fix;
      }
      updateSc(caseId, { userOverrides: ov });
    },
    [mobileFindings, caseId],
  );

  if (!mounted) return <main className={styles.page} aria-hidden />;

  if (!result) {
    return (
      <main className={styles.page}>
        <div className={styles.layout}>
          <div className={styles.notFound}>
            <h1>분석 결과를 찾을 수 없습니다</h1>
            <p>
              <Link href="/">← 새로 검토 시작하기</Link>
            </p>
          </div>
        </div>
      </main>
    );
  }

  // 수정본 생성 — 원문은 그대로, 사용자가 담은 수정 항목만 반영해 전문 출력.
  const handleGenerate = () => {
    // 담은 항목은 onPersist 가 store 의 userOverrides 로 즉시 영속화 — 호출
    // 시점의 최신 값을 store 에서 읽는다 (EC handleGenerate 와 동일 패턴).
    const overrides = getCase(caseId)?.sc?.userOverrides ?? {};
    const corrections = mobileFindings
      .filter((f) => overrides[f.key] !== undefined)
      .map((f) => ({ name: f.name, now: f.now, fix: overrides[f.key] ?? f.fix }));

    updateSc(caseId, { phase: 'generating', errorMessage: undefined });
    router.push(`/review/${caseId}/loading`);

    postScGenerate(entry?.sc?.extractedText ?? '', corrections)
      .then((out) => {
        updateSc(caseId, { phase: 'contract', generatedText: out.revised_text });
      })
      .catch((err) => {
        const msg =
          err instanceof ApiCallError
            ? err.detail
            : err instanceof Error
              ? err.message
              : String(err);
        setCaseError(caseId, msg);
        updateSc(caseId, { phase: 'result', errorMessage: msg });
      });
  };

  // ─── 모바일 — 결과 단계 전용 풀스크린 앱 (데스크톱 레이아웃 미렌더) ───
  if (isMobile) {
    const overallStatus = (result.overallStatus || '').trim();
    const mobileTone: 'bad' | 'warn' | 'ok' =
      overallStatus === '위험' ? 'bad' : overallStatus === '적정' ? 'ok' : 'warn';
    return (
      <MobileReviewApp
        docLabel="노무제공자 계약서"
        filename={entry?.originalFilename || '노무제공자 계약서'}
        verdict={{
          word: overallStatus || '보완 필요',
          tone: mobileTone,
          summary: result.overallOpinion || '',
        }}
        findings={mobileFindings}
        okCount={stats.적절}
        extractedText={entry?.sc?.extractedText}
        imageUrl={entry?.originalKind === 'image' ? entry?.originalUrl : undefined}
        initialDrafts={mobileInitialDrafts}
        initialAdded={mobileInitialAdded}
        onPersist={handleMobilePersist}
        onBack={() => router.push('/')}
        onGenerate={handleGenerate}
        generateLabel="수정본 계약서 만들기"
      />
    );
  }

  return (
    <main className={styles.page}>
      <div className={styles.layout} style={{ maxWidth: 1000, margin: '0 auto' }}>
        <div className={styles.head}>
          <span className={styles.docBadge}>📋 노무제공자 계약서 · 검토 결과</span>
        </div>
        <h1 className={styles.title}>노무제공자 계약서 검토 결과</h1>

        {/* 종합 카드 */}
        <section
          style={{
            margin: '16px 0',
            padding: 18,
            background:
              result.overallStatus === '위험'
                ? '#fef2f2'
                : result.overallStatus === '보완필요'
                  ? '#fffbeb'
                  : '#f0fdf4',
            border: `1px solid ${
              result.overallStatus === '위험'
                ? '#ef4444'
                : result.overallStatus === '보완필요'
                  ? '#f59e0b'
                  : '#22c55e'
            }`,
            borderRadius: 12,
          }}
        >
          <div
            style={{
              display: 'flex',
              gap: 14,
              alignItems: 'center',
              flexWrap: 'wrap',
            }}
          >
            <span
              style={{
                fontSize: 11,
                fontWeight: 700,
                padding: '4px 10px',
                background: 'var(--color-brand)',
                color: '#fff',
                borderRadius: 999,
              }}
            >
              위험도 {result.riskLevel}
            </span>
            <span style={{ fontSize: 18, fontWeight: 700 }}>{result.overallStatus}</span>
            {workerSubtype && (
              <span style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
                · 직종: <b>{workerSubtype}</b>
              </span>
            )}
            {businessSize && (
              <span style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
                · 규모: <b>{businessSize}</b>
              </span>
            )}
          </div>
          <p style={{ fontSize: 14, lineHeight: 1.65, margin: '10px 0 0' }}>
            {result.overallOpinion}
          </p>
        </section>

        {/* 분포 KPI */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 8,
            marginBottom: 18,
          }}
        >
          {(['적절', '보완필요', '부적절'] as const).map((k) => {
            const s = STATUS_STYLE[k];
            return (
              <div
                key={k}
                style={{
                  background: s.bg,
                  border: `1px solid ${s.border}`,
                  borderRadius: 10,
                  padding: '10px 12px',
                  textAlign: 'center',
                }}
              >
                <div style={{ fontSize: 11, fontWeight: 700, color: s.text }}>
                  {s.label}
                </div>
                <div
                  style={{
                    fontSize: 22,
                    fontWeight: 700,
                    color: s.text,
                    marginTop: 2,
                  }}
                >
                  {stats[k]}
                </div>
              </div>
            );
          })}
        </div>

        {/* 슬롯별 카드 리스트 */}
        <section>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 10 }}>
            16 슬롯 검토 ({result.results.length}건)
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {result.results.map((r, idx) => {
              const st = STATUS_STYLE[r.적절성] ?? STATUS_STYLE['보완필요'];
              const sv = SEV_STYLE[r.심각도] ?? SEV_STYLE.MEDIUM;
              return (
                <article
                  key={r.슬롯ID || idx}
                  style={{
                    background: '#fff',
                    border: `1px solid ${st.border}`,
                    borderRadius: 12,
                    padding: 14,
                  }}
                >
                  <header
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      flexWrap: 'wrap',
                      marginBottom: 8,
                    }}
                  >
                    <span
                      style={{
                        fontSize: 11,
                        fontWeight: 700,
                        padding: '3px 9px',
                        background: st.bg,
                        color: st.text,
                        borderRadius: 999,
                      }}
                    >
                      {st.label}
                    </span>
                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 700,
                        padding: '2px 8px',
                        background: sv.bg,
                        color: sv.text,
                        borderRadius: 999,
                      }}
                    >
                      {r.심각도}
                    </span>
                    <span
                      style={{
                        fontSize: 10.5,
                        color: 'var(--color-text-muted)',
                        fontFamily: 'D2Coding,ui-monospace,monospace',
                      }}
                    >
                      {r.슬롯ID}
                    </span>
                    <span style={{ fontSize: 14, fontWeight: 700, marginLeft: 'auto' }}>
                      {r.항목}
                    </span>
                  </header>
                  <div style={{ display: 'grid', gap: 6, fontSize: 13, lineHeight: 1.65 }}>
                    {r.발견내용 && (
                      <div>
                        <b>📌 발견:</b> {r.발견내용}
                      </div>
                    )}
                    {r.판단이유 && (
                      <div>
                        <b>🧠 판단:</b> {r.판단이유}
                      </div>
                    )}
                    {r.법적근거 && (
                      <div style={{ color: 'var(--color-text-muted)', fontSize: 12 }}>
                        <b>⚖️ 근거:</b> {r.법적근거}
                      </div>
                    )}
                    {r.개선권고 && (
                      <div
                        style={{
                          marginTop: 6,
                          padding: '8px 10px',
                          background: '#e0f2fe',
                          borderLeft: '3px solid #0ea5e9',
                          borderRadius: 6,
                          fontSize: 12.5,
                        }}
                      >
                        <b>💡 개선:</b> {r.개선권고}
                      </div>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        </section>

        {/* 최종 권고 */}
        {result.finalRecommendations && (
          <section
            style={{
              marginTop: 22,
              padding: 16,
              background: 'var(--color-brand-soft)',
              border: '1px solid var(--color-brand)',
              borderRadius: 12,
            }}
          >
            <h2 style={{ fontSize: 15, fontWeight: 700, margin: '0 0 8px' }}>
              📝 가장 시급한 시정 권고
            </h2>
            <p style={{ fontSize: 13.5, lineHeight: 1.7, margin: 0 }}>
              {result.finalRecommendations}
            </p>
          </section>
        )}

        {/* 가이드 안내 */}
        <section
          style={{
            marginTop: 22,
            padding: 14,
            background: '#fef9c3',
            border: '1px dashed #facc15',
            borderRadius: 10,
            fontSize: 12.5,
            lineHeight: 1.7,
          }}
        >
          💡 표준 노무제공계약서 양식은 <Link href="/guide" style={{ fontWeight: 700 }}>
          꿀팁 가이드 → 서식</Link>에서 고용노동부 자료실 외부 링크로 안내합니다.
          본 결과는 자율점검 보조 자료로, 사업장 노무사 검토 후 확정하세요.
        </section>

        <div style={{ marginTop: 22, display: 'flex', gap: 10 }}>
          <Link href="/" className={styles.btnSecondary}>
            새 검토 시작
          </Link>
          <Link href="/history" className={styles.btnSecondary}>
            내 검토 이력
          </Link>
        </div>
      </div>

      {/* 우하단 floating 챗봇 — SFR-001 (공용) */}
      <div className="noPrint">
        <ChatPanel
          analysis={(result as unknown as Record<string, unknown>) ?? null}
          docLabel="노무제공자 계약서"
          quickPrompts={[
            '산재보험은 누가 부담하나요?',
            '근로자성이 인정되면 어떻게 되나요?',
            '계약 해지 통지 기한은 얼마예요?',
            '특고 직종 16개가 뭔가요?',
          ]}
        />
      </div>
    </main>
  );
}
