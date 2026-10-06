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
