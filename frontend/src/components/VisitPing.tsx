'use client';

/**
 * 익명 방문 핑 — fire-and-forget POST /api/cgr/track/visits.
 * 개발표준정의서 API 엔드포인트: 리소스 visits (기존: /api/v1/track)
 *
 * 방문수·DAU/WAU/MAU 집계용. 방문자 식별자는 localStorage 의 **익명 uuid**(개인정보
 * 아님). 원시 IP·이름 등은 보내지 않는다. WarmupPing 과 동일하게 마운트 1회, 실패
 * 무시, 페이지 렌더를 막지 않는다.
 */
import { useEffect } from 'react';

import { BASE_PATH } from '@/lib/basePath';

function getVisitorId(): string {
  try {
    let v = localStorage.getItem('cgr_vid');
    if (!v) {
      v =
        (typeof crypto !== 'undefined' && crypto.randomUUID
          ? crypto.randomUUID()
          : Math.random().toString(36).slice(2) + Date.now().toString(36));
      localStorage.setItem('cgr_vid', v);
    }
    return v;
  } catch {
    return '';
  }
}

export default function VisitPing() {
  useEffect(() => {
    const t = window.setTimeout(() => {
      const visitor = getVisitorId();
      const page = (typeof window !== 'undefined' && window.location.pathname) || '';
      const ctrl = new AbortController();
      const killer = window.setTimeout(() => ctrl.abort(), 5000);
      fetch(`${BASE_PATH}/api/cgr/track/visits`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ visitor, page }),
        signal: ctrl.signal,
      })
        .catch(() => {
          /* best-effort */
        })
        .finally(() => window.clearTimeout(killer));
    }, 300);
    return () => window.clearTimeout(t);
  }, []);
  return null;
}
