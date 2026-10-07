import { patternForKind, type ReportKind } from './reportTokens';

interface PatternSwatchProps {
  kind: ReportKind;
  width?: number;
  height?: number;
}

/** 분포 범례/표에서 쓰는 패턴 스와치 — 16×12 기본. */
export function PatternSwatch({ kind, width = 16, height = 12 }: PatternSwatchProps) {
  return (
    <span
      aria-hidden
      style={{
        display: 'inline-block',
        width,
        height,
        border: '1px solid #0A0A0A',
        verticalAlign: 'middle',
        flexShrink: 0,
        ...patternForKind(kind),
      }}
    />
  );
}

export default PatternSwatch;
