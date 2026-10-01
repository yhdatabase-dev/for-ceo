'use client';

import { useEffect, useState, use } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

import MobileOcrConfirm from '@/components/review/mobile/MobileOcrConfirm';
import { useIsMobileViewport } from '@/components/review/mobile/MobileReviewApp';
import { postScAnalyze, postScStructure } from '@/lib/api/sc';
import type { ScStructuredData } from '@/lib/api/sc';
import { ApiCallError } from '@/lib/api/client';
import { getCase, setCaseError, updateSc } from '@/lib/reviewStore';

import styles from '../../ec/review/page.module.css';

/**
 * 노무제공자 계약서 — Step 2 검토·수정 페이지 (Phase 17).
 *
 * 좌: 원본 이미지/추출 텍스트
 * 우: 4 섹션·16 슬롯 편집 표 + worker_subtype 선택 + "분석 시작" CTA.
 *
 * worker_subtype 은 사회보험 적용을 결정하는 핵심 컨텍스트라 본 페이지에서 명시.
 */

const WORKER_SUBTYPES: Array<{ id: string; label: string; desc: string }> = [
  {
    id: '산재적용_특고16',
    label: '산재보험 적용 (특고 16개 직종)',
    desc: '학습지교사·보험설계사·캐디·택배·화물차주·가전설치/배송 등',
  },
  {
    id: '고용보험_노무제공자19',
    label: '고용보험 적용 (노무제공자 19개 직종)',
    desc: '예술인·대리운전·방문판매·신용카드모집 등 (2024 확대)',
  },
  {
    id: '플랫폼종사자',
    label: '플랫폼 종사자',
    desc: '배달·운송·가사·돌봄 등 플랫폼 매개',
  },
  {
    id: '기타_도급',
    label: '기타 도급/위임',
    desc: '위 카테고리에 해당하지 않음',
  },
];

const SECTIONS: Array<{
  key: keyof Omit<ScStructuredData, '기타사항'>;
  title: string;
  hint: string;
}> = [
  { key: '당사자정보', title: '1. 당사자 정보', hint: '사업주·노무제공자·적용 직종 분류' },
  { key: '계약기본', title: '2. 계약 기본', hint: '기간·장소·업무·노무제공 방식' },
  { key: '보수및사회보험', title: '3. 보수·사회보험', hint: '보수 구성·지급일·산재·고용보험' },
  { key: '보호및분쟁', title: '4. 보호·해지·분쟁', hint: '안전보건·해지·손해배상·분쟁·근로자성 위장 방지' },
];

