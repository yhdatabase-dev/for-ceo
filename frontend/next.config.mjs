/**
 * << 개정이력(Modification Information) >>
 * 수정일          수정자      수정 내용
 * ----------      ------      ---------------------------
 * 2026.05.28      kimzion77   최초 생성
 * 2026.10.07      이시영      환경설정 통합 (루트 .env·config.py), mock LLM 추가
 * 2026.10.07      이시영      화면 경로 /cgr·features 구조 이동, sync API 삭제, 업로드 원본 미저장
 * 2026.10.07      이시영      검토번호 서버 발급, 변경 사유 주석 추가
 *
 * Author: kimzion77
 * Since: 2026.05.28
 */
import { loadRootEnv } from './scripts/root-env.mjs';

// 개발표준정의서 Directory 구조: 환경설정 값은 환경변수로 주입 — 저장소 루트 .env 하나를 백엔드와 함께 씀 (기존: frontend/.env.local)
// 이미 있는 환경변수가 우선.
loadRootEnv();

/** @type {import('next').NextConfig} */
// 개발표준정의서 API 엔드포인트(화면 경로): 각 서비스 앱은 basePath 로 /cgr 접두를 갖는다 (기존: 접두 없음)
// 빈 값으로 지정하면 basePath 없이 루트에 배포.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? '/cgr';

const nextConfig = {
  reactStrictMode: true,
  // 정보노출 방지(국정원 점검) — 'X-Powered-By: Next.js' 응답 헤더 제거
  poweredByHeader: false,
  // BFF (`app/api/cgr/[...path]/route.ts`) 가 백엔드로 직접 fetch 하므로 rewrites 불필요.
  // 환경 변수: CGR_API_BASE, CGR_API_KEY 는 BFF 안에서만(서버 측) 사용.
  ...(basePath ? { basePath } : {}),
  // 브라우저 코드(lib/basePath.ts)가 같은 값을 보도록 빌드 시 인라인
  env: { NEXT_PUBLIC_BASE_PATH: basePath },
  // 루트(/)로 들어오면 서비스 첫 화면으로
  async redirects() {
    return basePath
      ? [{ source: '/', destination: basePath, basePath: false, permanent: false }]
      : [];
  },
  // ─── 보안 응답 헤더 (OWASP A05 / 국정원 점검: 클릭재킹·MIME 스니핑 등) ───
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=()',
          },
          // 스크립트/스타일은 제한하지 않고 프레이밍만 차단(앱 동작 영향 없음)
          { key: 'Content-Security-Policy', value: "frame-ancestors 'self'" },
          {
            key: 'Strict-Transport-Security',
            value: 'max-age=31536000; includeSubDomains',
          },
        ],
      },
    ];
  },
};

export default nextConfig;
