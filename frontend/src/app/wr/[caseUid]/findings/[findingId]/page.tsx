'use client';

import { useMemo, use } from 'react';
import Link from 'next/link';

import RiskBadge from '@/components/ui/RiskBadge';

import Breadcrumb from '@/features/wr/components/detail/Breadcrumb';
import CompareRow from '@/features/wr/components/detail/CompareBox';
import DetailTabs from '@/features/wr/components/detail/DetailTabs';
import PrevNextNav from '@/features/wr/components/detail/PrevNextNav';

import { SAMPLE_RESULT } from '@/data/sample';
import { getCase } from '@/features/history/store';
import { renderBold } from '@/lib/markdownBold';
import type { ReviewResult, RiskLevel } from '@/types/review';

import styles from './page.module.css';
import { routes } from '@/lib/routes';

/** 시정 필요 finding 만 노출 (적정·선택 제외). */
const EXCLUDED: RiskLevel[] = ['ok', 'skipped'];

const ORDER: Record<RiskLevel, number> = {
  missing: 0,
  violation: 1,
  warn: 2,
  ambiguous: 3,
  ok: 4,
  skipped: 5,
};

/**
 * 핀딩 상세 화면 — 시안 `screens-detail.jsx` 이식.
 *
 * Breadcrumb / 헤더 + reason / Compare 박스 / 5탭 / 이전·다음.
 * mock 동작 (SAMPLE_RESULT). 백엔드 연동 시 `GET /api/review/{id}/findings/{findingId}` 로 교체.
 */
export default function FindingDetailPage(
  props: {
    params: Promise<{ caseUid: string; findingId: string }>;
  }
) {
  const params = use(props.params);
  // store 에서 실제 결과 로드, 없으면 mock fallback.
  // 근로계약서(EC) 핀딩은 별도 페이지에서 다룰 예정 — 여기는 취업규칙 결과만.
  const reviewResult = useMemo<ReviewResult>(() => {
    if (params.caseUid === 'demo') return SAMPLE_RESULT;
    const entry = getCase(params.caseUid);
    if (entry?.status === 'done' && entry.result?.doc === 'work-rules') {
      return entry.result.data;
    }
    return SAMPLE_RESULT;
  }, [params.caseUid]);

  const { findings } = reviewResult;

  // 시정 필요 항목만 + 위험도 순으로 정렬 — 결과 페이지의 carousel·인쇄 순서와 동일
  const list = [...findings]
    .filter((f) => !EXCLUDED.includes(f.risk))
    .sort((a, b) => ORDER[a.risk] - ORDER[b.risk]);

  const idx = list.findIndex((f) => f.id === params.findingId);
  const finding = idx >= 0 ? list[idx] : null;

  if (!finding) {
    return (
      <main className={styles.page}>
        <div className={styles.container}>
          <div className={styles.notFound}>
            <div className={styles.notFoundTitle}>지적사항을 찾을 수 없습니다</div>
            <div className={styles.notFoundDesc}>
              요청하신 ID <code>{params.findingId}</code> 가 결과에 없습니다.
            </div>
            <Link href={routes.wrReview(params.caseUid)} className={styles.notFoundLink}>
              ← 결과 페이지로 돌아가기
            </Link>
          </div>
        </div>
      </main>
    );
  }

  const prev = idx > 0 ? list[idx - 1] : null;
  const next = idx < list.length - 1 ? list[idx + 1] : null;

  const currentLabel =
    finding.status === 'MISSING' ? '본문 상태' : '현재 사업장 규정';

  return (
    <main className={styles.page}>
      <Breadcrumb
        reviewId={params.caseUid}
        article={finding.article}
        articleTitle={finding.articleTitle}
        findingLabel={`${finding.article} ${finding.articleTitle}`}
      />

      <div className={styles.container}>
        {/* 헤더 */}
        <div className={styles.head}>
          <RiskBadge level={finding.risk} />
          <span className={styles.headMeta}>
            · {finding.article} {finding.articleTitle}
          </span>
        </div>
        <h1 className={styles.title}>{finding.title}</h1>
        <p className={styles.reason}>{renderBold(finding.reason)}</p>

        {/* 비교 박스 */}
        {(finding.extracted || finding.standard) && (
          <CompareRow
            current={
              finding.extracted ||
              (finding.status === 'MISSING' ? '관련 규정 미기재' : '-')
            }
            standard={finding.standard}
            currentLabel={currentLabel}
          />
        )}

        {/* 5개 탭 */}
        <DetailTabs finding={finding} />

        {/* 이전 / 다음 */}
        <PrevNextNav
          reviewId={params.caseUid}
          prev={prev}
          next={next}
          position={idx + 1}
          total={list.length}
        />
      </div>
    </main>
  );
}
