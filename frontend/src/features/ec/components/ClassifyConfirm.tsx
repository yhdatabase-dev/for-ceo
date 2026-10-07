'use client';

/**
 * ClassifyConfirm — "AI 1차 분류 → 사용자 확인" 공용 배너.
 *
 * 근로계약서(EC) 흐름에서 사용자가 근로자 유형을 직접 고르는 대신,
 * AI 가 업로드 문서를 보고 먼저 판단한 결과를 확인만 하게 한다.
 *
 *  - 초기(asking): 'AI 판단 · {docKind}' + 유형 칩 + 근거 1줄 → [맞아요]/[아니에요]
 *  - 맞아요: 슬림 확정 바('✓ {docKind} · 유형들')로 접힘 + '변경' 으로 재오픈
 *  - 아니에요: ALL_WORKER_TYPES 다중 선택 칩 그리드 → '선택 완료' 로 확정 바
 *
 * 데스크톱 카드·모바일 화면 양쪽에 그대로 들어가는 유동 폭(fluid) 컴포넌트.
 * 선택값(value)은 부모가 소유하는 controlled 패턴 — 분석 시작 시 부모가 사용.
 */

import { useState } from 'react';

import { ALL_WORKER_TYPES, type WorkerType } from '@/components/home/WorkplaceForm';

import styles from './ClassifyConfirm.module.css';

export interface ClassifyConfirmProps {
  /** 예: 'AI 판단: 기간제 근로계약서' 의 본문 — '기간제 근로계약서'. */
  docKind: string;
  /** AI 판단 근거 — 1줄 말줄임 표시. */
  reason?: string;
  /** AI 가 추정한 근로자 유형. */
  workerTypes: string[];
  /** 현재 선택값 (controlled). */
  value: string[];
  onChange: (types: string[]) => void;
  /** 맞아요(true)/아니에요(false) 클릭 시. */
  onConfirmed?: (ok: boolean) => void;
}

type Mode = 'asking' | 'editing' | 'confirmed';

function SparkleIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 3l1.8 4.6L18.5 9.4l-4.7 1.8L12 15.8l-1.8-4.6L5.5 9.4l4.7-1.8L12 3z" />
      <path d="M19 14l.9 2.3 2.3.9-2.3.9L19 20.4l-.9-2.3-2.3-.9 2.3-.9L19 14z" />
    </svg>
  );
}

export default function ClassifyConfirm({
  docKind,
  reason,
  workerTypes,
  value,
  onChange,
  onConfirmed,
}: ClassifyConfirmProps) {
  const [mode, setMode] = useState<Mode>('asking');

  const handleYes = () => {
    // AI 추정값을 그대로 확정 — 부모 선택값과 동기화
    onChange([...workerTypes]);
    onConfirmed?.(true);
    setMode('confirmed');
  };

  const handleNo = () => {
    onConfirmed?.(false);
    setMode('editing');
  };

  const toggle = (t: WorkerType) => {
    const has = value.includes(t);
    onChange(has ? value.filter((x) => x !== t) : [...value, t]);
  };

  // ── 확정 바 — 슬림 ──
  if (mode === 'confirmed') {
    return (
      <div className={styles.confirmedBar} role="status">
        <span className={styles.confirmedCheck} aria-hidden>
          ✓
        </span>
        <span className={styles.confirmedText}>
          {docKind}
          {value.length > 0 && <> · {value.join(' · ')}</>}
        </span>
        <button
          type="button"
          className={styles.changeBtn}
          onClick={() => setMode('editing')}
        >
          변경
        </button>
      </div>
    );
  }

  // ── 수동 선택 (아니에요) ──
  if (mode === 'editing') {
    return (
      <div className={styles.card}>
        <div className={styles.head}>
          <span className={styles.icon} aria-hidden>
            <SparkleIcon />
          </span>
          <div className={styles.headText}>
            <div className={styles.line1}>해당하는 근로자 유형을 골라주세요</div>
            <div className={styles.helper}>
              AI가 문서를 보고 판단했어요. 맞는지 확인해 주세요.
            </div>
          </div>
        </div>
        <div className={styles.chipGrid} role="group" aria-label="근로자 유형 선택">
          {ALL_WORKER_TYPES.map((t) => {
            const active = value.includes(t);
            return (
              <button
                key={t}
                type="button"
                className={`${styles.chip} ${active ? styles.chipActive : ''}`}
                aria-pressed={active}
                onClick={() => toggle(t)}
              >
                {t}
              </button>
            );
          })}
        </div>
        <div className={styles.editActions}>
          <button
            type="button"
            className={styles.btnBrand}
            disabled={value.length === 0}
            onClick={() => setMode('confirmed')}
          >
            선택 완료
          </button>
        </div>
      </div>
    );
  }

  // ── 초기 — AI 판단 확인 ──
  return (
    <div className={styles.card}>
      <div className={styles.askRow}>
        <span className={styles.icon} aria-hidden>
          <SparkleIcon />
        </span>
        <div className={styles.askBody}>
          <div className={styles.line1}>
            AI 판단 · <strong>{docKind}</strong>
          </div>
          <div className={styles.line2}>
            {workerTypes.map((t) => (
              <span key={t} className={styles.miniChip}>
                {t}
              </span>
            ))}
          </div>
          {reason && <div className={styles.reasonBlock}>{reason}</div>}
        </div>
        <div className={styles.askActions}>
          <button type="button" className={styles.btnBrand} onClick={handleYes}>
            맞아요
          </button>
          <button type="button" className={styles.btnGhost} onClick={handleNo}>
            아니에요
          </button>
        </div>
      </div>
    </div>
  );
}
