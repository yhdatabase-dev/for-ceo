'use client';

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';

import Icon from '@/components/ui/Icon';
import { useMockProgress } from '@/hooks/useMockProgress';
import { getCase } from '@/features/history/store';
import type { CaseEntry } from '@/features/history/store';
import type { DocumentType } from '@/types/review';
import styles from './LoadingScreen.module.css';
import { routes } from '@/lib/routes';

/**
 * 검토 진행 중 화면.
 *
 * **진행률 모델 — 흐름 전역 3매크로 + 구간 점근 (튐 방지)**
 * 전체 검토 흐름은 사용자 확인 페이지를 사이에 두고 여러 로딩 인스턴스로 쪼개진다.
 * 각 인스턴스를 0% 부터 다시 시작하면 "9%→100%→6%" 처럼 보인다. 그래서 모든
 * 흐름을 3개 매크로로 보고, 각 로딩은 **자기 매크로 구간의 하한부터** 차오른다:
 *
 *   ① 추출·정리      0→33%   (홈 진입 로딩)
 *   ② 법령 비교·분석  33→80%  (확인 페이지 뒤 분석 로딩)   ← 임금명세서는 33→100%
 *   ③ 표준문서 생성   80→100% (취업규칙·근로계약서·노무 only)
 *
 * 매크로는 store 의 phase 로 유도(새 필드 불요). 페이지 이동 직전 `snapTo` 로 구간
 * 상한까지 끌어올린 뒤 라우팅 → 다음 인스턴스가 그 상한부터 이어받아 단조 증가.
 */

type Macro = 'extract' | 'analyze' | 'generate';

interface Step {
  n: number;
  title: string;
  desc: string;
}

/** 문서종류 × 매크로 → 큰 제목 + 세부 단계 리스트 (기존 카피 보존). */
const DOC_MACROS: Record<DocumentType, Partial<Record<Macro, { heading: string; steps: Step[] }>>> = {
  'work-rules': {
    extract: {
      heading: '취업규칙을 꼼꼼히 살펴보고 있어요',
      steps: [
        { n: 1, title: '문서 추출', desc: 'DOCX·HWP·PDF·TXT 텍스트로 변환' },
        { n: 2, title: '조항 식별', desc: '조 단위로 분류해 검토 준비' },
      ],
    },
    analyze: {
      heading: '법령을 비교하고 결과를 정리하고 있어요',
      steps: [
        { n: 1, title: '법령 비교', desc: '위반 사항 평가' },
        { n: 2, title: '리포트 생성', desc: '위험도·시정 가이드·법령 근거 작성' },
      ],
    },
    generate: {
      heading: '수정된 취업규칙 신구대조표를 만들고 있어요',
      steps: [
        { n: 1, title: '개정 항목 정리', desc: '위반·누락 조항을 개정 전/후로 대조' },
        { n: 2, title: '신구대조표 작성', desc: '변경사유·관련 법령(최신) 반영' },
      ],
    },
  },
  'employment-contract': {
    extract: {
      heading: '근로계약서를 꼼꼼히 살펴보고 있어요',
      steps: [
        { n: 1, title: '문서 추출', desc: '이미지·DOCX·HWP·PDF·TXT 텍스트로 변환' },
        { n: 2, title: '필수 항목 식별', desc: '필수 기재사항 단위로 정리' },
      ],
    },
    analyze: {
      heading: '법령을 비교하고 결과를 정리하고 있어요',
      steps: [
        { n: 1, title: '법령 비교', desc: '근로기준법 제17조 등 위반 여부 확인' },
        { n: 2, title: '리포트 생성', desc: '적절·보완필요·부적절 분류 + 시정안 작성' },
      ],
    },
    generate: {
      heading: '표준 근로계약서 초안을 작성하고 있어요',
      steps: [
        { n: 1, title: '양식 정리', desc: '고용노동부 표준 양식 적용' },
        { n: 2, title: '본문 작성', desc: '분석 결과·보완사항 반영, 최저시급 보정' },
      ],
    },
  },
};

/** phase 한 개 → 매크로 (완료 phase 는 그 단계의 매크로로 본다: result→analyze, contract→generate). */
function phaseToMacro(p: string | undefined): Macro {
  if (p === 'analyzing' || p === 'result') return 'analyze';
  if (p === 'generating' || p === 'contract') return 'generate';
  return 'extract'; // idle·extracting·structuring·review·error·undefined
}

/** 케이스 전체에서 가장 앞선 매크로를 고른다(활성 워크플로는 하나뿐이라 안전). */
function macroOf(entry: CaseEntry | null | undefined): Macro {
  if (!entry) return 'extract';
  const phases = [entry.ec?.phase, entry.wr?.phase];
  let m: Macro = 'extract';
  for (const p of phases) {
    const pm = phaseToMacro(p);
    if (pm === 'generate') return 'generate';
    if (pm === 'analyze') m = 'analyze';
  }
  return m;
}

