'use client';

import { useState } from 'react';

import Icon from '@/components/ui/Icon';
import RiskBadge from '@/components/ui/RiskBadge';
import { renderBold } from '@/lib/markdownBold';
import { RISK } from '@/styles/tokens';
import type { Finding, FindingStatus, LawCitation } from '@/types/review';

import styles from './FindingCard.module.css';

/** 비교 패널의 왼쪽 라벨 — 상태별로 자연스럽게 분기. */
function currentLabelFor(status: FindingStatus): string {
  switch (status) {
    case 'MISSING':
      return '본문 상태';
    case 'VIOLATION':
      return '본문 표현';
    case 'AMBIGUOUS':
      return '본문 표현';
    case 'WARN':
      return '본문 표현';
    default:
      return '본문';
  }
}

/** 신구대조표에 담을 수 있는(변경 필요) 상태. */
const ADDABLE_STATUSES = new Set<FindingStatus>([
  'VIOLATION',
  'MISSING',
  'WARN',
  'AMBIGUOUS',
]);

interface FindingCardProps {
  finding: Finding;
  /** 클릭 시 상세 페이지로 이동. */
  onOpen?: (id: string) => void;
  /** 신구대조표 담기 상태 — 제공 시 카드에 '담기' 버튼 노출(변경 필요 항목만). */
  added?: boolean;
  onToggleAdd?: (id: string) => void;
}

/**
 * 핀딩 카드 — 시안 `FindingCard` (split variant) 이식.
 *
 * 헤더 → 제목 → 사유/인용 가로 분할 → 시정 가이드 강조 박스.
 */
export function FindingCard({ finding, onOpen, added, onToggleAdd }: FindingCardProps) {
  const r = RISK[finding.risk];
  const [copied, setCopied] = useState(false);
  const canAdd = ADDABLE_STATUSES.has(finding.status);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(finding.suggested);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      // clipboard API 미지원 환경 — 무시
    }
  };

  return (
    <article className={styles.card} style={{ borderLeftColor: r.solid }}>
      {/* 헤더 */}
      <div className={styles.header}>
        <RiskBadge level={finding.risk} />
        <span className={styles.artInfo}>
          {finding.article} {finding.articleTitle}
        </span>
        <button
          type="button"
          className={styles.detailBtn}
          onClick={() => onOpen?.(finding.id)}
        >
          상세 <Icon name="chevron" size={12} />
        </button>
      </div>

      <h3 className={styles.title}>{finding.title}</h3>

      {/* 가로 분할: 사유 ↔ 인용 */}
      <div className={styles.split}>
        <div className={styles.splitLeft}>
          <div className={styles.sectionHead}>
            <Icon name="info" size={14} color={r.solid} />
            <span className={styles.sectionLabel}>왜 이게 문제인가요?</span>
          </div>
          <div className={styles.reason}>{renderBold(finding.reason)}</div>

          {(finding.extracted || finding.standard) && (
            <div className={styles.compare}>
              <div className={styles.compareCol}>
                <div className={styles.compareLabel}>{currentLabelFor(finding.status)}</div>
                <div
                  className={styles.compareValue}
                  style={{ color: finding.status === 'MISSING' ? '#475569' : r.solid }}
                >
                  {finding.extracted || (finding.status === 'MISSING' ? '관련 규정 미기재' : '-')}
                </div>
              </div>
              <div className={styles.compareDivider} />
              <div className={styles.compareCol}>
                <div className={styles.compareLabel}>법정 기준</div>
                <div className={styles.compareValue} style={{ color: '#047857' }}>
                  {finding.standard || '-'}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className={styles.splitRight}>
          <div className={styles.sectionHead}>
            <Icon name="quote" size={14} color="var(--color-text-muted)" />
            <span className={styles.sectionLabel}>사업장 본문 인용</span>
          </div>
          {finding.quote ? (
            <div className={styles.quote}>{finding.quote}</div>
          ) : (
            <div className={`${styles.quote} ${styles.quoteEmpty}`}>
              본문에서 관련 규정을 찾지 못하였습니다.
            </div>
          )}
        </div>
      </div>

      {/* 시정 가이드 */}
      <div className={styles.fix}>
        <div className={styles.sectionHead}>
          <span className={styles.fixBadge}>
            <Icon name="check" size={11} strokeWidth={2.5} />
          </span>
          <span className={styles.fixLabel}>이렇게 고쳐 보세요</span>
        </div>
        <div className={styles.fixBox}>{finding.suggested}</div>
        <div className={styles.fixFooter}>
          <div className={styles.lawTags}>
            {finding.laws.map((law) => (
              <LawChip key={law.name} law={law} />
            ))}
          </div>
          <div className={styles.fixActions}>
            {onToggleAdd && canAdd && (
              <button
                type="button"
                className={`${styles.addBtn} ${added ? styles.addBtnOn : ''}`}
                onClick={() => onToggleAdd(finding.id)}
                aria-pressed={added}
              >
                <Icon name="check" size={12} strokeWidth={2.5} />
                {added ? '담음' : '신구대조표에 담기'}
              </button>
            )}
            <button type="button" className={styles.copyBtn} onClick={copy}>
              <Icon name={copied ? 'check' : 'edit'} size={12} />
              {copied ? '복사됨' : '복사하기'}
            </button>
          </div>
        </div>
      </div>

      {/* 벌칙 분리 — 미기재(omission) / 법령 위반(violation) */}
      {finding.penalty &&
        (finding.penalty.omission.length > 0 ||
          finding.penalty.violation.length > 0) && (
          <div className={styles.penalty}>
            {finding.penalty.omission.length > 0 && (
              <div className={styles.penaltyBlock}>
                <span className={`${styles.penaltyTag} ${styles.penaltyTagOmission}`}>
                  📋 취업규칙 미기재 시
                </span>
                <ul className={styles.penaltyList}>
                  {finding.penalty.omission.map((p, i) => (
                    <li key={i}>{p}</li>
                  ))}
                </ul>
              </div>
            )}
            {finding.penalty.violation.length > 0 && (
              <div className={styles.penaltyBlock}>
                <span className={`${styles.penaltyTag} ${styles.penaltyTagViolation}`}>
                  ⚖️ 법령 내용 위반 시
                </span>
                <ul className={styles.penaltyList}>
                  {finding.penalty.violation.map((p, i) => (
                    <li key={i}>{p}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
    </article>
  );
}

/** 법령 칩 — 호버 시 popover 로 법령 본문/요약을 노출. */
function LawChip({ law }: { law: LawCitation }) {
  return (
    <span className={styles.lawTagWrap} tabIndex={0}>
      <span className={styles.lawTag}>⚖ {law.name}</span>
      <span className={styles.lawTip} role="tooltip">
        <span className={styles.lawTipName}>{law.name}</span>
        <span className={styles.lawTipBody}>{law.text}</span>
      </span>
    </span>
  );
}

export default FindingCard;
