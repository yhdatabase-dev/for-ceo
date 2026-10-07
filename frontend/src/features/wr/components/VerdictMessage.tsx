/**
 * 종합 판정 카드 메시지·톤 생성기.
 *
 * 백엔드 분포(누락·위반·주의·검토필요·적정)를 받아
 * (1) 카드 톤 (severe/mild/warn/ok)
 * (2) 사람용 안내 문구 (ReactNode)
 * 를 분기해서 만든다.
 */
import { Fragment, type ReactNode } from 'react';

import { RISK } from '@/styles/tokens';
import type { RiskCounts, RiskLevel } from '@/types/review';

export type VerdictTone = 'severe' | 'mild' | 'warn' | 'ok';

export interface VerdictMessage {
  tone: VerdictTone;
  /** 1줄 메인 문구. */
  primary: ReactNode;
  /** 보조 줄 (부가 항목). 없으면 null. */
  secondary: ReactNode | null;
}

/** 색칠된 라벨. */
function ColorTag({ level }: { level: RiskLevel }) {
  return <strong style={{ color: RISK[level].solid }}>{RISK[level].label}</strong>;
}

/** 쉼표로 라벨 + 카운트를 잇는 ReactNode 시퀀스. */
function joinList(items: { level: RiskLevel; count: number }[]): ReactNode {
  return items.map((it, i) => (
    <Fragment key={it.level}>
      {i > 0 && ', '}
      <ColorTag level={it.level} /> {it.count}건
    </Fragment>
  ));
}

/** 5-Bucket 분포 → 톤 + 문구. */
export function buildVerdictMessage(counts: RiskCounts): VerdictMessage {
  const missing = counts.missing ?? 0;
  const violation = counts.violation ?? 0;
  const warn = counts.warn ?? 0;
  const ambiguous = counts.ambiguous ?? 0;

  const severeTotal = missing + violation; // 강행규정 미준수 합

  // ── 케이스 1: 적정 (모두 0) ──────────
  if (severeTotal === 0 && warn === 0 && ambiguous === 0) {
    return {
      tone: 'ok',
      primary: (
        <>
          법정 기준에 <strong>모두 부합</strong>합니다. 추가 시정 없이 운영
          가능합니다.
        </>
      ),
      secondary: null,
    };
  }

  // ── 케이스 2: 강행 위반은 없음, 권고 항목만 ──────
  if (severeTotal === 0) {
    const items = buildItemList({ warn, ambiguous });
    return {
      tone: 'warn',
      primary: (
        <>
          강행규정 위반은 없으나, {joinList(items)}의 점검 권장 항목이 있습니다.
        </>
      ),
      secondary: (
        <>강제성은 없지만 분쟁 예방을 위해 시정을 권장드립니다.</>
      ),
    };
  }

  // ── 케이스 3·4: 강행 위반 있음 (severe / mild 분기) ──
  const severeItems = buildItemList({ missing, violation });
  const extraItems = buildItemList({ warn, ambiguous });

  const isSevere = severeTotal >= 5 || missing >= 5;
  const verb = isSevere ? '즉시 시정이 필요합니다' : '시정이 필요합니다';

  return {
    tone: isSevere ? 'severe' : 'mild',
    primary: (
      <>
        {joinList(severeItems)}의 강행규정 미준수가 발견되어{' '}
        <strong>{verb}</strong>.
      </>
    ),
    secondary:
      extraItems.length > 0 ? (
        <>이외 {joinList(extraItems)}도 함께 점검해 주세요.</>
      ) : null,
  };
}

/** 0건은 제외하고 (level, count) 리스트로 변환. */
function buildItemList(map: Partial<Record<RiskLevel, number>>): {
  level: RiskLevel;
  count: number;
}[] {
  const order: RiskLevel[] = ['missing', 'violation', 'warn', 'ambiguous'];
  return order
    .map((level) => ({ level, count: map[level] ?? 0 }))
    .filter((x) => x.count > 0);
}
