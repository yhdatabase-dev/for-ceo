import { REPORT_RISK, type ReportKind } from './reportTokens';

interface RiskMarkProps {
  kind: ReportKind;
  /** 시각 마크 + 텍스트 라벨 병기 (a11y) */
  withLabel?: boolean;
}

/**
 * 위험도 마크 — 흑백 인쇄용 ■(강) / ▣(중) / □(약).
 *
 * 글리프 자체로 시각 식별 + (선택) 텍스트 라벨 병기.
 */
export function RiskMark({ kind, withLabel = false }: RiskMarkProps) {
  const tier = REPORT_RISK[kind].tier;
  const glyph = tier === '강' ? '■' : tier === '중' ? '▣' : '□';
  const label = REPORT_RISK[kind].label;

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        fontVariantNumeric: 'tabular-nums',
        whiteSpace: 'nowrap',
      }}
    >
      <span
        aria-hidden
        style={{
          fontSize: 12,
          lineHeight: 1,
          color: tier === '약' ? '#8A8A8A' : '#0A0A0A',
        }}
      >
        {glyph}
      </span>
      {withLabel && (
        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: 0.4,
          }}
        >
          {label}
        </span>
      )}
    </span>
  );
}

export default RiskMark;
