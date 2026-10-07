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
