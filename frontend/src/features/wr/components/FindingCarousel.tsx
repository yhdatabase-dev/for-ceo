'use client';

import { useCallback, useEffect, useState } from 'react';

import Icon from '@/components/ui/Icon';
import type { Finding } from '@/types/review';

import FindingCard from './FindingCard';
import styles from './FindingCarousel.module.css';

interface FindingCarouselProps {
  findings: Finding[];
  /** 클릭 시 상세 라우팅. */
  onOpen?: (id: string) => void;
  /** 신구대조표 담기 상태 맵(finding id → 담음 여부) + 토글 — 제공 시 카드에 담기 버튼 노출. */
  addedMap?: Record<string, boolean>;
  onToggleAdd?: (id: string) => void;
}

/**
 * 핀딩 카드 carousel — 한 번에 한 장씩 좌/우로 넘김.
 *
 * - ◀ / ▶ 버튼 + N/M 인덱스 + 하단 dot jump
 * - 키보드 ← / → 화살표로 이동
 * - findings 가 갱신되면(필터 변경 등) 첫 카드로 리셋
 */
export function FindingCarousel({
  findings,
  onOpen,
  addedMap,
  onToggleAdd,
}: FindingCarouselProps) {
  const [idx, setIdx] = useState(0);
  const total = findings.length;

  // findings 변경 → 첫 카드로
  useEffect(() => {
    setIdx(0);
  }, [findings]);

  const go = useCallback(
    (delta: number) => {
      setIdx((i) => Math.min(Math.max(0, i + delta), Math.max(0, total - 1)));
    },
    [total],
  );

  // 키보드 ← / →
  useEffect(() => {
    if (total === 0) return;
    const handler = (e: KeyboardEvent) => {
      // 입력 필드에서는 비활성
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        go(-1);
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        go(1);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [go, total]);

  if (total === 0) {
    return (
      <div className={styles.empty}>
        선택한 분류에 해당하는 항목이 없습니다.
      </div>
    );
  }

  const safeIdx = Math.min(idx, total - 1);
  const current = findings[safeIdx];
  const isFirst = safeIdx === 0;
  const isLast = safeIdx === total - 1;

  return (
    <div className={styles.wrap}>
      {/* 카드 + 좌우 floating 화살표 */}
      <div className={styles.stage}>
        <button
          type="button"
          className={`${styles.navBtn} ${styles.prev}`}
          onClick={() => go(-1)}
          disabled={isFirst}
          aria-label="이전 항목"
        >
          <Icon name="chevron" size={20} />
        </button>

        <div key={current.id} className={styles.cardEnter}>
          <FindingCard
            finding={current}
            onOpen={onOpen}
            added={!!addedMap?.[current.id]}
            onToggleAdd={onToggleAdd}
          />
        </div>

        <button
          type="button"
          className={`${styles.navBtn} ${styles.next}`}
          onClick={() => go(1)}
          disabled={isLast}
          aria-label="다음 항목"
        >
          <Icon name="chevron" size={20} />
        </button>
      </div>

      <div className={styles.footer}>
        <div className={styles.indicator} aria-live="polite">
          <span className={styles.indicatorCurrent}>{safeIdx + 1}</span>
          <span className={styles.indicatorTotal}> / {total}</span>
        </div>

        {total > 1 && total <= 25 && (
          <div className={styles.dots} role="tablist" aria-label="항목 점프">
            {findings.map((f, i) => (
              <button
                key={f.id}
                type="button"
                className={`${styles.dot} ${i === safeIdx ? styles.dotActive : ''}`}
                onClick={() => setIdx(i)}
                aria-label={`${i + 1}번 항목으로 이동`}
                aria-selected={i === safeIdx}
                role="tab"
              />
            ))}
          </div>
        )}

        <div className={styles.hint}>
          <span className={styles.kbd}>←</span>
          <span className={styles.kbd}>→</span>
          키로도 넘길 수 있습니다
        </div>
      </div>
    </div>
  );
}

export default FindingCarousel;
