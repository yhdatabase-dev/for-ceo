import type { ReviewSummary } from '@/types/review';

interface ReportVerdictProps {
  summary: ReviewSummary;
}

const monoFamily =
  'D2Coding, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';

/** 종합 판정 박스 — 2px 검정 외곽선. 좌측 큰 활자, 우측 카운트 요약. */
export function ReportVerdict({ summary }: ReportVerdictProps) {
  const m = summary.counts.missing ?? 0;
  const v = summary.counts.violation ?? 0;
  const w = summary.counts.warn ?? 0;
  const a = summary.counts.ambiguous ?? 0;

  const severeTotal = m + v;
  const totalIssues = m + v + w + a;

  // 영문 보조
  const en = totalIssues === 0 ? 'COMPLIANT' : 'NON-COMPLIANT';

  // 우측 헤드라인
  const headline =
    severeTotal > 0
      ? `강행규정 미준수 항목 ${severeTotal}건이 발견되어 즉시 시정이 필요합니다`
      : w + a > 0
        ? `강행규정 위반은 없으나 점검 권장 항목 ${w + a}건이 있습니다`
        : '법정 기준에 모두 부합합니다';

  return (
    <section
      style={{
        marginTop: 28,
        border: '2px solid #0A0A0A',
        display: 'grid',
        gridTemplateColumns: '220px 1fr',
        alignItems: 'stretch',
      }}
    >
      {/* 좌측 — 종합 판정 */}
      <div
        style={{
          padding: '22px 24px',
          borderRight: '1px solid #0A0A0A',
        }}
      >
        <div
          style={{
            fontSize: 11,
            fontWeight: 800,
            letterSpacing: 3,
            color: '#525252',
            textTransform: 'uppercase',
          }}
        >
          종합 판정
        </div>
        <div
          style={{
            fontSize: 44,
            fontWeight: 800,
            lineHeight: 1.1,
            color: '#0A0A0A',
            marginTop: 6,
            letterSpacing: -1.5,
          }}
        >
          {summary.verdict}
        </div>
        <div
          style={{
            fontSize: 11,
            color: '#525252',
            fontFamily: monoFamily,
            marginTop: 6,
            letterSpacing: 1,
          }}
        >
          {en}
        </div>
      </div>

      {/* 우측 — 헤드라인 + 카운트 */}
      <div
        style={{
          padding: '22px 24px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          gap: 10,
        }}
      >
        <div
          style={{
            fontSize: 15,
            lineHeight: 1.55,
            color: '#0A0A0A',
            fontWeight: 600,
          }}
        >
          {headline}
        </div>
        <div
          style={{
            fontSize: 12.5,
            color: '#1F2937',
            fontFamily: monoFamily,
            fontVariantNumeric: 'tabular-nums',
            letterSpacing: 0.2,
          }}
        >
          누락 {m}건 · 위반 {v}건 · 주의 {w}건 · 검토필요 {a}건
        </div>
      </div>
    </section>
  );
}

export default ReportVerdict;
