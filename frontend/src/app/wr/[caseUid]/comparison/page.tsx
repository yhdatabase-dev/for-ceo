'use client';

// 프로그램명세서 WR-003-01 신구대조표 확인: 화면 URL /cgr/wr/[caseUid]/comparison (기존: /review/[id]/wr/contract)

import { useEffect, useState, use } from 'react';
import Link from 'next/link';

import SiteHeader from '@/components/layout/SiteHeader';
import WrComparisonView from '@/features/wr/components/WrComparisonView';
import { getCase } from '@/features/history/store';

import styles from './page.module.css';
import { routes } from '@/lib/routes';

/**
 * 취업규칙 — **신구대조표** 페이지.
 *
 * 취업규칙은 근로계약서/임금명세서와 달리 '표준 초안'이 아니라, 검토에서 발견된
 * 개정 필요 조항을 **개정 전 | 개정 후 | 비고** 로 정리한 신구대조표가 결과물이다.
 * (문서/텍스트 보기 토글은 제거 — 신구대조표 단일 화면.)
 *
 * 데이터는 검토 결과 findings 에서 결정적으로 구성한다(WrComparisonView).
 */
export default function WrContractPage(props: { params: Promise<{ caseUid: string }> }) {
  const params = use(props.params);
  const caseId = params.caseUid;

  const [mounted, setMounted] = useState(false);
  const [entry, setEntry] = useState<ReturnType<typeof getCase>>(null);

  useEffect(() => {
    setMounted(true);
    setEntry(getCase(caseId));
  }, [caseId]);

  if (!mounted) {
    return <main className={styles.page} aria-hidden />;
  }

  const result = entry?.result;

  // 결과 화면에서 '담은' 수정안(wr.userOverrides)이 있으면 그 항목만, 개정 후 칸을 담은
  // 수정안으로 채워 신구대조표를 구성. 담은 게 없으면(레거시/바로 진입) 전 지적 항목으로 폴백.
  const overrides = entry?.wr?.userOverrides ?? {};
  const collectedIds = Object.keys(overrides);
  const allFindings =
    result && result.doc === 'work-rules' ? result.data.findings : [];
  const findings =
    collectedIds.length > 0
      ? allFindings
          .filter((f) => overrides[f.id] !== undefined)
          .map((f) => ({ ...f, suggested: overrides[f.id] || f.suggested }))
      : allFindings;

  if (!result || result.doc !== 'work-rules') {
    return (
      <main className={styles.page}>
        <SiteHeader />
        <div className={styles.containerSimple}>
          <div className={styles.notFound}>
            <h1>검토 결과가 없습니다</h1>
            <p>
              <Link href={routes.wrReview(caseId)}>← 검토 결과로 돌아가기</Link>
            </p>
          </div>
        </div>
      </main>
    );
  }

  const filename = (entry?.originalFilename || '취업규칙').replace(
    /\.(png|jpe?g|pdf|docx?|hwpx?|txt)$/i,
    '',
  );

  return (
    <main className={styles.page}>
      <SiteHeader />
      <div className={styles.layout}>
        <header className={styles.topbar}>
          <div className={styles.topbarLeft}>
            <span className={styles.eyebrow}>취업규칙 · 신구대조표</span>
            <h1 className={styles.title}>취업규칙 신구대조표</h1>
            <p className={styles.subtitle}>
              검토에서 발견된 개정 필요 조항을 개정 전·후로 정리했습니다. 칸을 클릭하면
              직접 고칠 수 있어요.
            </p>
          </div>
          <div className={`${styles.topbarRight} noPrint`}>
            <Link href={routes.wrReview(caseId)} className={styles.btnSecondary}>
              ← 결과로
            </Link>
          </div>
        </header>

        <WrComparisonView findings={findings} filename={filename} />

        <footer className={styles.footer}>
          <span className={styles.footerNote}>
            ⚠️ 취업규칙 변경은 근로자 과반수 의견 청취·동의 등 법정 절차를 거쳐 확정하세요.
            다운로드 시 <strong>의견청취서 양식</strong>이 신구대조표 뒤에 함께 포함됩니다.
          </span>
        </footer>
      </div>
    </main>
  );
}
