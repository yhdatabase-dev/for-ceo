import type { ReviewSummary } from '@/types/review';

interface ReportHeaderProps {
  summary: ReviewSummary;
  reportId: string;
}

/** 부처 보고서 톤 머리 — 좌측 타이틀 + 우측 메타. 하단 3중 검정선. */
export function ReportHeader({ summary, reportId }: ReportHeaderProps) {
  return (
    <header
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        paddingBottom: 14,
        borderBottom: '3px double #0A0A0A',
      }}
    >
      <div>
        <div
          style={{
            fontSize: 11,
            letterSpacing: 3,
            color: '#525252',
            textTransform: 'uppercase',
            fontWeight: 600,
          }}
        >
          노동법 자율점검 · WORK RULES REVIEW
        </div>
        <div
          style={{
            fontSize: 13,
            color: '#1F2937',
            marginTop: 6,
            fontWeight: 500,
          }}
        >
          고용노동부 표준취업규칙 DB 기반 검토 결과
        </div>
      </div>
      <div
        style={{
          fontFamily:
            'D2Coding, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
          fontSize: 11,
          color: '#1F2937',
          textAlign: 'right',
          lineHeight: 1.7,
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        <div>REPORT-ID · {reportId}</div>
        <div>발급 · {summary.reviewedAt}</div>
      </div>
    </header>
  );
}

export default ReportHeader;
