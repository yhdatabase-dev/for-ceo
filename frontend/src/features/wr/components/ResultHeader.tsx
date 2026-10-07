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
'use client';

import { useCallback } from 'react';
import { useRouter } from 'next/navigation';

import Button from '@/components/ui/Button';
import Icon from '@/components/ui/Icon';
import type { ReviewSummary } from '@/types/review';

import styles from './ResultHeader.module.css';

interface ResultHeaderProps {
  summary: ReviewSummary;
  /** 인쇄/PDF 다운로드 클릭 — 모두 `window.print()` 호출. */
  onPrint?: () => void;
}

/** 결과 화면 최상단 — 파일 정보 + 액션 버튼. */
export function ResultHeader({ summary, onPrint }: ResultHeaderProps) {
  const router = useRouter();

  // 직전 화면으로 — 브라우저 history 가 있으면 그쪽으로, 없으면 홈
  const handleBack = useCallback(() => {
    if (typeof window === 'undefined') {
      router.push('/');
      return;
    }
    // 같은 origin 의 referrer 가 있으면 안전하게 back, 아니면 홈
    const ref = document.referrer;
    if (ref && new URL(ref).origin === window.location.origin) {
      router.back();
    } else {
      router.push('/');
    }
  }, [router]);

  return (
    <div className={styles.bar}>
      <div className={styles.inner}>
        <button
          type="button"
          className={styles.backBtn}
          onClick={handleBack}
        >
          <span className={styles.backIcon}>
            <Icon name="arrow" size={14} />
          </span>
          이전 화면
        </button>

        <div className={styles.fileBlock}>
          <Icon name="file" size={18} color="var(--color-text-muted)" />
          <div className={styles.fileMeta}>
            <div className={styles.fileName}>{summary.fileName}</div>
            <div className={styles.fileSub}>
              {summary.fileSize} · 검토 {summary.reviewedAt} · 소요 {summary.duration}
            </div>
          </div>
        </div>

        <div className={styles.actions}>
          <Button variant="secondary" size="sm" icon="print" onClick={onPrint}>
            인쇄
          </Button>
          <Button variant="primary" size="sm" icon="download" onClick={onPrint}>
            PDF 다운로드
          </Button>
        </div>
      </div>
    </div>
  );
}

export default ResultHeader;
