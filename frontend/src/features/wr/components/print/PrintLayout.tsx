import type { Finding, ReviewSummary, RiskLevel } from '@/types/review';

import ReportDistribution from './ReportDistribution';
import ReportFinding from './ReportFinding';
import ReportFooter from './ReportFooter';
import ReportHeader from './ReportHeader';
import ReportPriorities from './ReportPriorities';
import ReportTitle from './ReportTitle';
import ReportVerdict from './ReportVerdict';
import styles from './PrintLayout.module.css';

interface PrintLayoutProps {
  summary: ReviewSummary;
  findings: Finding[];
}

/** 인쇄 본문에서 제외할 분류 (적정·선택). */
const EXCLUDED_FROM_PRINT: RiskLevel[] = ['ok', 'skipped'];

const ORDER: Record<RiskLevel, number> = {
  missing: 0,
  violation: 1,
  warn: 2,
  ambiguous: 3,
  ok: 4,
  skipped: 5,
};

/** REPORT-ID 생성 — fileName + reviewedAt 기반 deterministic. */
function buildReportId(summary: ReviewSummary): string {
  const ts = summary.reviewedAt.replace(/[^0-9]/g, '').slice(0, 8);
  // 간단한 해시 (charCode 합) — mock 일관성 충분
  const seed = `${summary.fileName}|${summary.reviewedAt}`;
  let h = 0;
  for (let i = 0; i < seed.length; i++) {
    h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  }
  const tail = h.toString(16).toUpperCase().padStart(4, '0').slice(-4);
  const date = `${ts.slice(0, 4)}-${ts.slice(4, 6)}-${ts.slice(6, 8)}`;
  return `RV-${date}-${tail}`;
}

/**
 * 인쇄 / PDF 전용 리포트 레이아웃 — REPORT_SPEC.md 명세 그대로.
 *
 * 화면에서는 `display: none`, `@media print` 에서만 표시.
 * 흑백 + 종이톤(#F5F4EF) 1가지 · 색 대신 패턴으로 위험도 식별.
 */
export function PrintLayout({ summary, findings }: PrintLayoutProps) {
  const reportId = buildReportId(summary);

  // 시정 필요 항목만 + 위험도 순
  const printable = findings
    .filter((f) => !EXCLUDED_FROM_PRINT.includes(f.risk))
    .sort((a, b) => ORDER[a.risk] - ORDER[b.risk]);

  return (
    <div className={styles.root} aria-hidden>
      <div className={styles.paper}>
        <ReportHeader summary={summary} reportId={reportId} />
        <ReportTitle summary={summary} />
        <ReportVerdict summary={summary} />
        <ReportDistribution summary={summary} />
        <ReportPriorities summary={summary} />

        {/* §03 지적사항 상세 — 헤딩 + 모든 finding */}
        {printable.length > 0 && (
          <section style={{ marginTop: 36 }}>
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
                  fontFamily:
                    'D2Coding, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                  fontSize: 13,
                  fontWeight: 800,
                  color: '#0A0A0A',
                  letterSpacing: 0.5,
                }}
              >
                §03
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
                지적사항 상세
              </h2>
              <span
                style={{
                  fontSize: 11,
                  color: '#525252',
                  marginLeft: 'auto',
                  fontFamily:
                    'D2Coding, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                }}
              >
                {printable.length}건 · 위험도순
              </span>
            </div>

            {printable.map((f, i) => (
              <ReportFinding key={f.id} finding={f} index={i + 1} />
            ))}
          </section>
        )}

        <ReportFooter reportId={reportId} />
      </div>
    </div>
  );
}

export default PrintLayout;
