/**
 * 배포 경로 prefix.
 *
 * - 기본 `/cgr` (next.config.mjs 가 값을 정해 빌드 시 인라인).
 * - 루트 배포는 `NEXT_PUBLIC_BASE_PATH=` (빈 값)으로 빌드.
 *
 * Next 의 `basePath`(next.config) 는 `<Link>`·router·자산만 자동 prefix 하고,
 * 원시 `fetch('/api/...')` 는 prefix 하지 않으므로 — BFF/관리자 등 모든 직접
 * fetch 경로 앞에 이 값을 붙여 쓴다. NEXT_PUBLIC_ 이라 빌드 시 인라인됨.
 */
export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? '';
