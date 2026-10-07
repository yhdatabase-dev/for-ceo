/**
 * << 개정이력(Modification Information) >>
 * 수정일          수정자      수정 내용
 * ----------      ------      ---------------------------
 * 2026.10.01      이시영      최초 생성
 *
 * Author: 이시영
 * Since: 2026.10.01
 */
// ESLint 9 flat config — Next 16 에서 `next lint` 가 제거되어 ESLint CLI 로 직접 실행한다.
import nextCoreWebVitals from 'eslint-config-next/core-web-vitals';
import nextTypescript from 'eslint-config-next/typescript';

const config = [
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    ignores: ['.next/**', 'node_modules/**', 'playwright-report/**', 'test-results/**', 'next-env.d.ts'],
  },
];

export default config;
