/**
 * 검토 결과 임시 저장소 — 모듈 메모리 (브라우저 탭 단위).
 *
 * 페이지 간 데이터 전달:
 *   홈 (POST 호출 시작) → 로딩 (대기) → 결과 (소비)
 *
 * sessionStorage 도 같이 사용 — 새로고침 시 결과 복원.
 * 단, 새로고침 후 검토 다시 돌리는 게 정확하므로 stale 표시.
 */
import type {
  EcAnalysisResult,
  EcReviewOut,
  EcStructuredData,
} from '@/lib/api/types';
import type { DocumentType, ReviewResult, WorkplaceContext } from '@/types/review';

/** 결과 타입 — 문서 종류별 결과 형태가 다름. */
export type AnyCaseResult =
  | { doc: 'work-rules'; data: ReviewResult }
  | { doc: 'employment-contract'; data: EcReviewOut };

/**
 * 근로계약서 풀 이식 — 4단계 워크플로 진행 상태.
 *
 * 각 단계 결과를 차곡차곡 쌓아두고, 사용자가 Step2 검토 페이지에 머무는 동안
 * 어디까지 갔는지 추적. `phase` 가 라우팅 분기 키.
 */
export type EcPhase =
  | 'idle' // 시작 전
  | 'extracting' // /ec/extract 진행
  | 'structuring' // /ec/structure 진행
  | 'review' // 사용자 검토·수정 단계 (Step2)
  | 'analyzing' // /ec/analyze 진행
  | 'result' // Step3 완료 — 결과 페이지로
  | 'generating' // /ec/generate 진행
  | 'contract' // Step4 완료 — 계약서 페이지로
  | 'error';

export interface EcWorkflow {
  phase: EcPhase;
  extractedText?: string;
  /** 백엔드가 첫 호출에서 준 8섹션 JSON — 사용자가 표 UI 에서 수정. */
  structuredData?: EcStructuredData;
  /** 사용자가 입력한 컨텍스트 (Step2 에서 확정). */
  businessSize?: string;
  workerTypes?: string[];
  /**
   * AI 1차 분류 결과 (/ec/classify) — 검토 페이지에서 사용자가 "맞아요/아니에요" 로
   * 확인한다. confirmed=true 는 분석 시작 시점에 박힌다. 분류 실패 시 undefined
   * (폼에서 받은 workerTypes 가 fallback).
   */
  classify?: {
    workerTypes: string[];
    docKind: string;
    reason?: string;
    confirmed?: boolean;
  };
  /** /ec/analyze 결과 (Step3 페이지가 사용). */
  analysisResult?: EcAnalysisResult;
  /** /ec/generate 결과 (Step4 페이지가 사용). */
  generatedContract?: string;
  /** 단계별 오류 메시지. */
  errorMessage?: string;
  /**
   * 사용자가 결과 페이지에서 직접 작성·수정한 보완 표현 (항목명 → 본인 입력 텍스트).
   *
   * SuggestBlock 의 "제안 표현" 박스를 편집한 뒤 "문서에 반영" 을 누르면 이 맵에 들어간다.
   * Step4 (표준 계약서 생성) 호출 시 analysis.results 의 `개선권고` 를 이 값으로 덮어써
   * 백엔드 generate 프롬프트에 사용자 표현이 그대로 흘러간다.
   */
  userOverrides?: Record<string, string>;
}

/**
 * 취업규칙 (work rules) — 추출 텍스트 확인·수정 단계용 최소 워크플로.
 *
 * 기존 단일 호출 흐름(postReviewWorkRules 한 방)에 사용자 확인 단계를 끼워넣기 위해:
 *   1) 홈에서 postEcExtract (범용 parse_to_text) 로 텍스트만 추출 → phase 'review'
 *   2) 사용자가 /review/[id]/wr/review 에서 텍스트 확인·수정
 *   3) '분석 시작' → phase 'analyzing' → 수정 텍스트를 .txt File 로 감싸 postReviewWorkRules
 * 결과는 기존과 동일하게 setCaseResult (status='done') → /review/[id] 라우팅.
 */
