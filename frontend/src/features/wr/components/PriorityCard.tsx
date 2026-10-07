'use client';

import Card from '@/components/ui/Card';
import { RISK } from '@/styles/tokens';
import type { PriorityItem } from '@/types/review';

import styles from './PriorityCard.module.css';

interface PriorityCardProps {
  items: PriorityItem[];
  /** 클릭 시 해당 finding 상세로 이동. */
  onOpenFinding?: (id: string) => void;
}

/** 가장 먼저 시정해야 할 항목 Top 카드. */
export function PriorityCard({ items, onOpenFinding }: PriorityCardProps) {
  if (items.length === 0) return null;

  return (
    <Card padding={18}>
      <div className={styles.title}>가장 먼저 시정해야 할 항목</div>
      {items.map((t) => {
        const r = RISK[t.risk];
        return (
          <button
            key={t.id}
            type="button"
            className={styles.row}
            onClick={() => onOpenFinding?.(t.id)}
          >
            <span className={styles.dotWrap}>
              <span className={styles.dot} style={{ background: r.solid }} />
            </span>
            <div className={styles.body}>
              <div className={styles.article}>{t.article}</div>
              <div className={styles.text}>{t.title}</div>
            </div>
          </button>
        );
      })}
    </Card>
  );
}

export default PriorityCard;
