/**
 * 검토 건 저장소 — 근로계약서·취업규칙 검토 건을 브라우저에 보관하고 검토 이력을 제공한다.
 * 도메인별 단계 상태 갱신은 features/ec/store.ts · features/wr/store.ts 가 맡는다.
 *
 * 개발표준정의서 프론트엔드 식별자: 전역 상태는 도메인별 features/<domain>/store.ts, 전역 단일 스토어를 두지 않는다
 *   (기존: lib/reviewStore.ts 하나에 근로계약서·취업규칙 상태와 보관을 모두 둠)
 *
 * 모듈 메모리 (브라우저 탭 단위).
 *
 * 페이지 간 데이터 전달:
 *   홈 (POST 호출 시작) → 로딩 (대기) → 결과 (소비)
 *
 * sessionStorage 도 같이 사용 — 새로고침 시 결과 복원.
 * 단, 새로고침 후 검토 다시 돌리는 게 정확하므로 stale 표시.
 */
import type { EcWorkflow } from '@/features/ec/store';
import type { WrWorkflow } from '@/features/wr/store';
import type { EcReviewOut } from '@/lib/api/types';
import type { DocumentType, ReviewResult } from '@/types/review';

/** 결과 타입 — 문서 종류별 결과 형태가 다름. */
export type AnyCaseResult =
  | { doc: 'work-rules'; data: ReviewResult }
  | { doc: 'employment-contract'; data: EcReviewOut };

export interface CaseEntry {
  caseId: string;
  /** 'pending' | 'done' | 'error' */
  status: 'pending' | 'done' | 'error';
  /** 문서 종류 — 결과 페이지가 분기 렌더에 사용. */
  documentType?: DocumentType;
  result?: AnyCaseResult;
  error?: string;
  /** 시작 시각 (ms). */
  startedAt: number;
  /** done 시각 (ms). */
  doneAt?: number;
  /**
   * 결과 페이지 좌측 패널에 띄울 원본의 임시 URL.
   * - 이미지(PNG/JPG 등): `URL.createObjectURL(file)` 의 blob URL
   * - docx/hwp/pdf/txt: undefined (텍스트 문서는 좌측 미리보기 미제공)
   * 결과 페이지 unmount 시 `URL.revokeObjectURL` 로 해제 필수.
   */
  originalUrl?: string;
  /** 원본 파일명 — 좌측 패널 헤더 표시용. */
  originalFilename?: string;
  /** 원본 종류 — 좌측 패널 렌더 분기 ('image' 만 우선 지원). */
  originalKind?: 'image' | 'doc';
  /** 근로계약서 풀 이식 — 4단계 워크플로 상태. EC 일 때만 사용. */
  ec?: EcWorkflow;
  /** 취업규칙 — 추출 텍스트 확인·수정 단계. */
  wr?: WrWorkflow;
}

/** 탭 메모리 — 도메인 store 가 직접 읽고 쓴다. */
export const memory = new Map<string, CaseEntry>();

const SS_PREFIX = 'cgr.review.';      // 세션 — 탭 단위 (큰 본문 포함)
const LS_PREFIX = 'cgr.review.ls.';   // 영구 — 브라우저 단위 (사용자 검토 이력)
const LS_INDEX_KEY = 'cgr.review.index'; // 케이스 ID 배열 (정렬·삭제용)

export function persist(caseId: string, entry: CaseEntry) {
  if (typeof window === 'undefined') return;
  // blob: URL 은 페이지 새로고침 시 무효화되므로 직렬화에서 제외.
  // 단 data: URL(다운스케일 미리보기)은 영구 보존 가능 → 유지해 새로고침/이력 복원
  // 후에도 좌측 원본 사진이 살아있게 한다.
  let persistable: Partial<CaseEntry> = entry;
  if (!entry.originalUrl || !entry.originalUrl.startsWith('data:')) {
    const { originalUrl: _omitUrl, ...rest } = entry;
    void _omitUrl;
    persistable = rest;
  }
  const serialized = JSON.stringify(persistable);
  // 1) sessionStorage — 즉시 복구·새로고침 보존
  try {
    window.sessionStorage.setItem(SS_PREFIX + caseId, serialized);
  } catch {
    /* QuotaExceeded — 무시 */
  }
  // 2) localStorage — 탭 닫고 다시 열어도 복원 가능
  //    결과 본문이 커도 사용자 검토 이력 차원 — 부담 적음 (탭 단위 다회 누적 시 수 MB 까지)
  try {
    window.localStorage.setItem(LS_PREFIX + caseId, serialized);
    _addToIndex(caseId);
  } catch {
    // QuotaExceeded — 오래된 것 자동 정리 1회 시도
    _pruneIndex(20);
    try {
      window.localStorage.setItem(LS_PREFIX + caseId, serialized);
      _addToIndex(caseId);
    } catch {
      /* 그래도 실패 — sessionStorage 만 사용 */
    }
  }
}

function loadFromSession(caseId: string): CaseEntry | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.sessionStorage.getItem(SS_PREFIX + caseId);
    if (!raw) return null;
    return JSON.parse(raw) as CaseEntry;
  } catch {
    return null;
  }
}

/** localStorage 에서 검토 복원 — 새 탭에서도 동작. */
function loadFromLocal(caseId: string): CaseEntry | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(LS_PREFIX + caseId);
    if (!raw) return null;
    return JSON.parse(raw) as CaseEntry;
  } catch {
    return null;
  }
}

