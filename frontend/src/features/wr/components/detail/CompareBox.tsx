/**
 * << 개정이력(Modification Information) >>
 * 수정일          수정자      수정 내용
 * ----------      ------      ---------------------------
 * 2026.05.28      kimzion77   최초 생성
 * 2026.10.07      이시영      화면 경로 /cgr·features 구조 이동, sync API 삭제, 업로드 원본 미저장
 *
 * Author: kimzion77
 * Since: 2026.05.28
 */
import Icon from '@/components/ui/Icon';

import styles from './CompareBox.module.css';

interface CompareRowProps {
  current: string;
  standard: string;
  /** 누락 케이스에서 "현재" 라벨 자동 변경. */
  currentLabel?: string;
}

/** 현재 ↔ 화살표 ↔ 법정 기준 3컬럼 비교. */
export function CompareRow({
  current,
  standard,
  currentLabel = '현재 사업장 규정',
}: CompareRowProps) {
  return (
    <div className={styles.row}>
      <div className={`${styles.box} ${styles.bad}`}>
        <div className={`${styles.label} ${styles.badLabel}`}>{currentLabel}</div>
        <div className={`${styles.value} ${styles.badValue}`}>{current || '-'}</div>
      </div>
      <div className={styles.arrow}>
        <Icon name="arrow" size={20} />
      </div>
      <div className={`${styles.box} ${styles.good}`}>
        <div className={`${styles.label} ${styles.goodLabel}`}>법정 기준</div>
        <div className={`${styles.value} ${styles.goodValue}`}>{standard || '-'}</div>
      </div>
    </div>
  );
}

export default CompareRow;
