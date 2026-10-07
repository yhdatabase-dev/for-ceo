/**
 * 근로계약서 검토 4단계 진행 표시 — 모든 EC 페이지(검토·분석·계약서) 상단에 노출.
 *
 * << 개정이력(Modification Information) >>
 * 수정일          수정자      수정 내용
 * ----------      ------      ---------------------------
 * 2026.06.02      kimzion77   최초 생성
 * 2026.10.07      이시영      화면 경로 /cgr·features 구조 이동, sync API 삭제, 업로드 원본 미저장
 *
 * Author: kimzion77
 * Since: 2026.06.02
 */
'use client';

/**
 * 근로계약서 검토 4단계 진행 표시 — 모든 EC 페이지(검토·분석·계약서) 상단에 노출.
 *
 * 4단계:
 *   1. 업로드          — 파일 업로드
 *   2. 문서 정리        — OCR/구조화 결과 검토·수정
 *   3. 법령 비교 분석    — 적절·보완필요·부적절 분류 + 권고
 *   4. 표준 계약서 생성  — 결과 반영한 표준 양식 본문
 *
 * UX 원칙:
 *   - 사용자는 "내가 지금 어디쯤이고, 다음에 뭘 할지" 한눈에 봐야 함
 *   - 완료 단계는 ✓ + 채워진 원, 현재는 강조 테두리, 이후는 회색
 *   - 모바일에서는 압축된 가로 막대로 fallback
 */
import Link from 'next/link';
import styles from './StepProgress.module.css';
import { routes } from '@/lib/routes';

export type EcStep = 1 | 2 | 3 | 4;

interface StepDef {
  n: EcStep;
  title: string;
  desc: string;
  /** 이 단계로 돌아갈 수 있는 라우트 (현재보다 앞 단계만 클릭 가능). */
  hrefFor?: (reviewId: string) => string;
}

const STEPS: StepDef[] = [
  {
    n: 1,
    title: '업로드',
    desc: '파일 업로드',
    // 1단계는 홈 화면 — case 가 끝나면 돌아갈 일 없음
  },
  {
    n: 2,
    title: '문서 정리',
    desc: 'OCR·구조화 검토',
    hrefFor: (id) => routes.ecContract(id),
  },
  {
    n: 3,
    title: '법령 비교',
    desc: '적절·보완·부적절 분류',
    hrefFor: (id) => routes.ecReview(id),
  },
  {
    n: 4,
    title: '표준 계약서',
    desc: '본문 자동 작성',
    hrefFor: (id) => routes.ecPreview(id),
  },
];

interface StepProgressProps {
  /** 현재 단계 — 강조 표시 대상. */
  current: EcStep;
  /** 케이스 id — 이전 단계로 돌아가는 링크용. 없으면 텍스트 only. */
  reviewId?: string;
}

export function StepProgress({ current, reviewId }: StepProgressProps) {
  return (
    <nav className={styles.wrap} aria-label="근로계약서 검토 단계">
      <ol className={styles.list}>
        {STEPS.map((s, i) => {
          const status =
            s.n < current ? 'done' : s.n === current ? 'current' : 'todo';
          const isLink = status === 'done' && reviewId && s.hrefFor;
          const inner = (
            <>
              <span className={`${styles.circle} ${styles[`circle_${status}`]}`}>
                {status === 'done' ? '✓' : s.n}
              </span>
              <span className={styles.body}>
                <span className={styles.title}>{s.title}</span>
                <span className={styles.desc}>{s.desc}</span>
              </span>
            </>
          );
          return (
            <li
              key={s.n}
              className={`${styles.item} ${styles[`item_${status}`]}`}
            >
              {isLink ? (
                <Link
                  href={s.hrefFor!(reviewId!)}
                  className={styles.link}
                  aria-label={`${s.n}단계 ${s.title}로 돌아가기`}
                >
                  {inner}
                </Link>
              ) : (
                <span className={styles.link} aria-current={status === 'current' ? 'step' : undefined}>
                  {inner}
                </span>
              )}
              {i < STEPS.length - 1 && (
                <span
                  className={`${styles.conn} ${s.n < current ? styles.conn_done : ''}`}
                  aria-hidden="true"
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
