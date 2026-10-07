import { renderBold } from '@/lib/markdownBold';
import type { Finding } from '@/types/review';

import FieldLabel from './FieldLabel';
import { REPORT_RISK, REPORT_TOKENS, toReportKind } from './reportTokens';

interface ReportFindingProps {
  finding: Finding;
  /** 본문 일련번호 (1 부터). 표지 우선순위와 매칭. */
  index: number;
}

const monoFamily =
  'D2Coding, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';

/**
 * §03 지적사항 상세 — 단일 finding 카드.
 *
 * REPORT_SPEC §4.6 의 8단계 흐름:
 *  헤더 → 제목 → 사유 → 본문 vs 법정 → 인용 → 시정안 → 근거 법령 → 벌칙
 */
export function ReportFinding({ finding, index }: ReportFindingProps) {
  const kind = toReportKind(finding.risk);
  const riskLabel = REPORT_RISK[kind].label;
  const number = String(index).padStart(2, '0');

  return (
    <article
      style={{
        marginTop: 28,
        breakInside: 'avoid',
        pageBreakInside: 'avoid',
      }}
    >
      {/* 1. 헤더 — 번호 검정 채움 + 라벨 + 조항 */}
      <header style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 38,
            height: 28,
            background: REPORT_TOKENS.ink,
            color: '#FFF',
            fontFamily: monoFamily,
            fontSize: 14,
            fontWeight: 800,
            letterSpacing: 0.5,
          }}
        >
          {number}
        </span>
        <span
          style={{
            fontSize: 11,
            fontWeight: 800,
            letterSpacing: 1,
            textTransform: 'uppercase',
            color: REPORT_TOKENS.ink,
            padding: '4px 8px',
            border: `1px solid ${REPORT_TOKENS.ink}`,
          }}
        >
          {riskLabel}
        </span>
        <span
          style={{
            fontFamily: monoFamily,
            fontSize: 12.5,
            color: REPORT_TOKENS.gray1,
            fontWeight: 600,
          }}
        >
          {finding.article} {finding.articleTitle}
        </span>
      </header>

      {/* 2. 제목 — H3 24px 800 + 하단 1px 회색선 */}
      <h3
        style={{
          fontSize: 24,
          fontWeight: 800,
          lineHeight: 1.35,
          letterSpacing: -0.5,
          color: REPORT_TOKENS.ink,
          margin: '14px 0 16px',
          paddingBottom: 16,
          borderBottom: `1px solid ${REPORT_TOKENS.gray3}`,
        }}
      >
        {finding.title}
      </h3>

      {/* 3. 왜 이게 문제인가요? */}
      <div style={{ marginTop: 24, breakInside: 'avoid' }}>
        <FieldLabel>왜 이게 문제인가요?</FieldLabel>
        <div
          style={{
            fontSize: 14.5,
            lineHeight: 1.8,
            color: REPORT_TOKENS.ink,
          }}
        >
          {renderBold(finding.reason)}
        </div>
      </div>

      {/* 4. 본문 vs 법정 기준 — 2행 표 */}
      {(finding.extracted || finding.standard) && (
        <table
          style={{
            marginTop: 24,
            width: '100%',
            borderCollapse: 'collapse',
            border: `1px solid ${REPORT_TOKENS.ink}`,
            breakInside: 'avoid',
            fontSize: 13.5,
          }}
        >
          <tbody>
            <tr>
              <th
                scope="row"
                style={{
                  width: 120,
                  background: REPORT_TOKENS.tint,
                  borderRight: `1px solid ${REPORT_TOKENS.ink}`,
                  padding: '10px 12px',
                  textAlign: 'left',
                  fontSize: 11,
                  fontWeight: 800,
                  letterSpacing: 0.5,
                  textTransform: 'uppercase',
                  color: REPORT_TOKENS.ink,
                }}
              >
                본문 표현
              </th>
              <td
                style={{
                  padding: '10px 14px',
                  color: REPORT_TOKENS.gray1,
                  textDecoration: 'line-through',
                  textDecorationColor: REPORT_TOKENS.gray2,
                }}
              >
                {finding.extracted ||
                  (finding.status === 'MISSING' ? '관련 규정 미기재' : '-')}
              </td>
            </tr>
            <tr style={{ borderTop: `1px solid ${REPORT_TOKENS.ink}` }}>
              <th
                scope="row"
                style={{
                  background: REPORT_TOKENS.tint,
                  borderRight: `1px solid ${REPORT_TOKENS.ink}`,
                  padding: '10px 12px',
                  textAlign: 'left',
                  fontSize: 11,
                  fontWeight: 800,
                  letterSpacing: 0.5,
                  textTransform: 'uppercase',
                  color: REPORT_TOKENS.ink,
                }}
              >
                법정 기준
              </th>
              <td
                style={{
                  padding: '10px 14px',
                  color: REPORT_TOKENS.ink,
                  fontWeight: 700,
                }}
              >
                {finding.standard || '-'}
              </td>
            </tr>
          </tbody>
        </table>
      )}

      {/* 5. 사업장 본문 인용 */}
      <div style={{ marginTop: 24, breakInside: 'avoid' }}>
        <FieldLabel>사업장 본문 인용</FieldLabel>
        <blockquote
          style={{
            margin: 0,
            background: REPORT_TOKENS.tint,
            borderLeft: `4px solid ${REPORT_TOKENS.ink}`,
            padding: '14px 16px',
            fontFamily: monoFamily,
            fontSize: 12.5,
            lineHeight: 1.7,
            color: REPORT_TOKENS.ink,
            whiteSpace: 'pre-wrap',
          }}
        >
          {finding.quote || '본문에서 관련 규정을 찾지 못하였습니다.'}
        </blockquote>
      </div>

      {/* 6. 이렇게 고쳐 보세요 */}
      <div style={{ marginTop: 24, breakInside: 'avoid' }}>
        <FieldLabel emphasis>이렇게 고쳐 보세요</FieldLabel>
        <div
          style={{
            border: `2px solid ${REPORT_TOKENS.ink}`,
            padding: '14px 16px',
            fontFamily: monoFamily,
            fontSize: 13,
            lineHeight: 1.75,
            color: REPORT_TOKENS.ink,
            whiteSpace: 'pre-wrap',
          }}
        >
          {finding.suggested}
        </div>
      </div>

      {/* 7. 근거 법령 */}
      {finding.laws.length > 0 && (
        <div style={{ marginTop: 24, breakInside: 'avoid' }}>
          <FieldLabel>근거 법령</FieldLabel>
          <ul
            style={{
              listStyle: 'none',
              margin: 0,
              padding: 0,
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
            }}
          >
            {finding.laws.map((law) => (
              <li
                key={law.name}
                style={{
                  border: `1px solid ${REPORT_TOKENS.gray3}`,
                  padding: '10px 12px',
                  fontSize: 12.5,
                  lineHeight: 1.6,
                  color: REPORT_TOKENS.ink,
                }}
              >
                <strong
                  style={{
                    fontWeight: 800,
                    fontFamily: monoFamily,
                    letterSpacing: 0.2,
                  }}
                >
                  {law.name}
                </strong>
                <span
                  style={{
                    color: REPORT_TOKENS.gray2,
                    margin: '0 8px',
                    letterSpacing: 2,
                  }}
                >
                  ·····
                </span>
                <span>{law.text}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 8. 벌칙 — omission / violation 분리 */}
      {finding.penalty &&
        (finding.penalty.omission.length > 0 ||
          finding.penalty.violation.length > 0) && (
          <div style={{ marginTop: 24, breakInside: 'avoid' }}>
            <FieldLabel>벌칙</FieldLabel>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr',
                gap: 8,
              }}
            >
              {finding.penalty.omission.length > 0 && (
                <PenaltyBlock label="취업규칙 미기재 시" items={finding.penalty.omission} />
              )}
              {finding.penalty.violation.length > 0 && (
                <PenaltyBlock label="법령 내용 위반 시" items={finding.penalty.violation} />
              )}
            </div>
          </div>
        )}
    </article>
  );
}

function PenaltyBlock({ label, items }: { label: string; items: string[] }) {
  return (
    <div
      style={{
        border: `1px solid ${REPORT_TOKENS.ink}`,
        display: 'grid',
        gridTemplateColumns: '90px 1fr',
        alignItems: 'stretch',
      }}
    >
      <div
        style={{
          background: REPORT_TOKENS.ink,
          color: '#FFF',
          padding: '10px 8px',
          fontFamily: monoFamily,
          fontSize: 10.5,
          fontWeight: 800,
          letterSpacing: 1,
          textAlign: 'center',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        PENALTY
      </div>
      <div style={{ padding: '10px 14px' }}>
        <div
          style={{
            fontSize: 11.5,
            fontWeight: 700,
            color: REPORT_TOKENS.ink,
            marginBottom: 6,
          }}
        >
          {label}
        </div>
        <ul
          style={{
            margin: 0,
            paddingLeft: 16,
            fontSize: 12,
            lineHeight: 1.6,
            color: REPORT_TOKENS.ink2,
          }}
        >
          {items.map((p, i) => (
            <li key={i}>{p}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export default ReportFinding;
