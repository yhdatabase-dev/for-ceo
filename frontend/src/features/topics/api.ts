/**
 * 노무사회 주제 코퍼스 — 백엔드 lazy fetch.
 *
 * 기존 `src/data/topicCorpus.json` (1.83MB) 를 빌드 번들에 박지 않고
 * 첫 hover/excerpt 요청 직전에 1회만 받아 모듈 캐시에 보관.
 *
 * 백엔드: `GET /api/cgr/topics/sections` (cgr/api/routes/topics.py)
 *
 * 캐시 정책
 *   - 모듈 레벨 Promise 한 개 → 동시 호출도 단일 fetch 로 수렴.
 *   - 실패 시 빈 corpus 로 resolve (앱 동작은 계속 — 4순위 fallback 메시지).
 *   - 페이지 새로고침 전까지 유지.
 */
import { useEffect, useState } from 'react';

import { apiGet } from '@/lib/api/client';

export interface TopicSection {
  title: string;
  body: string;
  body_friendly?: string;
}

export type TopicCorpus = Record<string, Record<string, TopicSection>>;

const EMPTY_CORPUS: TopicCorpus = {};

let _corpusCache: TopicCorpus | null = null;
let _inflight: Promise<TopicCorpus> | null = null;

// 적재 완료 알림 — 모듈 레벨 pub/sub. React 컴포넌트가 corpus 로드를 감지해
// 재렌더할 수 있게 함.
type Listener = () => void;
const _listeners = new Set<Listener>();
function _notify() {
  for (const fn of _listeners) {
    try {
      fn();
    } catch {
      // 리스너 한 개 실패가 다른 리스너에 영향 없도록.
    }
  }
}

/**
 * 코퍼스 적재 보장. 첫 호출 시에만 네트워크 호출.
 *
 * 호출 패턴 권장:
 *   - 컴포넌트 mount 직후 한 번 ensureCorpusLoaded() (await 안 해도 됨 — fire-and-forget).
 *   - 실제 lookup 직전 await ensureCorpusLoaded() — 캐시 hit 면 micro-task 한 번.
 */
export function ensureCorpusLoaded(): Promise<TopicCorpus> {
  if (_corpusCache) return Promise.resolve(_corpusCache);
  if (_inflight) return _inflight;
  _inflight = apiGet<TopicCorpus>('/topics/sections')
    .then((data) => {
      _corpusCache = data && typeof data === 'object' ? data : EMPTY_CORPUS;
      return _corpusCache;
    })
    .catch(() => {
      // 백엔드 실패 시 빈 corpus 로 fallback — UI 는 4순위 메시지로 동작.
      _corpusCache = EMPTY_CORPUS;
      return _corpusCache;
    })
    .finally(() => {
      _inflight = null;
      _notify();
    });
  return _inflight;
}

/**
 * 동기 접근. mount 시 ensureCorpusLoaded() 가 끝났다면 즉시 corpus 반환,
 * 아직 미적재면 빈 객체 반환 — 호출자는 await 버전을 우선 쓰는 것이 안전.
 */
export function getCorpusSync(): TopicCorpus {
  return _corpusCache ?? EMPTY_CORPUS;
}

/** 테스트·핫리로드 용. 캐시 비우기. */
export function _resetCorpusCacheForTest(): void {
  _corpusCache = null;
  _inflight = null;
}

/**
 * React 훅 — 코퍼스 적재 상태 구독.
 *
 * 반환값
 *   - `loaded`: 캐시가 채워졌는지 (boolean). 의존성 배열에 넣으면
 *     코퍼스 적재 직후 re-render 가 자동으로 일어남.
 *
 * 사용 예
 * ```tsx
 * const { loaded } = useTopicCorpus();
 * const excerpt = useMemo(() => lookupLawExcerpt(db, n), [db, n, loaded]);
 * ```
 *
 * mount 시 자동으로 ensureCorpusLoaded() 도 trigger — 호출자는 따로 안 해도 됨.
 */
export function useTopicCorpus(): { loaded: boolean } {
  const [loaded, setLoaded] = useState<boolean>(() => _corpusCache !== null);

  useEffect(() => {
    let alive = true;
    // 모듈 단일 fetch — 이미 끝났으면 즉시 resolve.
    ensureCorpusLoaded().then(() => {
      if (alive) setLoaded(true);
    });
    // 다른 컴포넌트에서 reset/재적재 시 동기화.
    const listener: Listener = () => {
      if (alive) setLoaded(_corpusCache !== null);
    };
    _listeners.add(listener);
    return () => {
      alive = false;
      _listeners.delete(listener);
    };
  }, []);

  return { loaded };
}
