/**
 * << 개정이력(Modification Information) >>
 * 수정일          수정자      수정 내용
 * ----------      ------      ---------------------------
 * 2026.05.28      kimzion77   최초 생성
 * 2026.10.01      이시영      임금명세서·노무제공자 계약서·관리자 기능 삭제
 *
 * Author: kimzion77
 * Since: 2026.05.28
 */
'use client';

import Icon, { type IconName } from '@/components/ui/Icon';
import type { DocumentType } from '@/types/review';
import styles from './DocTypePicker.module.css';

interface DocType {
  id: DocumentType;
  icon: IconName;
  title: string;
  subtitle: string;
  desc: string;
  detail: string;
  available: boolean;
  tag: string;
  /** true 면 화면에서 숨김 (코드·라우트는 유지 — 나중에 false 로 되살림). */
  hidden?: boolean;
}

export const DOC_TYPES: DocType[] = [
  {
    id: 'employment-contract',
    icon: 'contract',
    title: '근로계약서',
    subtitle: '개별 근로자 계약서',
    desc: '근로자와 체결한 근로계약서의 필수 기재사항·법정 기준을 검토합니다.',
    detail: '필수 기재 · 서면명시의무 검토',
    available: true,
    tag: '베타 운영',
  },
  {
    id: 'work-rules',
    icon: 'doc',
    title: '취업규칙',
    subtitle: '사업장 단위 근로조건 규정',
    desc: '10인 이상 사업장이 작성·신고해야 하는 취업규칙을 검토합니다.',
    detail: '근로기준법 제93조 필수기재사항 검토',
    available: true,
    tag: '베타 운영',
  },
];

interface DocTypePickerProps {
  value: DocumentType;
  onChange: (next: DocumentType) => void;
}

export function DocTypePicker({ value, onChange }: DocTypePickerProps) {
  return (
    <div className={styles.grid}>
      {DOC_TYPES.filter((d) => !d.hidden).map((d) => {
        const isSel = value === d.id;
        const disabled = !d.available;
        const classes = [
          styles.tile,
          isSel && styles.selected,
          disabled && styles.disabled,
        ]
          .filter(Boolean)
          .join(' ');

        return (
          <button
            key={d.id}
            type="button"
            onClick={() => d.available && onChange(d.id)}
            disabled={disabled}
            className={classes}
            aria-pressed={isSel}
          >
            <div className={styles.topRow}>
              <div className={styles.iconBox}>
                <Icon name={d.icon} size={20} />
              </div>
              <span className={`${styles.tag} ${d.available ? styles.tagOn : styles.tagOff}`}>
                {d.tag}
              </span>
            </div>
            <div className={styles.title}>{d.title}</div>
            <div className={styles.subtitle}>{d.subtitle}</div>
            <div className={styles.desc}>{d.desc}</div>
            <div className={styles.detail}>
              <Icon name="book" size={12} /> {d.detail}
            </div>
          </button>
        );
      })}
    </div>
  );
}

export default DocTypePicker;
