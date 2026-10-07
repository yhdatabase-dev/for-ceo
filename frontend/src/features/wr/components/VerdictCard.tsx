'use client';

import Icon, { type IconName } from '@/components/ui/Icon';
import type { ReviewSummary } from '@/types/review';

import { buildVerdictMessage, type VerdictTone } from './VerdictMessage';
import styles from './VerdictCard.module.css';

interface VerdictCardProps {
  summary: ReviewSummary;
}

/** 톤별 스타일·아이콘 매핑 — verdictMessage 의 4단계와 1:1. */
const TONE_META: Record<
  VerdictTone,
  { cardClass: string; textClass: string; iconName: IconName; iconColor: string }
> = {
  severe: {
    cardClass: styles.severe,
    textClass: styles.severeText,
    iconName: 'alert',
    iconColor: '#dc2626',
  },
  mild: {
    cardClass: styles.mild,
    textClass: styles.mildText,
    iconName: 'warn',
    iconColor: '#ea580c',
  },
  warn: {
    cardClass: styles.warnTone,
    textClass: styles.warnText,
    iconName: 'warn',
    iconColor: '#a16207',
  },
  ok: {
    cardClass: styles.okTone,
    textClass: styles.okText,
    iconName: 'check',
    iconColor: '#16a34a',
  },
};

/** 종합 판정 카드 — 분포에 따라 톤·문구가 달라진다. */
export function VerdictCard({ summary }: VerdictCardProps) {
  const msg = buildVerdictMessage(summary.counts);
  const tone = TONE_META[msg.tone];

  return (
    <div className={`${styles.card} ${tone.cardClass}`}>
      <div className={styles.header}>
        <Icon name={tone.iconName} size={18} color={tone.iconColor} />
        <span className={`${styles.label} ${tone.textClass}`}>종합 판정</span>
      </div>
      <div className={`${styles.verdict} ${tone.textClass}`}>{summary.verdict}</div>
      <div className={styles.desc}>
        {msg.primary}
        {msg.secondary && <div className={styles.descSub}>{msg.secondary}</div>}
      </div>
    </div>
  );
}

export default VerdictCard;
