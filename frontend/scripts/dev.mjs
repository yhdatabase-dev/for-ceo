/**
 * 로컬 개발 서버 — 루트 .env 의 CGR_FRONTEND_PORT(기본 18091)로 next dev 를 띄운다.
 *
 * << 개정이력(Modification Information) >>
 * 수정일          수정자      수정 내용
 * ----------      ------      ---------------------------
 * 2026.10.07      이시영      최초 생성
 * 2026.10.07      이시영      검토번호 서버 발급, 변경 사유 주석 추가
 *
 * Author: 이시영
 * Since: 2026.10.07
 */
/**
 * 로컬 개발 서버 — 루트 .env 의 CGR_FRONTEND_PORT(기본 18091)로 next dev 를 띄운다.
 * 개발표준정의서 Directory 구조: 환경설정 값은 환경변수로 주입 — 저장소 루트 .env 하나를 백엔드와 함께 씀 (신규 — 기존: package.json 에 포트 3000 고정)
 */
import { spawn } from 'node:child_process';
import { loadRootEnv } from './root-env.mjs';

loadRootEnv();
const port = process.env.CGR_FRONTEND_PORT || '18091';
const child = spawn('npx', ['next', 'dev', '-p', port], { stdio: 'inherit', shell: true });
child.on('exit', (code) => process.exit(code ?? 0));
