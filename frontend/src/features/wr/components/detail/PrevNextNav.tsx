'use client';

import { useRouter } from 'next/navigation';

import Icon from '@/components/ui/Icon';
import type { Finding } from '@/types/review';

import styles from './PrevNextNav.module.css';
import { routes } from '@/lib/routes';

interface PrevNextNavProps {
  reviewId: string;
  prev: Finding | null;
  next: Finding | null;
  /** 1-base 현재 위치. */
  position: number;
  /** 시정 필요 총 건수. */
  total: number;
}

/** 이전 / 다음 핀딩 이동 + 인덱스 표시. */
export function PrevNextNav({
  reviewId,
  prev,
  next,
  position,
  total,
}: PrevNextNavProps) {
  const router = useRouter();
  const go = (f: Finding | null) => {
    if (!f) return;
    router.push(routes.wrFinding(reviewId, f.id));
  };

  return (
    <nav className={styles.nav} aria-label="이전·다음 지적사항">
      <button
        type="button"
        className={styles.btn}
        onClick={() => go(prev)}
        disabled={!prev}
        aria-label={prev ? `이전 지적사항: ${prev.title}` : '이전 항목 없음'}
      >
        <span className={styles.iconLeft}>
          <Icon name="arrow" size={14} />
        </span>
        <span className={styles.label}>
          <span className={styles.dir}>이전</span>
          <span className={styles.title}>
            {prev ? `${prev.article} ${prev.title}` : '— 처음 항목입니다 —'}
          </span>
        </span>
      </button>

      <span className={styles.indicator}>
        지적사항 {position} / {total}
      </span>

      <button
        type="button"
        className={`${styles.btn} ${styles.btnNext}`}
        onClick={() => go(next)}
        disabled={!next}
        aria-label={next ? `다음 지적사항: ${next.title}` : '다음 항목 없음'}
      >
        <span className={styles.label}>
          <span className={styles.dir}>다음</span>
          <span className={styles.title}>
            {next ? `${next.article} ${next.title}` : '— 마지막 항목입니다 —'}
          </span>
        </span>
        <Icon name="arrow" size={14} />
      </button>
    </nav>
  );
}

export default PrevNextNav;