// ─── 검토 인덱스 (영구) ───────────────────────────────
function _readIndex(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(LS_INDEX_KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

function _writeIndex(ids: string[]) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(LS_INDEX_KEY, JSON.stringify(ids));
  } catch {
    /* noop */
  }
}

function _addToIndex(caseId: string) {
  const ids = _readIndex();
  const idx = ids.indexOf(caseId);
  if (idx >= 0) ids.splice(idx, 1); // 최근으로 옮기기
  ids.unshift(caseId);
  _writeIndex(ids);
}

/** 오래된 것부터 N개 유지 (용량 확보용). */
function _pruneIndex(keep: number) {
  if (typeof window === 'undefined') return;
  const ids = _readIndex();
  const drop = ids.slice(keep);
  for (const id of drop) {
    try {
      window.localStorage.removeItem(LS_PREFIX + id);
    } catch {
      /* noop */
    }
  }
  _writeIndex(ids.slice(0, keep));
}

interface StartCaseOptions {
  originalUrl?: string;
  originalFilename?: string;
  originalKind?: 'image' | 'doc';
}

export function startCase(
  caseId: string,
  documentType?: DocumentType,
  opts: StartCaseOptions = {},
) {
  const entry: CaseEntry = {
    caseId,
    status: 'pending',
    documentType,
    startedAt: Date.now(),
    originalUrl: opts.originalUrl,
    originalFilename: opts.originalFilename,
    originalKind: opts.originalKind,
  };
  memory.set(caseId, entry);
  persist(caseId, entry);
}

export function setCaseError(caseId: string, error: string) {
  const entry: CaseEntry = {
    caseId,
    status: 'error',
    error,
    startedAt: memory.get(caseId)?.startedAt ?? Date.now(),
    doneAt: Date.now(),
  };
  memory.set(caseId, entry);
  persist(caseId, entry);
}

export function getCase(caseId: string): CaseEntry | null {
  // 우선순위: memory → sessionStorage (현재 탭) → localStorage (지난 탭)
  return memory.get(caseId) ?? loadFromSession(caseId) ?? loadFromLocal(caseId);
}

/** 영구 보관된 모든 검토 목록 — 최근 순. /history 페이지용. */
export function listCases(): CaseEntry[] {
  if (typeof window === 'undefined') return [];
  const ids = _readIndex();
  const out: CaseEntry[] = [];
  for (const id of ids) {
    const e = loadFromLocal(id);
    if (e) out.push(e);
  }
  return out;
}

/**
 * case entry 가 어디서도 발견되지 않을 때의 fallback — minimal entry 생성.
 *
 * 이전에는 `if (!prev) return;` 로 silent fail 했는데, 새로고침·hot reload·
 * 다른 탭에서 들어온 경우 등 store 가 비어 있어도 `updateXxx` 가 동작해야
 * 사용자가 "문서에 반영" 등의 클릭을 잃지 않는다. 분석 결과 자체가
 * 없는 상태에서 phase 만 박힌 entry 라도 만들어두면 다음 통화에서 채워짐.
 */
export function ensureCaseEntry(caseId: string): CaseEntry {
  let prev = memory.get(caseId);
  if (!prev) {
    // memory → session → local 3단계 fallback. updateXxx 가 호출되는 시점은
    // 결과 페이지 등 case 가 이미 만들어진 후가 일반적이라 local 까지 봐서
    // 복원 가능성 최대화.
    const fromSession = loadFromSession(caseId);
    if (fromSession) {
      prev = fromSession;
      memory.set(caseId, fromSession);
    } else {
      const fromLocal = loadFromLocal(caseId);
      if (fromLocal) {
        prev = fromLocal;
        memory.set(caseId, fromLocal);
      }
    }
  }
  if (prev) return prev;
  // 정말 어디에도 없으면 minimal entry 생성 — 사용자 클릭 손실 방지.
  // status='pending' 으로 두면 후속 setCaseResult 호출 시 자연스럽게 done 으로 갱신됨.
  const minimal: CaseEntry = {
    caseId,
    status: 'pending',
    startedAt: Date.now(),
  };
  memory.set(caseId, minimal);
  persist(caseId, minimal);
  if (typeof window !== 'undefined' && typeof console !== 'undefined') {
    console.warn(
      '[history/store] case 가 어디에도 없어 minimal entry 생성:',
      caseId,
    );
  }
  return minimal;
}

export function clearCase(caseId: string) {
  memory.delete(caseId);
  if (typeof window !== 'undefined') {
    try {
      window.sessionStorage.removeItem(SS_PREFIX + caseId);
    } catch {
      /* noop */
    }
    try {
      window.localStorage.removeItem(LS_PREFIX + caseId);
      const ids = _readIndex();
      _writeIndex(ids.filter((id) => id !== caseId));
    } catch {
      /* noop */
    }
  }
}

/** 전체 검토 이력 삭제 — /history 페이지의 "전체 삭제" 버튼용. */
export function clearAllCases() {
  if (typeof window === 'undefined') return;
  const ids = _readIndex();
  for (const id of ids) {
    memory.delete(id);
    try {
      window.localStorage.removeItem(LS_PREFIX + id);
      window.sessionStorage.removeItem(SS_PREFIX + id);
    } catch {
      /* noop */
    }
  }
  _writeIndex([]);
}
