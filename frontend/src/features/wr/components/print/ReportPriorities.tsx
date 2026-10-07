import type { ReviewSummary } from '@/types/review';

import RiskMark from './RiskMark';
import { toReportKind } from './reportTokens';

interface ReportPrioritiesProps {
  summary: ReviewSummary;
}

const monoFamily =
  'D2Coding, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';

/** §02 가장 먼저 시정해야 할 항목 — 단순 ol 리스트 (Top 3). */
export function ReportPriorities({ summary }: ReportPrioritiesProps) {
  if (summary.topPriority.length === 0) return null;

  return (
    <section style={{ marginTop: 36 }}>
      <SectionTitle no="02" title="가장 먼저 시정해야 할 항목" />

      <ol
        style={{
          listStyle: 'none',
          padding: 0,
          margin: '4px 0 0',
          borderTop: '1px solid #0A0A0A',
          borderBottom: '1px solid #0A0A0A',
        }}
      >
        {summary.topPriority.map((t, i) => (
          <li
            key={t.id}
            style={{
              display: 'grid',
              gridTemplateColumns: '60px 110px 1fr',
              alignItems: 'center',
              gap: 16,
              padding: '14px 4px',
              borderTop: i > 0 ? '1px solid #C9C9C9' : undefined,
            }}
          >
            <span
              style={{
                fontFamily: monoFamily,
                fontSize: 26,
                fontWeight: 800,
                color: '#0A0A0A',
                letterSpacing: -0.5,
              }}
            >
              {String(i + 1).padStart(2, '0')}
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <RiskMark kind={toReportKind(t.risk)} withLabel />
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, minWidth: 0 }}>
              <span
                style={{
                  fontFamily: monoFamily,
                  fontSize: 12,
                  color: '#525252',
                  fontWeight: 600,
                  letterSpacing: 0.2,
                  flexShrink: 0,
                }}
              >
                {t.article}
              </span>
              <span
                style={{
                  fontSize: 15,
                  fontWeight: 700,
                  color: '#0A0A0A',
                  lineHeight: 1.4,
                  letterSpacing: -0.1,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {t.title}
              </span>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function SectionTitle({ no, title }: { no: string; title: string }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'baseline',
        gap: 10,
        borderBottom: '1px solid #0A0A0A',
        paddingBottom: 6,
      }}
    >
      <span
        style={{
          fontFamily: monoFamily,
          fontSize: 13,
          fontWeight: 800,
          color: '#0A0A0A',
          letterSpacing: 0.5,
        }}
      >
        §{no}
      </span>
      <h2
        style={{
          fontSize: 17,
          fontWeight: 800,
          letterSpacing: -0.2,
          margin: 0,
          color: '#0A0A0A',
        }}
      >
        {title}
      </h2>
    </div>
  );
}

export default ReportPriorities;
