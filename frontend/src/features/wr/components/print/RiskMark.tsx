/**
 * << 개정이력(Modification Information) >>
 * 수정일          수정자      수정 내용
 * ----------      ------      ---------------------------
 * 2026.05.28      kimzion77   최초 생성
 * 2026.10.07      이시영      화면 경로 /cgr·features 구조 이동, sync API 삭제, 업로드 원본 미저장
 *
 * Author: kimzion77
 * Since: 2026.05.28
 */
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
