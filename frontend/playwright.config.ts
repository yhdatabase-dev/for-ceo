/**
 * Playwright E2E 스모크 설정.
 *
 * << 개정이력(Modification Information) >>
 * 수정일          수정자      수정 내용
 * ----------      ------      ---------------------------
 * 2026.07.08      kimzion77   최초 생성
 * 2026.10.07      이시영      환경설정 통합 (루트 .env·config.py), mock LLM 추가
 * 2026.10.07      이시영      검토번호 서버 발급, 변경 사유 주석 추가
 *
 * Author: kimzion77
 * Since: 2026.07.08
 */
/**
 * Playwright E2E 스모크 설정.
 *
 * - 로컬: 이미 떠 있는 dev 서버(CGR_FRONTEND_PORT, 기본 18091)를 재사용, 없으면 dev 서버 기동.
 * - CI: 프로덕션 빌드 산출물을 `next start` 로 기동 (빌드는 CI 선행 단계에서 완료).
 * - 백엔드 없이 동작 — 테스트가 sessionStorage 에 검토 결과를 시드하므로
 *   API 호출 실패(BFF 502)는 페이지 폴백 경로의 일부로 함께 검증된다.
 */
import { defineConfig } from '@playwright/test';

// CI 는 next start(3000), 로컬은 dev 서버 포트 — 루트 .env 의 CGR_FRONTEND_PORT (기존: 3000 고정)
const PORT = process.env.CI ? 3000 : Number(process.env.CGR_FRONTEND_PORT || 18091);

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://localhost:${PORT}`,
    viewport: { width: 1280, height: 800 },
    trace: 'retain-on-failure',
  },
  webServer: {
    command: process.env.CI ? 'npm run start' : 'npm run dev',
    port: PORT,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
