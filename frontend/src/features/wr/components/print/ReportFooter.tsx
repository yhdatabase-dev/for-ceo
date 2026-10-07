interface ReportFooterProps {
  reportId: string;
}

const monoFamily =
  'D2Coding, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';

/** 푸터 — 상단 2px 검정선, 좌측 안내문, 우측 REPORT-ID. */
export function ReportFooter({ reportId }: ReportFooterProps) {
  return (
    <footer
      style={{
        marginTop: 48,
        paddingTop: 14,
        borderTop: '2px solid #0A0A0A',
        display: 'grid',
        gridTemplateColumns: '1fr auto',
        gap: 24,
        alignItems: 'start',
      }}
    >
      <p
        style={{
          margin: 0,
          fontSize: 11,
          lineHeight: 1.65,
          color: '#525252',
          maxWidth: 640,
        }}
      >
        본 리포트는 자율점검 참고용입니다. 시정 시에는 근로기준법 제94조에 따른{' '}
        <strong style={{ color: '#0A0A0A', fontWeight: 700 }}>
          근로자 의견청취(과반수 동의) 절차
        </strong>
        가 필요합니다.
      </p>
      <div
        style={{
          fontFamily: monoFamily,
          fontSize: 11,
          color: '#525252',
          textAlign: 'right',
          lineHeight: 1.7,
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        <div>REPORT-ID · {reportId}</div>
      </div>
    </footer>
  );
}

export default ReportFooter;