/**
 * 매크로 → 진행률 구간 + 체감 시간.
 *
 * 검토 본류는 2단계(추출정리 0→50, 법령비교분석 50→100)로 결과가 100%에 도달한다.
 * 표준문서 생성은 사용자가 '수정본 만들기' 를 눌렀을 때만 일어나는 **별도 짧은 로딩**이라
 * 0→100 단독 구간으로 둔다(인디케이터에는 본류 2단계만 노출).
 */
function segBounds(macro: Macro): { lo: number; hi: number; durationMs: number } {
  if (macro === 'extract') return { lo: 0, hi: 50, durationMs: 12000 };
  if (macro === 'analyze') return { lo: 50, hi: 100, durationMs: 18000 };
  return { lo: 0, hi: 100, durationMs: 12000 }; // generate — 단독 로딩
}

interface LoadingScreenProps {
  /** 라우트의 review id — 100% 도달 시 결과 페이지(/review/{id})로 이동에 사용. UI 노출 X. */
  reviewId?: string;
}

// SSR 과 첫 클라이언트 렌더가 어긋나지 않도록 동형(isomorphic) 레이아웃 이펙트 사용.
// 서버엔 useLayoutEffect 가 없으므로 useEffect 로 폴백(no-op).
const useIsoLayoutEffect = typeof window !== 'undefined' ? useLayoutEffect : useEffect;

