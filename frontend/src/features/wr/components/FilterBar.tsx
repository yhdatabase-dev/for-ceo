'use client';

import Icon from '@/components/ui/Icon';
import RiskChip from '@/components/ui/RiskChip';
import type { RiskCounts, RiskLevel } from '@/types/review';

import styles from './FilterBar.module.css';

/** UI 상의 필터 — 위험도 키 또는 'all'. */
export type RiskFilter = RiskLevel | 'all';

/** 정렬 모드. */
export type SortMode = 'risk' | 'article';

interface FilterBarProps {
  counts: RiskCounts;
  filter: RiskFilter;
  onFilterChange: (next: RiskFilter) => void;
  sort: SortMode;
  onSortChange: (next: SortMode) => void;
}

/**
 * 위험도 칩 필터 + 정렬 토글.
 *
 * 0건 분류는 칩 자체를 숨겨서 신뢰도 ↑.
 * 현재 활성화된 필터는 0이어도 일시적으로 표시 (사용자가 클릭한 직후 결과가 비더라도 칩 유지).
 */
export function FilterBar({
  counts,
  filter,
  onFilterChange,
  sort,
  onSortChange,
}: FilterBarProps) {
  const toggle = (level: RiskLevel) =>
    onFilterChange(filter === level ? 'all' : level);

  const show = (level: RiskLevel) =>
    (counts[level] ?? 0) > 0 || filter === level;

  const showSevereGroup =
    show('missing') || show('violation') || show('warn') || show('ambiguous');
  const showDivider = showSevereGroup && show('ok');

  return (
    <div className={styles.bar}>
      <span className={styles.legend}>분류:</span>

      {show('missing') && (
        <RiskChip
          level="missing"
          count={counts.missing ?? 0}
          active={filter === 'missing'}
          onClick={() => toggle('missing')}
        />
      )}
      {show('violation') && (
        <RiskChip
          level="violation"
          count={counts.violation ?? 0}
          active={filter === 'violation'}
          onClick={() => toggle('violation')}
        />
      )}
      {show('warn') && (
        <RiskChip
          level="warn"
          count={counts.warn ?? 0}
          active={filter === 'warn'}
          onClick={() => toggle('warn')}
        />
      )}
      {show('ambiguous') && (
        <RiskChip
          level="ambiguous"
          count={counts.ambiguous ?? 0}
          active={filter === 'ambiguous'}
          onClick={() => toggle('ambiguous')}
        />
      )}

      {showDivider && <span className={styles.divider} />}

      {show('ok') && (
        <RiskChip
          level="ok"
          count={counts.ok ?? 0}
          active={filter === 'ok'}
          onClick={() => toggle('ok')}
        />
      )}

      <button
        type="button"
        className={`${styles.sortBtn} ${sort === 'article' ? styles.sortBtnActive : ''}`}
        onClick={() => onSortChange(sort === 'risk' ? 'article' : 'risk')}
        title="현재 정렬 토글"
      >
        <Icon name="filter" size={12} /> {sort === 'risk' ? '위험도순' : '조항순'} 정렬
      </button>
    </div>
  );
}

export default FilterBar;
