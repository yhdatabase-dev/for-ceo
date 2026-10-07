/**
 * << 개정이력(Modification Information) >>
 * 수정일          수정자      수정 내용
 * ----------      ------      ---------------------------
 * 2026.05.28      kimzion77   최초 생성
 * 2026.10.06      이시영      PostgreSQL 전환, 노무가이드 삭제
 *
 * Author: kimzion77
 * Since: 2026.05.28
 */
import Link from 'next/link';

import Icon from '@/components/ui/Icon';
import styles from './SiteHeader.module.css';

/** 공통 상단 헤더. */
export function SiteHeader() {
  return (
    <header className={`${styles.header} noPrint`}>
      <Link href="/" className={styles.brand} aria-label="홈으로">
        <div className={styles.logo}>
          <Icon name="shield" size={18} />
        </div>
        <div>
          <div className={styles.title}>노동법 자율점검</div>
          <div className={styles.subtitle}>고용노동부 DB 기반</div>
        </div>
      </Link>
      <div className={styles.nav}>
        <Link href="/history" className={styles.navLink}>
          내 검토
        </Link>
        <span className={styles.anonChip}>익명 사용 중</span>
      </div>
    </header>
  );
}

export default SiteHeader;
