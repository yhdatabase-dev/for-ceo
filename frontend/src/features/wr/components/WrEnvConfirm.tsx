'use client';

/**
 * WrEnvConfirm — 취업규칙 "AI 근로환경 1차 분류 → 사용자 확인" 배너.
 *
 * 사업장들이 잘 모르는 근로환경 항목(교대제·산안법 적용·화학물질·작업환경측정)을
 * 홈 폼에서 직접 묻는 대신, AI 가 취업규칙 본문을 읽고 먼저 추정한 결과를
 * 확인만 하게 한다 — EC 의 ClassifyConfirm 과 동일한 UX·시각 언어.
 *
 *  - 초기(asking): 'AI 판단 · {docKind}' + 항목 칩 4개 + 근거 → [맞아요]/[아니에요]
 *  - 맞아요: 슬림 확정 바로 접힘 + '변경' 으로 재오픈
 *  - 아니에요: 항목별 3지선다(예/아니오/모름) 행 → '선택 완료' 로 확정 바
 *
 * 선택값(value)은 부모가 소유하는 controlled 패턴 — 분석 시작 시 부모가
 * WorkplaceContext 에 덮어쓴다. null = 모름(보수적으로 검사함).
 */

import { useState } from 'react';

// 개발표준정의서 계층 구조: 도메인 간 직접 참조 금지 — 근로계약서 ClassifyConfirm 스타일을 복사해 따로 둠 (기존: ./ClassifyConfirm.module.css 공유)
import styles from './WrEnvConfirm.module.css';

/** 근로환경 4항목 — WorkplaceContext 의 취업규칙용 필드와 1:1. */
export interface WrEnv {
  shiftWorkUsed: boolean | null;
  oshaApplicable: boolean | null;
  chemicalHandling: boolean | null;
  workenvMeasurement: boolean | null;
}

export interface WrEnvConfirmProps {
  /** 예: 'AI 판단: 제조업 취업규칙' 의 본문 — '제조업 취업규칙'. */
  docKind: string;
  /** AI 판단 근거 — 1줄 표시. */
  reason?: string;
  /** AI 가 추정한 근로환경 — [맞아요] 시 그대로 확정. */
  aiEnv: WrEnv;
  /** 현재 선택값 (controlled). */
  value: WrEnv;
  onChange: (env: WrEnv) => void;
  /** 맞아요(true)/아니에요(false) 클릭 시. */
  onConfirmed?: (ok: boolean) => void;
}

type Mode = 'asking' | 'editing' | 'confirmed';

interface EnvItem {
  key: keyof WrEnv;
  label: string;
  yes: string;
  no: string;
}

const ENV_ITEMS: EnvItem[] = [
  { key: 'shiftWorkUsed', label: '교대근로', yes: '도입함', no: '미도입' },
  { key: 'oshaApplicable', label: '산업안전보건법 적용', yes: '해당', no: '비해당' },
  { key: 'chemicalHandling', label: '화학물질 취급', yes: '취급함', no: '미취급' },
  { key: 'workenvMeasurement', label: '작업환경측정 대상', yes: '대상', no: '비대상' },
];

function fmt(item: EnvItem, v: boolean | null): string {
  if (v === null) return '모름';
  return v ? item.yes : item.no;
}

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

export default function WrEnvConfirm({
  docKind,
  reason,
  aiEnv,
  value,
  onChange,
  onConfirmed,
}: WrEnvConfirmProps) {
  const [mode, setMode] = useState<Mode>('asking');

  const handleYes = () => {
    // AI 추정값을 그대로 확정 — 부모 선택값과 동기화
    onChange({ ...aiEnv });
    onConfirmed?.(true);
    setMode('confirmed');
  };

  const handleNo = () => {
    onConfirmed?.(false);
    setMode('editing');
  };

  const setItem = (key: keyof WrEnv, v: boolean | null) =>
    onChange({ ...value, [key]: v });

  // ── 확정 바 — 슬림 ──
  if (mode === 'confirmed') {
    return (
      <div className={styles.confirmedBar} role="status">
        <span className={styles.confirmedCheck} aria-hidden>
          ✓
        </span>
        <span className={styles.confirmedText}>
          {docKind} ·{' '}
          {ENV_ITEMS.map((it) => `${it.label} ${fmt(it, value[it.key])}`).join(
            ' · ',
          )}
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
            <div className={styles.line1}>사업장 근로환경을 알려주세요</div>
            <div className={styles.helper}>
              잘 모르겠으면 &lsquo;모름&rsquo;을 선택하세요 — 해당 항목까지
              빠짐없이 검사해 드려요.
            </div>
          </div>
        </div>
        <div role="group" aria-label="근로환경 선택">
          {ENV_ITEMS.map((it) => {
            const cur = value[it.key];
            const options: { v: boolean | null; label: string }[] = [
              { v: true, label: it.yes },
              { v: false, label: it.no },
              { v: null, label: '모름' },
            ];
            return (
              <div key={it.key} className={styles.envRow}>
                <span className={styles.envLabel}>{it.label}</span>
                <span className={styles.envOptions}>
                  {options.map((opt) => {
                    const active = cur === opt.v;
                    return (
                      <button
                        key={String(opt.v)}
                        type="button"
                        className={`${styles.chip} ${active ? styles.chipActive : ''}`}
                        aria-pressed={active}
                        onClick={() => setItem(it.key, opt.v)}
                      >
                        {opt.label}
                      </button>
                    );
                  })}
                </span>
              </div>
            );
          })}
        </div>
        <div className={styles.editActions}>
          <button
            type="button"
            className={styles.btnBrand}
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
          <div className={styles.envSummary}>
            {ENV_ITEMS.map((it) => (
              <span key={it.key} className={styles.miniChip}>
                {it.label} {fmt(it, aiEnv[it.key])}
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
