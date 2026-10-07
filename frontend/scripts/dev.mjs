/**
 * 로컬 개발 서버 — 루트 .env 의 CGR_FRONTEND_PORT(기본 18091)로 next dev 를 띄운다.
 */
import { spawn } from 'node:child_process';
import { loadRootEnv } from './root-env.mjs';

loadRootEnv();
const port = process.env.CGR_FRONTEND_PORT || '18091';
const child = spawn('npx', ['next', 'dev', '-p', port], { stdio: 'inherit', shell: true });
child.on('exit', (code) => process.exit(code ?? 0));
