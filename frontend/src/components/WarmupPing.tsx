/**
 * 백엔드 warm-up ping — fire-and-forget GET /api/cgr/warmup (인증 불필요).
 *
 * << 개정이력(Modification Information) >>
 * 수정일          수정자      수정 내용
 * ----------      ------      ---------------------------
 * 2026.06.02      kimzion77   최초 생성
 * 2026.10.07      이시영      검토번호 서버 발급, 변경 사유 주석 추가
 *
 * Author: kimzion77
 * Since: 2026.06.02
 */
'use client';

/**
 * 백엔드 warm-up ping — fire-and-forget GET /api/cgr/warmup (인증 불필요).
 * 개발표준정의서 API 엔드포인트: 서비스 접두 /api/cgr (기존: /api/v1/warmup)
 *
 * 배경:
 *   Render 무료 플랜은 15분 유휴 후 sleep → 첫 요청에 15-30초 cold start.
 *   사용자가 검토 화면에 들어가기 전 미리 깨워두면 분석 시작 시점에 이미 warm.
 *
 * 동작:
 *   - 홈 페이지 마운트 시 1회 호출
 *   - 응답을 기다리지 않음 (fire-and-forget) — 페이지 렌더 막지 않음
 *   - 실패해도 무시 — 사용자 흐름과 무관
 *
 * 사용 위치:
 *   - app/layout.tsx 또는 app/page.tsx 의 home 화면에 한 번 마운트
 *   - 검토 시작 페이지(EC/WS/SC) 진입 시에도 호출
 */
import { useEffect } from 'react';

import { BASE_PATH } from '@/lib/basePath';

export default function WarmupPing() {
  useEffect(() => {
    // 마운트 후 100ms 지연 — 페이지 렌더에 영향 안 주게 idle 시점에 발사
    const t = window.setTimeout(() => {
      // /health 는 인증 불필요. AbortController 로 5초 후 자동 취소 (오래 잡고 있지 않게)
      const ctrl = new AbortController();
      const killer = window.setTimeout(() => ctrl.abort(), 5000);
      fetch(`${BASE_PATH}/api/cgr/warmup`, { method: 'GET', signal: ctrl.signal })
        .catch(() => {
          /* 무시 — warm-up 은 best-effort */
        })
        .finally(() => window.clearTimeout(killer));
    }, 100);
    return () => window.clearTimeout(t);
  }, []);
  return null;
}
