'use client';

import { useState, type ReactNode } from 'react';

import Icon, { type IconName } from '@/components/ui/Icon';
import Term from '@/components/ui/Term';
import type { Finding } from '@/types/review';

import styles from './DetailTabs.module.css';

type TabKey = 'guide' | 'law' | 'context' | 'topic';

const TABS: { key: TabKey; label: string; icon: IconName }[] = [
  { key: 'guide', label: '시정 가이드', icon: 'edit' },
  { key: 'law', label: '근거 법령', icon: 'scale' },
  { key: 'context', label: '본문 위치', icon: 'quote' },
  { key: 'topic', label: '연관 주제', icon: 'book' },
];

interface DetailTabsProps {
  finding: Finding;
}

/** 시안 `screens-detail.jsx` 의 5탭 영역 — 탭 바 + 콘텐츠. */
export function DetailTabs({ finding }: DetailTabsProps) {
  const [tab, setTab] = useState<TabKey>('guide');

  return (
    <>
      <div className={styles.tabBar} role="tablist">
        {TABS.map((t) => {
          const active = tab === t.key;
          return (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={active}
              className={`${styles.tabBtn} ${active ? styles.tabBtnActive : ''}`}
              onClick={() => setTab(t.key)}
            >
              <Icon name={t.icon} size={14} />
              {t.label}
            </button>
          );
        })}
      </div>

      <div className={styles.tabPanel} role="tabpanel">
        {tab === 'guide' && <GuideTab finding={finding} />}
        {tab === 'law' && <LawTab finding={finding} />}
        {tab === 'context' && <ContextTab finding={finding} />}
        {tab === 'topic' && <TopicTab finding={finding} />}
      </div>
    </>
  );
}

/* ─── 시정 가이드 ─── */
function GuideTab({ finding }: { finding: Finding }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(finding.suggested);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  };

  return (
    <div className={styles.guideGrid}>
      <div className={styles.guideCol}>
        <Heading icon="quote" tone="muted">
          현재 본문 (수정 전)
        </Heading>
        <div className={styles.guideBoxBad}>
          {finding.quote || '본문에서 관련 규정을 찾지 못하였습니다.'}
        </div>
        <div className={styles.guideHint}>
          <strong style={{ color: '#dc2626' }}>붉은색</strong> 표시 부분이 법정 기준에 미달합니다.
        </div>
      </div>

      <div className={`${styles.guideCol} ${styles.guideColGood}`}>
        <Heading icon="check" tone="good">
          시정안 (이렇게 고쳐보세요)
        </Heading>
        <div className={styles.guideBoxGood}>{finding.suggested}</div>
        <div className={styles.guideActions}>
          <button type="button" className={styles.btnPrimary} onClick={copy}>
            <Icon name={copied ? 'check' : 'edit'} size={14} />
            {copied ? '복사됨' : '시정안 복사'}
          </button>
          <button type="button" className={styles.btnSecondary}>
            해결됨 표시
          </button>
        </div>
      </div>

      <div className={styles.guideNotice}>
        <span className={styles.guideNoticeIcon}>
          <Icon name="info" size={20} />
        </span>
        <div>
          <strong>참고:</strong> 시정안은 표준 문구 예시입니다. 사업장 상황에 맞게 다듬어
          사용하세요. 취업규칙 변경 시에는{' '}
          <Term
            def="근로자 과반수 또는 근로자대표(노조)의 의견을 듣거나 동의를 받아야 합니다. 불이익 변경의 경우 동의가 필수입니다."
            hideDelay={500}
            width={320}
          >
            근로자 의견청취
          </Term>{' '}
          절차가 필요합니다.
        </div>
      </div>
    </div>
  );
}

/* ─── 근거 법령 ─── */
function LawTab({ finding }: { finding: Finding }) {
  if (finding.laws.length === 0) {
    return <div style={{ color: 'var(--color-text-subtle)' }}>등록된 근거 법령이 없습니다.</div>;
  }
  return (
    <div className={styles.lawList}>
      {finding.laws.map((law) => (
        <div key={law.name} className={styles.lawCard}>
          <span className={styles.lawTag}>⚖ {law.name}</span>
          <div className={styles.lawBody}>{law.text}</div>
        </div>
      ))}
    </div>
  );
}

/* ─── 본문 위치 ─── */
function ContextTab({ finding }: { finding: Finding }) {
  // 인접 조 표시는 백엔드 데이터 부재로 mock 텍스트.
  return (
    <div className={styles.contextCard}>
      <Heading icon="quote" tone="muted">
        사업장 본문에서의 위치
      </Heading>
      <div className={styles.contextBody}>
        <div className={styles.contextDim}>… 이전 조의 본문이 여기에 표시됩니다.</div>
        <div className={styles.contextHighlight}>
          {finding.quote || '본문에서 관련 규정을 찾지 못하였습니다.'}
          <span className={styles.contextHighlightHint}>▲ 여기가 문제 부분입니다</span>
        </div>
        <div className={styles.contextDim}>… 다음 조의 본문이 여기에 표시됩니다.</div>
      </div>
      <div
        style={{
          marginTop: 14,
          fontSize: 11.5,
          color: 'var(--color-text-subtle)',
          lineHeight: 1.6,
        }}
      >
        실제 본문 위치는 백엔드 연동 후 전·후 조 본문이 자동으로 채워집니다.
      </div>
    </div>
  );
}

/* ─── 연관 주제 ─── */
function TopicTab({ finding }: { finding: Finding }) {
  return (
    <div className={styles.topicCard}>
      <Heading icon="book" tone="muted">
        연관 주제 ({finding.topics.length})
      </Heading>
      {finding.topics.length > 0 ? (
        <div className={styles.topicTags}>
          {finding.topics.map((t) => (
            <span key={t} className={styles.topicTag}>
              #{t}
            </span>
          ))}
        </div>
      ) : (
        <div style={{ marginTop: 14, color: 'var(--color-text-subtle)' }}>
          등록된 주제가 없습니다.
        </div>
      )}
      <div className={styles.topicHint}>
        같은 주제의 다른 조항도 함께 검토하시면 일관성 있는 규정을 만들 수 있습니다.
      </div>
    </div>
  );
}

/* ─── 공용 heading ─── */
function Heading({
  icon,
  tone,
  children,
}: {
  icon: IconName;
  tone: 'muted' | 'good';
  children: ReactNode;
}) {
  const color = tone === 'good' ? '#059669' : 'var(--color-text-muted)';
  return (
    <div className={styles.heading} style={{ color }}>
      <Icon name={icon} size={14} />
      {children}
    </div>
  );
}

export default DetailTabs;