export interface WrWorkflow {
  phase: 'review' | 'analyzing' | 'generating' | 'contract';
  extractedText?: string;
  errorMessage?: string;
  /** 홈 폼에서 받은 사업장 컨텍스트 — 분석 호출 시 그대로 전달. */
  context?: WorkplaceContext;
  /**
   * AI 1차 근로환경 분류 (취업규칙 본문 추정) — wr/review 확인 배너에 사용.
   * 사용자가 [맞아요/아니에요]로 확정한 값이 분석 컨텍스트를 덮어쓴다.
   * null = 본문만으로 판단 불가(모름 — 보수적으로 검사함).
   */
  classify?: {
    shiftWorkUsed: boolean | null;
    oshaApplicable: boolean | null;
    chemicalHandling: boolean | null;
    workenvMeasurement: boolean | null;
    docKind: string;
    reason: string;
  };
  /** 사용자가 결과 페이지에서 수정본에 담은 보완 표현 (항목 key → 본인 입력 텍스트). */
  userOverrides?: Record<string, string>;
  /** /review/generate 결과 — 원문 보존 + 수정 항목만 반영된 수정본 전문. */
  generatedText?: string;
}

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

const memory = new Map<string, CaseEntry>();

const SS_PREFIX = 'cgr.review.';      // 세션 — 탭 단위 (큰 본문 포함)
const LS_PREFIX = 'cgr.review.ls.';   // 영구 — 브라우저 단위 (사용자 검토 이력)
const LS_INDEX_KEY = 'cgr.review.index'; // 케이스 ID 배열 (정렬·삭제용)

function persist(caseId: string, entry: CaseEntry) {
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

/** 임시 case_id 생성 — POST 응답에 case_id 가 오면 그걸로 교체. */
export function makeTempCaseId(): string {
  const ts = new Date()
    .toISOString()
    .replace(/[-:T.Z]/g, '')
    .slice(0, 14);
  const rand = Math.random().toString(36).slice(2, 6);
  return `tmp_${ts}_${rand}`;
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

/** 취업규칙 결과 저장. */
export function setCaseResult(caseId: string, result: ReviewResult) {
  const prev = memory.get(caseId);
  const entry: CaseEntry = {
    caseId,
    status: 'done',
    documentType: prev?.documentType ?? 'work-rules',
    result: { doc: 'work-rules', data: result },
    startedAt: prev?.startedAt ?? Date.now(),
    doneAt: Date.now(),
    originalUrl: prev?.originalUrl,
    originalFilename: prev?.originalFilename,
    originalKind: prev?.originalKind,
    // 워크플로 상태 보존 — 특히 wr.extractedText 가 있어야 결과 화면에서
    // '원문에서 보기'가 노출된다(이게 없으면 원문 보기 버튼이 사라짐).
    wr: prev?.wr,
    ec: prev?.ec,
  };
  memory.set(caseId, entry);
  persist(caseId, entry);
}

/** 근로계약서 결과 저장. */
export function setCaseEcResult(caseId: string, ec: EcReviewOut) {
  const prev = memory.get(caseId);
  const entry: CaseEntry = {
    caseId,
    status: 'done',
    documentType: 'employment-contract',
    result: { doc: 'employment-contract', data: ec },
    startedAt: prev?.startedAt ?? Date.now(),
    doneAt: Date.now(),
    originalUrl: prev?.originalUrl,
    originalFilename: prev?.originalFilename,
    originalKind: prev?.originalKind,
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
function ensureCaseEntry(caseId: string): CaseEntry {
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
      '[reviewStore] case 가 어디에도 없어 minimal entry 생성:',
      caseId,
    );
  }
  return minimal;
}


/**
 * 근로계약서 4단계 워크플로 — 단계별로 EcWorkflow 를 부분 갱신.
 *
 * 각 호출은 기존 ec 상태와 머지 (이전 단계 결과 보존).
 * `phase` 만 바뀌는 경우도 자주 있어서 별도 헬퍼는 두지 않음.
 *
 * **resilient**: case entry 가 어디서도 발견되지 않으면 새로 만들어 갱신.
 * 이전 silent return 동작이 SuggestBlock "문서에 반영" 클릭을 잃는 원인이었음.
 */
export function updateEc(caseId: string, patch: Partial<EcWorkflow>) {
  const prev = ensureCaseEntry(caseId);
  const prevEc: EcWorkflow = prev.ec ?? { phase: 'idle' };
  const nextEc: EcWorkflow = { ...prevEc, ...patch };
  const entry: CaseEntry = { ...prev, ec: nextEc };
  memory.set(caseId, entry);
  persist(caseId, entry);
}

/** WR (취업규칙) 워크플로 부분 갱신 — 추출 텍스트 확인 단계. */
export function updateWr(caseId: string, patch: Partial<WrWorkflow>) {
  const prev = ensureCaseEntry(caseId);
  const prevWr: WrWorkflow = prev.wr ?? { phase: 'review' };
  const nextWr: WrWorkflow = { ...prevWr, ...patch };
  const entry: CaseEntry = { ...prev, wr: nextWr };
  memory.set(caseId, entry);
  persist(caseId, entry);
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
