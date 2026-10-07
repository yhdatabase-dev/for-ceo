/**
 * 인쇄용 리포트 — 흑백 토큰 + 위험도 패턴.
 *
 * REPORT_SPEC.md 의 디자인 토큰을 그대로 옮긴 것.
 * **컬러 절대 금지**. 위험도는 채움 패턴으로만 식별.
 */
import type { CSSProperties } from 'react';

import type { RiskLevel } from '@/types/review';

/** 흑백 + 종이톤 1가지. 모든 인쇄 요소가 이 안에서만 변형. */
export const REPORT_TOKENS = {
  ink: '#0A0A0A',
  ink2: '#1F2937',
  gray1: '#525252', // 보조 텍스트
  gray2: '#8A8A8A', // 캡션
  gray3: '#C9C9C9', // 가는 구분선
  gray4: '#E5E5E5', // 더 가는 구분선
  paper: '#FFFFFF',
  tint: '#F5F4EF', // 인용/배경 (인쇄 시 회색)
  pageBg: '#E8E6E0',
} as const;

/** spec 의 위험도 키 — 백엔드의 RiskLevel 과 매핑한다. */
export type ReportKind = 'missing' | 'violation' | 'caution' | 'review' | 'ok';

/** backend RiskLevel → spec ReportKind. */
export function toReportKind(level: RiskLevel): ReportKind {
  switch (level) {
    case 'missing':
      return 'missing';
    case 'violation':
      return 'violation';
    case 'warn':
      return 'caution';
    case 'ambiguous':
      return 'review';
    case 'ok':
      return 'ok';
    case 'skipped':
      // 인쇄에서 skipped 는 본문 미포함이지만 키 안정성 위해 ok 로 매핑
      return 'ok';
  }
}

export const REPORT_RISK: Record<
  ReportKind,
  { label: string; tier: '강' | '중' | '약' }
> = {
  missing: { label: '누락', tier: '강' },
  violation: { label: '위반', tier: '강' },
  caution: { label: '주의', tier: '중' },
  review: { label: '검토필요', tier: '중' },
  ok: { label: '적정', tier: '약' },
};

/**
 * 위험도 → CSS 채움 패턴.
 *
 * - missing  : 솔리드 검정 (가장 강한 시각 강조)
 * - violation: 굵은 사선
 * - caution  : 가는 사선
 * - review   : 가로 줄무늬
 * - ok       : 빈칸
 */
export function patternForKind(k: ReportKind): CSSProperties {
  switch (k) {
    case 'missing':
      return { background: REPORT_TOKENS.ink };
    case 'violation':
      return {
        background: `repeating-linear-gradient(45deg, ${REPORT_TOKENS.ink} 0, ${REPORT_TOKENS.ink} 3px, white 3px, white 6px)`,
      };
    case 'caution':
      return {
        background: `repeating-linear-gradient(45deg, ${REPORT_TOKENS.gray1} 0, ${REPORT_TOKENS.gray1} 1.5px, white 1.5px, white 5px)`,
      };
    case 'review':
      return {
        background: `repeating-linear-gradient(0deg, ${REPORT_TOKENS.gray1} 0, ${REPORT_TOKENS.gray1} 1px, white 1px, white 4px)`,
      };
    case 'ok':
      return { background: 'white' };
  }
}