export default function ScReviewPage(props: { params: Promise<{ id: string }> }) {
  const params = use(props.params);
  const router = useRouter();
  const caseId = params.id;

  const [mounted, setMounted] = useState(false);
  const [initialEntry, setInitialEntry] =
    useState<ReturnType<typeof getCase>>(null);
  const [structured, setStructured] = useState<ScStructuredData | null>(null);
  const [workerSubtype, setWorkerSubtype] = useState<string>('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setMounted(true);
    const e = getCase(caseId);
    setInitialEntry(e);
    if (e?.sc?.structuredData) setStructured(e.sc.structuredData);
    if (e?.sc?.workerSubtype) setWorkerSubtype(e.sc.workerSubtype);
    // 구조화·분석 중이면 로딩 페이지로 자동 안내
    const phase = e?.sc?.phase;
    if (
      e &&
      !e.sc?.structuredData &&
      (phase === 'extracting' || phase === 'structuring' || phase === 'analyzing')
    ) {
      router.replace(`/review/${caseId}/loading`);
    }
  }, [caseId, router]);

  // 모바일(≤720px) — 줄 단위 OCR 확인 화면으로 분기 (훅은 조기 return 전에)
  const isMobile = useIsMobileViewport();

  const originalUrl = initialEntry?.originalUrl;
  const originalKind = initialEntry?.originalKind;
  const extractedText = initialEntry?.sc?.extractedText ?? '';
  const businessSize = initialEntry?.sc?.businessSize ?? '';

  if (!mounted) {
    return <main className={styles.page} aria-hidden />;
  }
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
  // 텍스트가 수정됐으면 재구조화(postScStructure) 후 분석, 아니면 기존 structuredData 재사용.
  // phase: 'structuring' → 'analyzing' → 'result' 순서로 LoadingScreen 이 라우팅을 이끈다
  // ('structuring'/'analyzing' 은 라우팅하지 않고 로딩 유지, 'result' 에서 결과 페이지로).
  if (isMobile && initialEntry.sc?.extractedText) {
    const originalText = initialEntry.sc.extractedText;
    const existingSd = initialEntry.sc.structuredData;

    const startMobileAnalyze = (edited: string) => {
      setSubmitting(true);
      updateSc(caseId, {
        phase: 'structuring',
        extractedText: edited,
        errorMessage: undefined,
      });
      router.push(`/review/${caseId}/loading`);
      // 백그라운드 — 페이지 이탈 후에도 promise 는 살아있다.
      (async () => {
        let sd = existingSd;
        // 수정됐거나 기존 구조화 결과가 없으면 재구조화
        if (edited !== originalText || !sd || Object.keys(sd).length === 0) {
          const out = await postScStructure(edited);
          const next = out?.structured_data;
          if (!next || typeof next !== 'object' || Object.keys(next).length === 0) {
            throw new Error(
              '구조화 결과가 비어있어요. OCR 텍스트가 짧거나 형식이 표준 계약서가 아닐 수 있습니다.',
            );
          }
          sd = next;
        }
        updateSc(caseId, {
          phase: 'analyzing',
          structuredData: sd,
          workerSubtype,
        });
        const out = await postScAnalyze(sd, { workerSubtype, businessSize });
        updateSc(caseId, { phase: 'result', analysisResult: out.analysis_result });
      })().catch((err) => {
        const msg =
          err instanceof ApiCallError
            ? err.detail
            : err instanceof Error
              ? err.message
              : String(err);
        // setCaseError 는 entry 를 새로 만들며 sc 를 비우므로,
        // 패치에 텍스트·컨텍스트를 다시 실어 재시도 가능 상태를 보존.
        setCaseError(caseId, msg);
        updateSc(caseId, {
          phase: 'review',
          errorMessage: msg,
          extractedText: edited,
          workerSubtype,
          businessSize,
        });
      });
    };

    return (
      <MobileOcrConfirm
        initialText={originalText}
        submitting={submitting}
        onSubmit={startMobileAnalyze}
        onBack={() => router.push('/')}
        errorMessage={initialEntry.sc?.errorMessage}
        imageUrl={
          initialEntry.originalKind === 'image'
            ? initialEntry.originalUrl
            : undefined
        }
      />
    );
  }

  if (!structured) {
    const phase = initialEntry.sc?.phase;
    const isProgress = phase === 'extracting' || phase === 'structuring' || phase === 'analyzing';
    if (isProgress) {
      return <main className={styles.page} aria-hidden />;
    }
    return (
      <main className={styles.page}>
        <div className={styles.layout}>
          <div className={styles.notFound}>
            <h1 className={styles.title}>구조화 데이터가 없어요</h1>
            <p style={{ color: 'var(--color-text-muted)', marginBottom: 12 }}>
              세션은 있지만 구조화된 데이터를 찾을 수 없습니다 (현재 단계: {phase || '미상'}). 새로
              검토를 시작하시는 게 빠를 것 같아요.
            </p>
            <p>
              <Link href="/">← 새로 검토 시작하기</Link>
            </p>
          </div>
        </div>
      </main>
    );
  }

  const updateSlot = (
    section: keyof Omit<ScStructuredData, '기타사항'>,
    slot: string,
    field: 'value' | 'note',
    next: string,
  ) => {
    setStructured((prev) => {
      if (!prev) return prev;
      const sec = { ...(prev[section] as Record<string, { value: string; note: string }>) };
      sec[slot] = { ...sec[slot], [field]: next };
      return { ...prev, [section]: sec } as ScStructuredData;
    });
  };

  const startAnalyze = () => {
    if (!structured) return;
    setSubmitting(true);
    setError(null);
    updateSc(caseId, {
      phase: 'analyzing',
      structuredData: structured,
      workerSubtype,
      errorMessage: undefined,
    });
    router.push(`/review/${caseId}/loading`);
    postScAnalyze(structured, { workerSubtype, businessSize })
      .then((out) => {
        updateSc(caseId, {
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
        setCaseError(caseId, msg);
        updateSc(caseId, { phase: 'review', errorMessage: msg });
      });
  };

  return (
    <main className={styles.page}>
      <div className={styles.layout}>
        <div className={styles.head}>
          <span className={styles.docBadge}>📋 노무제공자 계약서 · Step 2</span>
        </div>
        <h1 className={styles.title}>추출된 내용을 확인하고 수정해 주세요</h1>
        <div className={styles.subtitle}>
          <strong>왼쪽 원본</strong>과 비교하면서 <strong>잘못 읽힌 부분</strong>을 직접 고치면
          분석이 <strong>더 정확</strong>해져요. 특히 <strong>적용 직종</strong>은 사회보험 가입 의무 판단의 핵심입니다.
        </div>

        <div className={styles.split}>
          <aside className={styles.docPanel} aria-label="업로드된 문서 원본">
            <div className={styles.panelHead}>
              <span className={styles.panelTitle}>업로드된 문서</span>
              {initialEntry?.originalFilename && (
                <span className={styles.panelSubtitle} title={initialEntry.originalFilename}>
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
              <span className={styles.contextChip}>{businessSize || '미지정'}</span>
            </div>

            {/* 노무제공자 직종 분류 — 핵심 컨텍스트 */}
            <div
              style={{
                marginTop: 16,
                padding: 14,
                background: 'var(--color-brand-soft)',
                border: '1px solid var(--color-brand)',
                borderRadius: 12,
              }}
            >
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>
                ⚙️ 노무제공자 직종 분류 (사회보험 적용 판단)
              </div>
              <div style={{ display: 'grid', gap: 6 }}>
                {WORKER_SUBTYPES.map((opt) => (
                  <label
                    key={opt.id}
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 8,
                      padding: 8,
                      background: workerSubtype === opt.id ? '#fff' : 'transparent',
                      border:
                        workerSubtype === opt.id
                          ? '1px solid var(--color-brand)'
                          : '1px solid transparent',
                      borderRadius: 8,
                      cursor: 'pointer',
                    }}
                  >
                    <input
                      type="radio"
                      name="worker_subtype"
                      checked={workerSubtype === opt.id}
                      onChange={() => setWorkerSubtype(opt.id)}
                      style={{ marginTop: 3 }}
                    />
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{opt.label}</div>
                      <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)' }}>
                        {opt.desc}
                      </div>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            {/* 4 섹션 16 슬롯 편집 */}
            <div style={{ marginTop: 18 }}>
              {SECTIONS.map((sec) => {
                const sectionData = structured[sec.key] as Record<
                  string,
                  { value: string; note: string }
                >;
                return (
                  <div
                    key={sec.key}
                    style={{
                      marginBottom: 18,
                      padding: 14,
                      background: '#fff',
                      border: '1px solid var(--color-border)',
                      borderRadius: 12,
                    }}
                  >
                    <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>
                      {sec.title}
                    </div>
                    <div
                      style={{
                        fontSize: 11.5,
                        color: 'var(--color-text-muted)',
                        marginBottom: 10,
                      }}
                    >
                      {sec.hint}
                    </div>
                    {Object.entries(sectionData).map(([slot, val]) => (
                      <div
                        key={slot}
                        style={{
                          display: 'grid',
                          gridTemplateColumns: '120px 1fr',
                          gap: 8,
                          alignItems: 'start',
                          padding: '6px 0',
                          borderTop: '1px dashed var(--color-border)',
                        }}
                      >
                        <div style={{ fontSize: 12, fontWeight: 600, paddingTop: 4 }}>
                          {slot}
                        </div>
                        <div>
                          <textarea
                            value={val.value}
                            onChange={(e) =>
                              updateSlot(sec.key, slot, 'value', e.target.value)
                            }
                            rows={2}
                            placeholder="기재 내용"
                            style={{
                              width: '100%',
                              fontSize: 12.5,
                              padding: 6,
                              border: '1px solid var(--color-border)',
                              borderRadius: 6,
                              resize: 'vertical',
                              fontFamily: 'inherit',
                            }}
                          />
                          {val.note && (
                            <div
                              style={{
                                marginTop: 4,
                                fontSize: 11,
                                color: 'var(--color-text-muted)',
                                fontStyle: 'italic',
                              }}
                            >
                              메모: {val.note}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>

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
