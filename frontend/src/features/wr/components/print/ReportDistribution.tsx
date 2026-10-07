import type { ReviewSummary } from '@/types/review';

import PatternSwatch from './PatternSwatch';
import {
  patternForKind,
  REPORT_RISK,
  REPORT_TOKENS,
  type ReportKind,
} from './reportTokens';

interface ReportDistributionProps {
  summary: ReviewSummary;
}

const monoFamily =
  'D2Coding, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';

const ORDER: ReportKind[] = ['missing', 'violation', 'caution', 'review', 'ok'];

/**
 * §01 검사항목 분포
 *
 * - 가로 스택드 바 (높이 28px, 검정 1px 외곽선) — 5단계 패턴 식별
 * - 표 형식 분포표 (구분 / 분류 / 건수 / 비중 / 막대바)
 */
export function ReportDistribution({ summary }: ReportDistributionProps) {
  const total =
    (summary.counts.missing ?? 0) +
    (summary.counts.violation ?? 0) +
    (summary.counts.warn ?? 0) +
    (summary.counts.ambiguous ?? 0) +
    (summary.counts.ok ?? 0);

  const rows = ORDER.map((kind) => {
    const backendKey =
      kind === 'caution' ? 'warn' : kind === 'review' ? 'ambiguous' : kind;
    const n = summary.counts[backendKey as keyof typeof summary.counts] ?? 0;
    const pct = total > 0 ? (n / total) * 100 : 0;
    return { kind, label: REPORT_RISK[kind].label, count: n, pct };
  });

  return (
    <section style={{ marginTop: 36 }}>
      <SectionTitle no="01" title="검사항목 분포" />

      {/* 가로 스택드 바 */}
      <div
        style={{
          marginTop: 16,
          display: 'flex',
          height: 28,
          border: `1px solid ${REPORT_TOKENS.ink}`,
        }}
      >
        {rows.map((r) =>
          r.count > 0 ? (
            <div
              key={r.kind}
              title={`${r.label}: ${r.count}건`}
              style={{
                width: `${r.pct}%`,
                ...patternForKind(r.kind),
                borderRight:
                  rows.findIndex((x) => x.count > 0 && x.kind === r.kind) <
                  rows.filter((x) => x.count > 0).length - 1
                    ? `1px solid ${REPORT_TOKENS.ink}`
                    : 'none',
              }}
            />
          ) : null,
        )}
      </div>

      {/* 범례 */}
      <div
        style={{
          marginTop: 10,
          display: 'flex',
          flexWrap: 'wrap',
          gap: '6px 16px',
          fontSize: 11.5,
          color: REPORT_TOKENS.ink2,
        }}
      >
        {rows.map((r) => (
          <span
            key={r.kind}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
          >
            <PatternSwatch kind={r.kind} />
            <span style={{ fontWeight: 600 }}>{r.label}</span>
            <span style={{ color: REPORT_TOKENS.gray1, fontFamily: monoFamily }}>
              {r.count}건
            </span>
          </span>
        ))}
      </div>

      {/* 표 형식 분포표 */}
      <table
        style={{
          marginTop: 20,
          width: '100%',
          borderCollapse: 'collapse',
          borderTop: '2px solid #0A0A0A',
          borderBottom: '1px solid #0A0A0A',
          fontSize: 12.5,
        }}
      >
        <thead>
          <tr>
            <Th width={56}>구분</Th>
            <Th>분류</Th>
            <Th width={80} align="right">
              건수
            </Th>
            <Th width={80} align="right">
              비중
            </Th>
            <Th width={220}>분포</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.kind}
              style={{ borderTop: `1px solid ${REPORT_TOKENS.gray3}` }}
            >
              <Td>
                <PatternSwatch kind={r.kind} />
              </Td>
              <Td>
                <strong style={{ fontWeight: 700 }}>{r.label}</strong>
              </Td>
              <Td align="right" mono>
                {r.count}
              </Td>
              <Td align="right" mono>
                {r.pct.toFixed(1)}%
              </Td>
              <Td>
                <div
                  style={{
                    height: 8,
                    border: '1px solid #0A0A0A',
                    width: '100%',
                    background: 'white',
                  }}
                >
                  <div
                    style={{
                      width: `${r.pct}%`,
                      height: '100%',
                      ...patternForKind(r.kind),
                    }}
                  />
                </div>
              </Td>
            </tr>
          ))}
        </tbody>
      </table>
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

function Th({
  children,
  width,
  align = 'left',
}: {
  children: React.ReactNode;
  width?: number;
  align?: 'left' | 'right';
}) {
  return (
    <th
      scope="col"
      style={{
        padding: '8px 10px',
        textAlign: align,
        fontSize: 11,
        fontWeight: 800,
        letterSpacing: 0.6,
        textTransform: 'uppercase',
        color: '#0A0A0A',
        width,
      }}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  align = 'left',
  mono = false,
}: {
  children: React.ReactNode;
  align?: 'left' | 'right';
  mono?: boolean;
}) {
  return (
    <td
      style={{
        padding: '8px 10px',
        textAlign: align,
        verticalAlign: 'middle',
        fontFamily: mono ? monoFamily : undefined,
        fontVariantNumeric: mono ? 'tabular-nums' : undefined,
      }}
    >
      {children}
    </td>
  );
}

export default ReportDistribution;
