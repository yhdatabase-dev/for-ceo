import type { ReviewSummary } from '@/types/review';

interface ReportTitleProps {
  summary: ReviewSummary;
}

const monoFamily =
  'D2Coding, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';

const ROW: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '100px 1fr',
  alignItems: 'baseline',
  gap: 12,
};

const LABEL: React.CSSProperties = {
  fontSize: 12,
  color: '#525252',
  fontWeight: 700,
  letterSpacing: 0.2,
};

const VALUE: React.CSSProperties = {
  fontSize: 13,
  color: '#0A0A0A',
};

/** 표제 영역 — H1 + 메타 4행 (라벨 100px / 값 1fr). */
export function ReportTitle({ summary }: ReportTitleProps) {
  const excluded = summary.counts.skipped ?? 0;

  return (
    <section style={{ marginTop: 36 }}>
      <h1
        style={{
          fontSize: 36,
          fontWeight: 800,
          letterSpacing: -1,
          lineHeight: 1.25,
          margin: 0,
          color: '#0A0A0A',
        }}
      >
        취업규칙 자율점검 결과
      </h1>

      <div style={{ marginTop: 22, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={ROW}>
          <div style={LABEL}>검토 파일</div>
          <div style={VALUE}>
            {summary.fileName}{' '}
            <span style={{ color: '#525252', fontFamily: monoFamily, fontSize: 12 }}>
              ({summary.fileSize})
            </span>
          </div>
        </div>
        <div style={ROW}>
          <div style={LABEL}>검토 일시</div>
          <div style={{ ...VALUE, fontFamily: monoFamily, fontVariantNumeric: 'tabular-nums' }}>
            {summary.reviewedAt}
          </div>
        </div>
        <div style={ROW}>
          <div style={LABEL}>소요 시간</div>
          <div style={{ ...VALUE, fontFamily: monoFamily, fontVariantNumeric: 'tabular-nums' }}>
            {summary.duration}
          </div>
        </div>
        <div style={ROW}>
          <div style={LABEL}>검사 항목</div>
          <div style={{ ...VALUE, fontFamily: monoFamily, fontVariantNumeric: 'tabular-nums' }}>
            총 {summary.totalSlots}건
            {excluded > 0 && (
              <span style={{ color: '#525252', marginLeft: 6 }}>
                · 선택조항 {excluded}건 제외
              </span>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

export default ReportTitle;
