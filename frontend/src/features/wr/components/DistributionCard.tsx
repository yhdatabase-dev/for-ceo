import Card from '@/components/ui/Card';
import Donut from '@/components/ui/Donut';
import { RISK, RISK_ORDER } from '@/styles/tokens';
import type { ReviewSummary } from '@/types/review';

import styles from './DistributionCard.module.css';

interface DistributionCardProps {
  summary: ReviewSummary;
}

/**
 * 위험도 분포 카드.
 *
 * 시각화(도넛) + 수치(총합·5-Bucket 카운트)를 한 카드에 모은다.
 * 적정 segment 는 의도적으로 옅게 표시해 시정 필요 항목이 도드라지게.
 */
export function DistributionCard({ summary }: DistributionCardProps) {
  const c = summary.counts;
  const totalIssues =
    (c.missing ?? 0) +
    (c.violation ?? 0) +
    (c.warn ?? 0) +
    (c.ambiguous ?? 0);

  return (
    <Card padding={18}>
      <div className={styles.title}>위험도 분포</div>

      {/* 상단: 큰 합계 + 도넛 가로 배치 */}
      <div className={styles.head}>
        <div className={styles.total}>
          <div className={styles.totalN}>{summary.totalSlots}</div>
          <div className={styles.totalL}>총 검사항목</div>
        </div>
        <div className={styles.donutWrap}>
          <Donut counts={c} size={120} thickness={13} />
          <div className={styles.donutCenter}>
            <span className={styles.donutNumber}>{totalIssues}</span>
            <span className={styles.donutLabel}>시정 필요</span>
          </div>
        </div>
      </div>

      {/* 강조 — "왜 고쳐야 하는지" 한 줄 */}
      {totalIssues > 0 && (
        <div className={styles.alert}>
          <span className={styles.alertIcon}>⚠</span>
          적정이 {c.ok ?? 0}건이지만,{' '}
          <strong>{totalIssues}건은 시정하지 않으면 과태료·벌금 대상</strong>이 될 수 있어요.
        </div>
      )}

      {/* 하단: 5-Bucket 카운트 리스트 — 0건 분류는 숨김 (신뢰도 ↑) */}
      <ul className={styles.list}>
        {RISK_ORDER.map((k) => {
          const r = RISK[k];
          const n = c[k] ?? 0;
          if (n <= 0) return null;
          return (
            <li key={k} className={styles.row}>
              <span className={styles.dot} style={{ background: r.solid }} />
              <span className={styles.name}>{r.label}</span>
              <span className={styles.count}>{n}</span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

export default DistributionCard;
