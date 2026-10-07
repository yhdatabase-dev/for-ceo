/**
 * 취업규칙 검토 상태 — 검토 건(features/history/store)의 wr 단계 상태와 결과를 갱신한다.
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
 * 취업규칙 검토 상태 — 검토 건(features/history/store)의 wr 단계 상태와 결과를 갱신한다.
 *
 * 개발표준정의서 프론트엔드 식별자: 전역 상태는 도메인별 features/<domain>/store.ts, 전역 단일 스토어를 두지 않는다 (기존: lib/reviewStore.ts)
 */
import { ensureCaseEntry, memory, persist, type CaseEntry } from '@/features/history/store';
import type { ReviewResult, WorkplaceContext } from '@/types/review';

/**
 * 취업규칙 (work rules) — 추출 텍스트 확인·수정 단계용 최소 워크플로.
 *
 * 기존 단일 호출 흐름(postReviewWorkRules 한 방)에 사용자 확인 단계를 끼워넣기 위해:
 *   1) 홈에서 postEcExtract (범용 parse_to_text) 로 텍스트만 추출 → phase 'review'
 *   2) 사용자가 /wr/[caseUid]/text 에서 텍스트 확인·수정
 *   3) '분석 시작' → phase 'analyzing' → 수정 텍스트를 .txt File 로 감싸 postReviewWorkRules
 * 결과는 기존과 동일하게 setCaseResult (status='done') → /wr/[caseUid]/review 라우팅.
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

/** WR (취업규칙) 워크플로 부분 갱신 — 추출 텍스트 확인 단계. */
export function updateWr(caseId: string, patch: Partial<WrWorkflow>) {
  const prev = ensureCaseEntry(caseId);
  const prevWr: WrWorkflow = prev.wr ?? { phase: 'review' };
  const nextWr: WrWorkflow = { ...prevWr, ...patch };
  const entry: CaseEntry = { ...prev, wr: nextWr };
  memory.set(caseId, entry);
  persist(caseId, entry);
}
