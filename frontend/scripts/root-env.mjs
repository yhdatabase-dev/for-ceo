/**
 * 저장소 루트 .env 로더 — 백엔드와 같은 .env 하나를 프론트 서버도 쓰게 한다.
 *
 * 이미 설정된 환경변수는 덮지 않는다(운영·컨테이너는 환경변수로만 주입, .env 없음).
 * next.config.mjs · scripts/dev.mjs 에서 부른다.
 */
import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT_ENV = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '.env');

export function loadRootEnv() {
  if (!existsSync(ROOT_ENV)) return;
  for (const raw of readFileSync(ROOT_ENV, 'utf-8').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const i = line.indexOf('=');
    const key = line.slice(0, i).trim();
    const value = line.slice(i + 1).trim().replace(/^['"]|['"]$/g, '');
    if (key && value && process.env[key] === undefined) process.env[key] = value;
  }
}
