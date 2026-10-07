'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';

import SiteHeader from '@/components/layout/SiteHeader';
import { clearAllCases, clearCase, listCases } from '@/features/history/store';
import type { DocumentType } from '@/types/review';

import styles from './page.module.css';
import { routes } from '@/lib/routes';

/**
 * 내 검토 이력 — 사업주가 지난 검토를 다시 보는 페이지.
 *
 * 데이터 — localStorage 기반 (브라우저 단위 영구 보관).
 * 사용자는 새 탭/다른 날 와도 이 페이지에서 자기 검토 목록 봄.
 *
 * 행 항목 클릭 → 결과 페이지로 라우팅 (문서종류에 따라 ec/취업규칙).
 */

const DOC_META: Record<DocumentType, { icon: string; label: string }> = {
  'work-rules': { icon: '📜', label: '취업규칙' },
  'employment-contract': { icon: '📋', label: '근로계약서' },
};

function resolveResultUrl(
  caseId: string,
  doc?: DocumentType,
): string {
  if (doc === 'employment-contract') return routes.ecReview(caseId);
  return routes.wrReview(caseId);
}

function formatDate(ts: number): string {
  if (!ts) return '—';
  const d = new Date(ts);
  return d.toLocaleString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function relativeTime(ts: number): string {
  if (!ts) return '';
  const diffMs = Date.now() - ts;
  const min = Math.floor(diffMs / 60000);
  if (min < 1) return '방금 전';
  if (min < 60) return `${min}분 전`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}시간 전`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}일 전`;
  const mo = Math.floor(d / 30);
  return `${mo}개월 전`;
}


export default function HistoryPage() {
  const [mounted, setMounted] = useState(false);
  const [cases, setCases] = useState<ReturnType<typeof listCases>>([]);
  const [confirmingClear, setConfirmingClear] = useState(false);

  useEffect(() => {
    setMounted(true);
    setCases(listCases());
  }, []);

  const grouped = useMemo(() => {
    const out: Record<string, typeof cases> = {
      'work-rules': [],
      'employment-contract': [],
    };
    for (const c of cases) {
      const k = c.documentType ?? 'work-rules';
      (out[k] ?? out['work-rules']).push(c);
    }
    return out;
  }, [cases]);

  const handleDelete = (caseId: string) => {
    if (!confirm('이 검토를 삭제하시겠습니까?')) return;
    clearCase(caseId);
    setCases(listCases());
  };

  const handleClearAll = () => {
    if (!confirmingClear) {
      setConfirmingClear(true);
      setTimeout(() => setConfirmingClear(false), 4000);
      return;
    }
    clearAllCases();
    setCases([]);
    setConfirmingClear(false);
  };

  if (!mounted) {
    return <main className={styles.page} aria-hidden />;
  }

  return (
    <main className={styles.page}>
      <SiteHeader />
      <div className={styles.container}>
        <header className={styles.header}>
          <div>
            <div className={styles.eyebrow}>내 검토 이력</div>
            <h1 className={styles.title}>지난 검토 다시 보기</h1>
            <p className={styles.subtitle}>
              이 브라우저에서 진행한 검토 {cases.length}건 — 같은 기기에서만 보입니다.
              <span className={styles.subtitleNote}>
                {' '}(서버에 저장되지 않으며 다른 기기·계정과 공유 안 됨)
              </span>
            </p>
          </div>
          <div className={styles.headerActions}>
            <Link href="/" className={styles.btnSecondary}>
              + 새 검토 시작
            </Link>
            {cases.length > 0 && (
              <button
                type="button"
                className={
                  confirmingClear ? styles.btnDangerActive : styles.btnDanger
                }
                onClick={handleClearAll}
              >
                {confirmingClear ? '⚠ 한 번 더 — 정말 삭제' : '🗑 전체 삭제'}
              </button>
            )}
          </div>
        </header>

        {cases.length === 0 ? (
          <div className={styles.emptyCard}>
            <div className={styles.emptyIcon}>📂</div>
            <div className={styles.emptyTitle}>아직 검토 이력이 없어요</div>
            <p className={styles.emptyDesc}>
              홈에서 첫 검토를 시작하면 여기에 자동으로 쌓입니다.
            </p>
            <Link href="/" className={styles.btnPrimary}>
              검토 시작하기 →
            </Link>
          </div>
        ) : (
          <>
            {(['employment-contract', 'work-rules'] as DocumentType[]).map(
              (doc) => {
                const list = grouped[doc] ?? [];
                if (list.length === 0) return null;
                const meta = DOC_META[doc];
                return (
                  <section key={doc} className={styles.section}>
                    <h2 className={styles.sectionTitle}>
                      <span className={styles.sectionIcon}>{meta.icon}</span>
                      {meta.label}
                      <span className={styles.sectionCount}>{list.length}</span>
                    </h2>
                    <ul className={styles.cardList}>
                      {list.map((c) => (
                        <li key={c.caseId} className={styles.card}>
                          <Link
                            href={resolveResultUrl(c.caseId, c.documentType)}
                            className={styles.cardBody}
                          >
                            <div className={styles.cardTitle}>
                              {c.originalFilename || '(파일명 없음)'}
                            </div>
                            <div className={styles.cardMeta}>
                              <span className={styles.cardMetaTime}>
                                {formatDate(c.doneAt || c.startedAt)}
                              </span>
                              <span className={styles.cardMetaSep}>·</span>
                              <span className={styles.cardMetaRelative}>
                                {relativeTime(c.doneAt || c.startedAt)}
                              </span>
                              <span className={styles.cardMetaSep}>·</span>
                              <StatusBadge status={c.status} />
                            </div>
                          </Link>
                          <button
                            type="button"
                            className={styles.cardDelete}
                            onClick={() => handleDelete(c.caseId)}
                            aria-label="이 검토 삭제"
                            title="삭제"
                          >
                            🗑
                          </button>
                        </li>
                      ))}
                    </ul>
                  </section>
                );
              },
            )}
          </>
        )}

        <footer className={styles.footer}>
          <p>
            💡 검토 이력은 사용자 브라우저에만 저장됩니다. 다른 기기에서 이어보려면
            결과 화면에서 <strong>📄 인쇄·PDF</strong> 로 저장해 두세요.
          </p>
        </footer>
      </div>
    </main>
  );
}


function StatusBadge({ status }: { status: 'pending' | 'done' | 'error' }) {
  const map = {
    pending: { label: '진행 중', soft: '#fef9c3', color: '#854d0e' },
    done: { label: '완료', soft: '#d1fae5', color: '#065f46' },
    error: { label: '오류', soft: '#fee2e2', color: '#991b1b' },
  } as const;
  const m = map[status] ?? map.done;
  return (
    <span
      className={styles.statusBadge}
      style={{ background: m.soft, color: m.color }}
    >
      {m.label}
    </span>
  );
}
