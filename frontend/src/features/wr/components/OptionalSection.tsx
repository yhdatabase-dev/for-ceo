'use client';

import { useState } from 'react';

import Icon from '@/components/ui/Icon';

import styles from './OptionalSection.module.css';

interface OptionalSectionProps {
  /** 선택 조항 개수. summary.counts.skipped 와 동기화. */
  count: number;
}

/** "선택 조항 격리" 카드 — 펼치기는 다음 단계에서 본 목록으로 연결. */
export function OptionalSection({ count }: OptionalSectionProps) {
  const [expanded, setExpanded] = useState(false);

  if (count <= 0) return null;

  return (
    <div className={styles.wrap}>
      <div className={styles.head}>
        <Icon name="info" size={16} color="var(--color-text-muted)" />
        <span className={styles.title}>
          선택 조항 {count}건은 별도 영역에 보관됨
        </span>
      </div>
      <div className={styles.desc}>
        사업장 정보로 검사 대상이 아닌 조항입니다 (예: 교대근로 미도입 → 교대근로 조항 검사 제외).
      </div>
      <button
        type="button"
        className={styles.toggle}
        onClick={() => setExpanded((v) => !v)}
      >
        {expanded ? '↑ 접기' : '선택 조항 펼쳐보기 →'}
      </button>
      {expanded && (
        <div
          style={{
            marginTop: 12,
            padding: 12,
            background: '#fff',
            borderRadius: 8,
            fontSize: 12,
            color: 'var(--color-text-subtle)',
          }}
        >
          선택 조항 목록은 다음 단계에서 백엔드 <code>optional_displays</code> 응답으로 연결됩니다.
        </div>
      )}
    </div>
  );
}

export default OptionalSection;
