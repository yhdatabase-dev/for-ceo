/**
 * 근로계약서 검토 상태 — 검토 건(features/history/store)의 ec 단계 상태를 갱신한다.
 */
import { ensureCaseEntry, memory, persist, type CaseEntry } from '@/features/history/store';
import type {
  EcAnalysisResult,
  EcReviewOut,
  EcStructuredData,
} from '@/lib/api/types';

/**
 * 근로계약서 풀 이식 — 4단계 워크플로 진행 상태.
 *
 * 각 단계 결과를 차곡차곡 쌓아두고, 사용자가 Step2 검토 페이지에 머무는 동안
 * 어디까지 갔는지 추적. `phase` 가 라우팅 분기 키.
 */
export type EcPhase =
  | 'idle' // 시작 전
  | 'extracting' // /ec/extractions 진행
  | 'structuring' // /ec/structure 진행
  | 'review' // 사용자 검토·수정 단계 (Step2)
  | 'analyzing' // /ec/analyses 진행
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
  /** /ec/analyses 결과 (Step3 페이지가 사용). */
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
