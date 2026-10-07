/**
 * 백엔드 FastAPI 응답 타입 — `mvp/cgr/api/schemas.py` 와 1:1 매핑.
 *
 * 프론트 `types/review.ts::Finding` 으로의 변환은 `lib/api/mappers.ts` 에서.
 */

/** 백엔드 FindingOut (cgr/api/schemas.py). */
export interface FindingOut {
  slot_id: string;
  article: number;
  bucket: '누락' | '위반' | '주의' | '검토필요' | '적정';
  status: 'VIOLATION' | 'MISSING' | 'AMBIGUOUS' | 'OK' | 'WARN' | 'ERROR';
  severity: string; // CRITICAL/HIGH/MEDIUM/LOW/INFO/''
  comparator: string;
  reason: string;
  user_reason: string | null;
  quote: string;
  extracted_value: unknown;
  penalty_omission: string[];
  penalty_violation: string[];
  fix_example: string | null;
}

export interface ArticleResultOut {
  article: number;
  title: string;
  findings: FindingOut[];
}

export interface ReviewFullOut {
  case_id: string;
  filename: string;
  overall_label: string; // 적정/부적정/검토불가
  summary: Record<string, number>; // {"누락": N, ...}
  n_findings: number;
  elapsed_sec: number;
  llm_model: string;
  article_results: ArticleResultOut[];
}

export interface ReviewSummaryOut {
  case_id: string;
  filename: string;
  overall_label: string;
  summary: Record<string, number>;
  n_findings: number;
  elapsed_sec: number;
  llm_model: string;
}

/** /health 응답. */
export interface HealthOut {
  status: string;
  version: string;
  services: Record<string, string>;
}

export interface ApiError {
  detail: string;
}

/* ───────────────────────────────────────────────
 * 근로계약서 (EC) — 3-Bucket 분류
 * ─────────────────────────────────────────────── */

export interface EcFindingOut {
  slot_id: string;
  field: string;
  bucket: '적절' | '보완필요' | '부적절';
  severity: string; // CRITICAL/HIGH/MEDIUM/LOW
  present: boolean;
  extracted: string;
  reason: string;
  required_content: string;
  purpose: string;
  laws: string[];
  topic_meta: string[];
  fix_example: string;
}

export interface EcReviewOut {
  case_id: string;
  filename: string;
  doc: 'employment_contract';
  overall_label: string; // 적절/보완필요/부적절/검토불가
  summary: Record<string, number>; // 3-Bucket 카운트
  n_findings: number;
  skipped: number;
  elapsed_sec: number;
  findings: EcFindingOut[];
}

/**
 * 통합 응답 타입 — `document_type` 에 따라 ReviewFullOut 또는 EcReviewOut.
 * EcReviewOut 은 `doc` 필드로 식별 가능 (`doc: 'employment_contract'`).
 */
export type AnyReviewOut = ReviewFullOut | EcReviewOut;

export function isEcReview(r: AnyReviewOut): r is EcReviewOut {
  return (r as EcReviewOut).doc === 'employment_contract';
}

/* ───────────────────────────────────────────────
 * 근로계약서 풀 이식 — 4단계 API
 * (기존 1. 근로계약서/기존/ Vite+Express 의 prompts.json 스키마를 그대로 옮김)
 * ─────────────────────────────────────────────── */

/** `/api/cgr/ec/extractions` 응답. */
export interface EcExtractOut {
  extracted_text: string;
  filename: string;
  elapsed_sec: number;
  model: string;
}

/** 8섹션 필드의 단위 값. `value` 는 핵심 수치/문구, `note` 는 단서 조항. */
export interface EcStructuredField {
  value: string;
  note: string;
}

/**
 * `structure` 프롬프트가 보장하는 8섹션 + 기타사항 구조.
 * 사용자가 검토 페이지에서 행 단위로 직접 수정한다.
 */
export interface EcStructuredData {
  기본정보: Record<string, EcStructuredField>;
  계약사항: Record<string, EcStructuredField>;
  근로시간: Record<string, EcStructuredField>;
  휴일휴가: Record<string, EcStructuredField>;
  임금: Record<string, EcStructuredField>;
  퇴직급여: Record<string, EcStructuredField>;
  사회보험: Record<string, EcStructuredField>;
  계약체결: Record<string, EcStructuredField>;
  기타사항: string[];
  /** LLM 이 양식 외 섹션을 만든 경우 대비 — 표 UI 가 동적으로 받을 수 있게. */
  [extra: string]: Record<string, EcStructuredField> | string[];
}

/** `/api/cgr/ec/structures` 응답. */
export interface EcStructureOut {
  structured_data: EcStructuredData;
  elapsed_sec: number;
  model: string;
}

/** `analyze` 결과 한 항목 (33매핑 × 사용자 컨텍스트 필터 후). */
export interface EcAnalysisItem {
  항목: string;
  적용조건: string; // 공통/5인이상/기간제/단시간/일용직/연소자/외국인 ...
  서면명시의무: string; // 필수_서면교부 등
  적절성: '적절' | '부적절' | '보완필요';
  /** `<meta db='...' n='...' />` 태그를 포함할 수 있음. 프론트에서 파싱해 칩으로 렌더. */
  판단이유: string;
  발견내용: string;
  법적근거: string;
  개선권고: string;
}

/** `analyze` 응답 전체 (기존 prompts.json analysis 출력 스키마). */
export interface EcAnalysisResult {
  riskLevel: '상' | '중' | '하' | string;
  overallStatus: '위험' | '보완필요' | '적정' | string;
  overallOpinion: string;
  results: EcAnalysisItem[];
  finalRecommendations: string;
}

/** `/api/cgr/ec/analyses` 응답. */
export interface EcAnalyzeOut {
  analysis_result: EcAnalysisResult;
  elapsed_sec: number;
  model: string;
}

/** `/api/cgr/ec/drafts` 응답. */
export interface EcGenerateOut {
  contract_text: string;
  elapsed_sec: number;
  model: string;
}

