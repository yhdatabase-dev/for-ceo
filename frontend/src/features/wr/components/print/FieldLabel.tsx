import type { ReactNode } from 'react';

interface FieldLabelProps {
  children: ReactNode;
  emphasis?: boolean;
}

/**
 * 섹션 내부 필드 라벨 — 11px 800 uppercase letter-spacing 1
 * 좌측에 검정 마커 바(10px / emphasis 시 18px).
 */
export function FieldLabel({ children, emphasis = false }: FieldLabelProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        marginBottom: 8,
        fontSize: 11,
        fontWeight: 800,
        letterSpacing: 1,
        textTransform: 'uppercase',
        color: '#0A0A0A',
      }}
    >
      <span
        aria-hidden
        style={{
          display: 'inline-block',
          width: emphasis ? 18 : 10,
          height: 2,
          background: '#0A0A0A',
        }}
      />
      <span>{children}</span>
    </div>
  );
}

export default FieldLabel;
