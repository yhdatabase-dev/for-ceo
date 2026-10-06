'use client';

import { useEffect, useMemo, useState, use } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

import ClassifyConfirm from '@/components/review/ClassifyConfirm';
import EditableStructureTable from '@/components/review/EditableStructureTable';
import MobileOcrConfirm from '@/components/review/mobile/MobileOcrConfirm';
import { useIsMobileViewport } from '@/components/review/mobile/MobileReviewApp';
import { postEcAnalyze, postEcStructure } from '@/lib/api/ec';
import { ApiCallError } from '@/lib/api/client';
import type { EcStructuredData } from '@/lib/api/types';
import { getCase, setCaseError, updateEc } from '@/lib/reviewStore';

import styles from './page.module.css';

/**
 * Step2 — OCR 결과 검토·수정 페이지 (풀 이식).
 *
 * 좌: 원본 이미지 (또는 추출 텍스트 fallback)
 * 우: EditableStructureTable (8섹션 dict 사용자 수정)
 * 하단: "분석 시작" → POST /api/cgr/ec/analyses → 결과 페이지로 이동.
 */
export default function EcReviewPage(props: { params: Promise<{ id: string }> }) {
  const params = use(props.params);
  const router = useRouter();
  const caseId = params.id;

  // SSR / client mount 간 hydration 일관성 — store 는 mount 후에만.
  const [mounted, setMounted] = useState(false);
  const [initialEntry, setInitialEntry] =
    useState<ReturnType<typeof getCase>>(null);
  const [structured, setStructured] = useState<EcStructuredData | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // AI 1차 분류 확인 — 사용자가 확정한 근로자 유형 (ClassifyConfirm controlled value).
  // null = 아직 마운트 전. 마운트 시 AI 분류값 → 폼값 순으로 초기화.
  const [confirmedTypes, setConfirmedTypes] = useState<string[] | null>(null);

  useEffect(() => {
    setMounted(true);
    const e = getCase(caseId);
    setInitialEntry(e);
    if (e?.ec?.structuredData) setStructured(e.ec.structuredData);
    setConfirmedTypes(e?.ec?.classify?.workerTypes ?? e?.ec?.workerTypes ?? []);
    // 구조화·분석 중이면 사용자가 직접 URL 친 경우라도 로딩 페이지로 자동 안내.
    // structuredData 가 아직 안 채워졌으면 로딩에서 phase 변화를 기다려야 함.
    const phase = e?.ec?.phase;
    if (
      e &&
      !e.ec?.structuredData &&
      (phase === 'extracting' || phase === 'structuring' || phase === 'analyzing')
    ) {
      router.replace(`/review/${caseId}/loading`);
    }
  }, [caseId, router]);

  // 모바일(≤720px) — 줄 단위 OCR 확인 화면으로 분기 (훅은 조기 return 전에)
  const isMobile = useIsMobileViewport();

  // 좌측 패널: 원본 이미지 우선, 없으면 OCR 추출 텍스트.
  // blob URL revoke 는 다음 페이지가 같은 URL 을 못 읽는 버그 방지 위해 일부러 안 함.
  const originalUrl = initialEntry?.originalUrl;
  const originalKind = initialEntry?.originalKind;
  const extractedText = initialEntry?.ec?.extractedText ?? '';
  const businessSize = initialEntry?.ec?.businessSize ?? '';
  const workerTypes = initialEntry?.ec?.workerTypes ?? [];

  if (!mounted) {
    return <main className={styles.page} aria-hidden />;
  }

  // 케이스 자체가 없음 — 새로고침으로 sessionStorage 마저 비었거나 잘못된 URL
  if (!initialEntry) {
    return (
      <main className={styles.page}>
        <div className={styles.layout}>
          <div className={styles.notFound}>
            <h1 className={styles.title}>검토 세션을 찾을 수 없습니다</h1>
            <p style={{ color: 'var(--color-text-muted)', marginBottom: 12 }}>
              세션 ID <code style={{ fontFamily: 'D2Coding, ui-monospace, monospace' }}>{caseId}</code>{' '}
              에 해당하는 검토를 찾지 못했어요. 브라우저 저장소가 비워졌거나 다른 기기에서 시작한
              세션일 수 있습니다.
            </p>
            <p>
              <Link href="/">← 새로 검토 시작하기</Link>
            </p>
          </div>
        </div>
      </main>
    );
  }

  // ── 모바일 (≤720px) — 줄 단위 OCR 확인 화면 ──
  // 텍스트가 수정됐으면 재구조화(postEcStructure) 후 분석, 아니면 기존 structuredData 재사용.
  // phase: 'structuring' → 'analyzing' → 'result' 순서로 LoadingScreen 이 라우팅을 이끈다
  // ('structuring'/'analyzing' 은 라우팅하지 않고 로딩 유지, 'result' 에서 결과 페이지로).
  if (isMobile && initialEntry.ec?.extractedText) {
    const originalText = initialEntry.ec.extractedText;
    const existingSd = initialEntry.ec.structuredData;
    const classify = initialEntry.ec.classify;

    const startMobileAnalyze = (edited: string) => {
      setSubmitting(true);
      // AI 분류 확인값 우선 — 없으면(레거시·분류 실패) 폼에서 받은 workerTypes.
      const finalTypes = confirmedTypes ?? workerTypes;
      updateEc(caseId, {
        phase: 'structuring',
        extractedText: edited,
        errorMessage: undefined,
        workerTypes: finalTypes,
        ...(classify ? { classify: { ...classify, confirmed: true } } : {}),
      });
      router.push(`/review/${caseId}/loading`);
      // 백그라운드 — 페이지 이탈 후에도 promise 는 살아있다.
      (async () => {
        let sd = existingSd;
        // 수정됐거나 기존 구조화 결과가 없으면 재구조화
        if (edited !== originalText || !sd || Object.keys(sd).length === 0) {
          const out = await postEcStructure(edited);
          const next = out?.structured_data;
          if (!next || typeof next !== 'object' || Object.keys(next).length === 0) {
            throw new Error(
              '계약서 구조화 결과가 비어있어요. OCR 텍스트가 짧거나 형식이 표준 계약서가 아닐 수 있습니다.',
            );
          }
          sd = next;
        }
        updateEc(caseId, { phase: 'analyzing', structuredData: sd });
        const out = await postEcAnalyze(sd, businessSize, finalTypes, { caseId });
        updateEc(caseId, { phase: 'result', analysisResult: out.analysis_result });
      })().catch((err) => {
        const msg =
          err instanceof ApiCallError
            ? err.detail
            : err instanceof Error
              ? err.message
              : String(err);
        // setCaseError 는 entry 를 새로 만들며 ec 를 비우므로,
        // 패치에 텍스트·컨텍스트를 다시 실어 재시도 가능 상태를 보존.
        setCaseError(caseId, msg);
        updateEc(caseId, {
          phase: 'review',
          errorMessage: msg,
          extractedText: edited,
          businessSize,
          workerTypes: finalTypes,
        });
      });
    };

    return (
      <MobileOcrConfirm
        initialText={originalText}
        submitting={submitting}
        onSubmit={startMobileAnalyze}
        onBack={() => router.push('/')}
        errorMessage={initialEntry.ec?.errorMessage}
        imageUrl={
          initialEntry.originalKind === 'image'
            ? initialEntry.originalUrl
            : undefined
        }
        headerExtra={
          classify ? (
            <ClassifyConfirm
              docKind={classify.docKind}
              reason={classify.reason}
              workerTypes={classify.workerTypes}
              value={confirmedTypes ?? []}
              onChange={setConfirmedTypes}
            />
          ) : undefined
        }
      />
    );
  }

  // 케이스는 있는데 structuredData 가 아직 없음 — phase 가 진행 중이면 이미 로딩으로 이동했고,
  // 그 외 (예: error/contract 등) 면 안내 + 재시작 권유
  if (!structured) {
    const phase = initialEntry.ec?.phase;
    const isProgress = phase === 'extracting' || phase === 'structuring' || phase === 'analyzing';
    if (isProgress) {
      // useEffect 의 router.replace 가 곧 페이지를 바꿀 것 — 그동안 빈 페이지
      return <main className={styles.page} aria-hidden />;
    }
    const retryStructure = async () => {
      const text = initialEntry.ec?.extractedText;
      if (!text) return;
      updateEc(caseId, { phase: 'structuring', errorMessage: undefined });
      router.push(`/review/${caseId}/loading`);
      try {
        // postEcStructure 를 동적 import 로 — 페이지 코드 분리
        const { postEcStructure } = await import('@/lib/api/ec');
        const out = await postEcStructure(text);
        const sd = out?.structured_data;
        if (!sd || Object.keys(sd).length === 0) {
          throw new Error('재시도 후에도 구조화 결과가 비어있어요.');
        }
        updateEc(caseId, { phase: 'review', structuredData: sd });
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setCaseError(caseId, msg);
        updateEc(caseId, { phase: 'review', errorMessage: msg });
        router.push(`/review/${caseId}/ec/review`);
      }
    };
    return (
      <main className={styles.page}>
        <div className={styles.layout}>
          <div className={styles.notFound}>
            <h1 className={styles.title}>구조화 데이터가 없어요</h1>
            <p style={{ color: 'var(--color-text-muted)', marginBottom: 12 }}>
              세션은 있지만 구조화된 계약서 데이터를 찾을 수 없어요 (현재 단계:{' '}
              <code style={{ fontFamily: 'D2Coding, ui-monospace, monospace' }}>{phase || '미상'}</code>).
              {initialEntry.ec?.errorMessage && (
                <>
                  <br />
                  <span style={{ color: '#b91c1c', fontSize: 12 }}>
                    이전 오류: {initialEntry.ec.errorMessage.slice(0, 200)}
                  </span>
                </>
              )}
            </p>
            {initialEntry.ec?.extractedText && (
              <div
                style={{
                  display: 'flex',
                  gap: 10,
                  marginBottom: 14,
                  flexWrap: 'wrap',
                }}
              >
                <button
                  type="button"
                  onClick={retryStructure}
                  style={{
                    padding: '8px 14px',
                    background: 'var(--color-brand)',
                    color: '#fff',
                    border: 'none',
                    borderRadius: 8,
                    fontWeight: 700,
                    cursor: 'pointer',
                  }}
                >
                  🔁 구조화 다시 시도
                </button>
                <Link
                  href="/"
                  style={{
                    padding: '8px 14px',
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    borderRadius: 8,
                    fontWeight: 600,
                    color: 'var(--color-text)',
                    textDecoration: 'none',
                  }}
                >
                  새로 검토 시작
                </Link>
              </div>
            )}
            {!initialEntry.ec?.extractedText && (
              <p>
                <Link href="/">← 새로 검토 시작하기</Link>
              </p>
            )}
          </div>
        </div>
      </main>
    );
  }

  const startAnalyze = () => {
    if (!structured) return;
    setSubmitting(true);
    setError(null);
    // AI 분류 확인값 우선 — 없으면(레거시·분류 실패) 폼에서 받은 workerTypes.
    const finalTypes = confirmedTypes ?? workerTypes;
    const classify = initialEntry?.ec?.classify;
    // 검토 페이지에서 사용자가 수정한 최종본을 store 에 저장하고,
    // phase 를 'analyzing' 으로 박은 뒤 즉시 로딩 페이지로 이동.
    // LoadingScreen 이 phase 를 보고 "분석 단계" UI 를 띄우다가
    // phase='result' 가 되면 결과 페이지로 라우팅한다.
    updateEc(caseId, {
      phase: 'analyzing',
      structuredData: structured,
      errorMessage: undefined,
      workerTypes: finalTypes,
      ...(classify ? { classify: { ...classify, confirmed: true } } : {}),
    });
    router.push(`/review/${caseId}/loading`);
    // 백그라운드 fetch — 페이지 이탈 후에도 promise 는 살아있다.
    postEcAnalyze(structured, businessSize, finalTypes, { caseId })
      .then((out) => {
        updateEc(caseId, {
          phase: 'result',
          analysisResult: out.analysis_result,
        });
      })
      .catch((err) => {
        const msg =
          err instanceof ApiCallError
            ? err.detail
            : err instanceof Error
              ? err.message
              : String(err);
        // 로딩 화면이 에러를 표시하도록 case status 까지 error 로.
        setCaseError(caseId, msg);
        updateEc(caseId, { phase: 'review', errorMessage: msg });
      });
  };

  return (
    <main className={styles.page}>
      <div className={styles.layout}>
        <h1 className={styles.title}>추출된 내용을 확인하고 수정해 주세요</h1>
        <div className={styles.subtitle}>
          <strong>왼쪽 원본</strong>과 비교하면서 <strong>잘못 읽힌 숫자·날짜·이름</strong> 등을{' '}
          <strong>직접 고치면</strong> 분석이 <strong>더 정확</strong>해져요.
          수정이 끝나면 아래 <strong>“분석 시작”</strong>을 눌러 주세요.
        </div>

        {/* AI 1차 분류 확인 — 분류 결과가 있을 때만 (레거시·분류 실패 시 기존 흐름) */}
        {initialEntry.ec?.classify && (
          <div className={styles.classifyWrap}>
            <ClassifyConfirm
              docKind={initialEntry.ec.classify.docKind}
              reason={initialEntry.ec.classify.reason}
              workerTypes={initialEntry.ec.classify.workerTypes}
              value={confirmedTypes ?? []}
              onChange={setConfirmedTypes}
            />
          </div>
        )}

        <div className={styles.split}>
          <aside className={styles.docPanel} aria-label="업로드된 문서 원본">
            <div className={styles.panelHead}>
              <span className={styles.panelTitle}>업로드된 문서</span>
              {initialEntry?.originalFilename && (
                <span
                  className={styles.panelSubtitle}
                  title={initialEntry.originalFilename}
                >
                  {initialEntry.originalFilename}
                </span>
              )}
            </div>
            {originalKind === 'image' && originalUrl ? (
              <div className={styles.docImageScroll}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={originalUrl}
                  alt={initialEntry?.originalFilename || '업로드 문서'}
                  className={styles.docImage}
                />
              </div>
            ) : (
              <div className={styles.docTextScroll}>
                {extractedText || '(추출된 텍스트가 비어 있습니다)'}
              </div>
            )}
          </aside>

          <section className={styles.analysisPanel}>
            <div className={styles.contextRow}>
              <span className={styles.contextLabel}>사업장 규모</span>
              <span className={styles.contextChip}>
                {businessSize || '미지정'}
              </span>
              <span className={styles.contextLabel} style={{ marginLeft: 8 }}>
                근로자 유형
              </span>
              {workerTypes.length === 0 ? (
                <span className={styles.contextChip}>미지정</span>
              ) : (
                workerTypes.map((t) => (
                  <span key={t} className={styles.contextChip}>
                    {t}
                  </span>
                ))
              )}
            </div>

            <EditableStructureTable value={structured} onChange={setStructured} />

            <div className={styles.ctaBar}>
              <Link href="/" className={styles.btnSecondary}>
                다시 업로드
              </Link>
              <button
                type="button"
                className={styles.btnPrimary}
                onClick={startAnalyze}
                disabled={submitting}
              >
                {submitting ? '분석 중…' : '분석 시작'}
              </button>
            </div>

            {error && (
              <div className={styles.error}>
                <strong>분석 실패:</strong> {error}
              </div>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