export function LoadingScreen({ reviewId }: LoadingScreenProps) {
  const router = useRouter();
  const [apiError, setApiError] = useState<string | null>(null);
  // SSR 안전 기본값으로 시작 — 하드 리로드 시 hydration mismatch 방지.
  // 실제 값은 마운트 직후 레이아웃 이펙트가 store 에서 읽어와 paint 전에 보정한다.
  const [docType, setDocType] = useState<DocumentType>('work-rules');
  const [macro, setMacro] = useState<Macro>('extract');
  // 라우팅 직전 구간 상한까지 끌어올리는 스냅 값.
  const [snapTo, setSnapTo] = useState<number | null>(null);
  // 라우팅 시작 후 폴링 재진입 차단(상태 변경으로 effect 가 재시작돼도 안전).
  const routingRef = useRef(false);

  const bounds = useMemo(() => segBounds(macro), [macro]);
  // 현재 매크로의 큰 제목 + 세부 단계 (없으면 extract 로 폴백).
  const macroDef = DOC_MACROS[docType][macro] ?? DOC_MACROS[docType].extract!;
  const STEPS = macroDef.steps;

  const { progress, activeStep } = useMockProgress({
    segLo: bounds.lo,
    segHi: bounds.hi,
    segDurationMs: bounds.durationMs,
    snapTo,
    totalSteps: STEPS.length,
  });

  // 마운트 직후(첫 paint 전) store 에서 문서종류·매크로를 읽어 보정.
  // 클라이언트 내비게이션은 깜빡임 없이, 하드 리로드는 mismatch 없이 정확해진다.
  useIsoLayoutEffect(() => {
    if (!reviewId) return;
    const entry = getCase(reviewId);
    if (!entry) return;
    if (entry.documentType && entry.documentType !== docType) setDocType(entry.documentType);
    const m = macroOf(entry);
    if (m !== macro) setMacro(m);
    // 마운트 1회만 — 이후 변화는 아래 폴링 effect 가 처리.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // store 폴링 — 단계 전환 및 결과 도달 시 페이지 라우팅.
  useEffect(() => {
    if (!reviewId) return;
    const id = window.setInterval(() => {
      if (routingRef.current) return; // 이미 이동 중 — 중복 라우팅 방지
      const entry = getCase(reviewId);
      if (!entry) return;

      // documentType / 매크로 동기화 (UI 분기 키)
      if (entry.documentType && entry.documentType !== docType) {
        setDocType(entry.documentType);
      }
      const curMacro = macroOf(entry);
      if (curMacro !== macro) {
        setMacro(curMacro);
      }

      // 라우팅 직전: 현재 구간 상한까지 스냅 → barFill 이 채워진 뒤 이동.
      // 다음 로딩 인스턴스는 그 상한(=다음 구간 하한)부터 시작 → 연속.
      const { hi } = segBounds(curMacro);
      const go = (path: string) => {
        routingRef.current = true;
        window.clearInterval(id);
        setSnapTo(hi);
        window.setTimeout(() => router.replace(path), 420);
      };
      const fail = (msg: string) => {
        window.clearInterval(id);
        setApiError(msg);
      };

      // EC 풀 이식 — phase 변화에 따라 다음 페이지로 자동 라우팅.
      const curPhase = entry.ec?.phase;
      if (curPhase === 'review') return go(routes.ecContract(reviewId));
      if (curPhase === 'result') return go(routes.ecReview(reviewId));
      if (curPhase === 'contract') return go(routes.ecPreview(reviewId));

      // 취업규칙 — 추출 텍스트 확인 단계. 'analyzing' 은 라우팅하지 않음
      // (분석 완료 시 아래 status='done' 분기가 /wr/[caseUid]/review 로 보냄).
      const wrPhase = entry.wr?.phase;
      if (wrPhase === 'review') return go(routes.wrText(reviewId));
      // 취업규칙 수정본 — 완료 시 contract 페이지로, 생성 중에는 status='done'
      // (기존 분석 완료) 분기가 결과 페이지로 되돌리지 않게 여기서 홀드.
      if (wrPhase === 'contract') return go(routes.wrComparison(reviewId));
      if (wrPhase === 'generating') return; // 생성 진행 중 — 폴링 유지

      // 취업규칙 등 단일 호출 흐름
      if (entry.status === 'done') {
        const target =
          entry.result?.doc === 'employment-contract'
            ? routes.ecReview(reviewId)
            : routes.wrReview(reviewId);
        return go(target);
      }
      if (entry.status === 'error') return fail(entry.error || '알 수 없는 오류');
    }, 500);
    return () => window.clearInterval(id);
  }, [reviewId, router, docType, macro]);

  return (
    <main className={styles.page}>
      <div className={styles.inner}>
        {/* 회전 로더 + 문서 아이콘 */}
        <div className={styles.loader}>
          <svg
            width="100"
            height="100"
            viewBox="0 0 100 100"
            className={styles.spin}
            aria-hidden
          >
            <circle
              cx="50"
              cy="50"
              r="42"
              fill="none"
              stroke="var(--color-brand-soft)"
              strokeWidth="4"
            />
            <circle
              cx="50"
              cy="50"
              r="42"
              fill="none"
              stroke="var(--color-brand)"
              strokeWidth="4"
              strokeLinecap="round"
              strokeDasharray="60 200"
            />
          </svg>
          <div className={styles.loaderIcon}>
            <Icon name="doc" size={36} />
          </div>
        </div>

        <div className={styles.eyebrow}>검토 진행중</div>
        <h2 className={styles.title}>{macroDef.heading}</h2>
        <div className={styles.subtitle}>
          잠시만 기다려 주세요. 페이지를 닫지 마세요.
        </div>

        {/* 진행률 카드 */}
        <section
          className={styles.progressCard}
          role="status"
          aria-live="polite"
          aria-label={`전체 진행률 ${progress} 퍼센트`}
        >
          <div className={styles.progressHead}>
            <span className={styles.progressLabel}>전체 진행률</span>
            <span className={styles.progressValue}>
              {progress}
              <span className={styles.progressUnit}>%</span>
            </span>
          </div>
          <div className={styles.bar}>
            <div className={styles.barFill} style={{ width: `${progress}%` }} />
          </div>
        </section>

        {/* 단계 리스트 — 현재 매크로의 세부 단계 */}
        <ol className={styles.steps} aria-label="검토 단계">
          {STEPS.map((s) => {
            const done = s.n < activeStep;
            const active = s.n === activeStep;
            const badgeClass = done
              ? `${styles.badge} ${styles.badgeDone}`
              : active
                ? `${styles.badge} ${styles.badgeActive}`
                : `${styles.badge} ${styles.badgePending}`;

            return (
              <li
                key={s.n}
                className={`${styles.step} ${!done && !active ? styles.stepPending : ''}`}
                aria-current={active ? 'step' : undefined}
              >
                <div className={badgeClass}>
                  {done ? <Icon name="check" size={14} /> : s.n}
                </div>
                <div className={styles.stepBody}>
                  <div className={styles.stepTitle}>{s.title}</div>
                  <div className={styles.stepDesc}>{s.desc}</div>
                </div>
                {active && (
                  <div className={styles.pulse} aria-hidden>
                    <span className={styles.dot} />
                    <span className={styles.dot} />
                    <span className={styles.dot} />
                  </div>
                )}
              </li>
            );
          })}
        </ol>

        {apiError ? (
          <div
            style={{
              marginTop: 18,
              padding: '16px 18px',
              background: '#fef2f2',
              border: '1px solid #fca5a5',
              borderLeft: '4px solid #dc2626',
              borderRadius: 10,
              color: '#7f1d1d',
              fontSize: 13,
              lineHeight: 1.7,
              textAlign: 'left',
              whiteSpace: 'pre-line',
            }}
          >
            <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 6 }}>
              ⚠ 검토를 완료하지 못했어요
            </div>
            <div>{apiError}</div>
            <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
              <button
                type="button"
                onClick={() => router.push('/')}
                style={{
                  background: '#dc2626',
                  border: '1px solid #dc2626',
                  color: '#fff',
                  padding: '8px 14px',
                  borderRadius: 6,
                  fontSize: 13,
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                ↺ 다시 시도
              </button>
              <button
                type="button"
                onClick={() => router.push('/history')}
                style={{
                  background: 'transparent',
                  border: '1px solid #fca5a5',
                  color: '#7f1d1d',
                  padding: '8px 14px',
                  borderRadius: 6,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                📋 내 검토 보기
              </button>
            </div>
          </div>
        ) : (
          <div className={styles.tip}>
            💡 결과 페이지는 PDF로 저장해 사업장에 보관할 수 있어요.
          </div>
        )}
      </div>
    </main>
  );
}

export default LoadingScreen;
