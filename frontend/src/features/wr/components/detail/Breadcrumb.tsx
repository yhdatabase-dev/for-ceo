'use client';

import { useRouter } from 'next/navigation';

import Icon from '@/components/ui/Icon';

import styles from './Breadcrumb.module.css';
import { routes } from '@/lib/routes';

interface BreadcrumbProps {
  reviewId: string;
  article: string;
  articleTitle: string;
  findingLabel: string;
}

/** 결과 페이지 › 조항 › 핀딩 ID 형태의 네비. */
export function Breadcrumb({
  reviewId,
  article,
  articleTitle,
  findingLabel,
}: BreadcrumbProps) {
  const router = useRouter();
  return (
    <div className={styles.bar}>
      <div className={styles.inner}>
        <button
          type="button"
          className={styles.backBtn}
          onClick={() => router.push(routes.wrReview(reviewId))}
        >
          <span className={styles.backIcon}>
            <Icon name="arrow" size={12} />
          </span>
          결과 페이지
        </button>
        <span className={styles.divider}>›</span>
        <span>
          {article} {articleTitle}
        </span>
        <span className={styles.divider}>›</span>
        <span className={styles.current}>{findingLabel}</span>
      </div>
    </div>
  );
}

export default Breadcrumb;
