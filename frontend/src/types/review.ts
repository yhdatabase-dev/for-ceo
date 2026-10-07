/**
 * 검토 결과 도메인 타입
 *
 * << 개정이력(Modification Information) >>
 * 수정일          수정자      수정 내용
 * ----------      ------      ---------------------------
 * 2026.05.28      kimzion77   최초 생성
 * 2026.10.01      이시영      임금명세서·노무제공자 계약서·관리자 기능 삭제
 *
 * Author: kimzion77
 * Since: 2026.05.28
 */
/**
 * 검토 결과 도메인 타입
 *
 * **백엔드 정합**: `cgr/verdict.py` 의 5-Bucket + 선택조항을 그대로 반영한다.
 * - 누락 / 위반 / 주의 / 검토필요 / 적정 + 선택(검사 대상 아님)
 *
 * `RiskLevel` 은 시안 어휘 차용이지만 값은 백엔드 키. 별칭 `Bucket` 도 제공.
 */
import type { RiskLevel } from '@/styles/tokens';

export type { RiskLevel };

/** 백엔드 `verdict.classify()` 와 동치. */
export type Bucket = RiskLevel;

/** 슬롯 평가 상태 — 백엔드 `Finding.status` 와 동치. */
export type FindingStatus =
  | 'VIOLATION' // 본문에 있으나 법정 기준 미달
  | 'MISSING'   // 본문에 규정 자체가 없음
  | 'AMBIGUOUS' // 매칭이 모호 — 감독관 재확인 권장
  | 'WARN'      // 임의 규정 미준수
  | 'OK'        // 적정
  | 'ERROR';    // 추출 실패 등

/** 법령 인용 한 줄. */
export interface LawCitation {
  /** 법령명 + 조항 (예: "근로기준법 제53조"). */
  name: string;
  /** 본문 또는 요약. */
  text: string;
}

/**
 * 벌칙 정보 — 백엔드 `cgr/penalty_parser.py::format_for_user()` 결과.
 *
 * - omission   : 취업규칙에 **미기재** 시 — 행정 책임 (필수기재 누락)
 * - violation  : 법령 **내용 위반** 시 — 형사·과태료 (실체 위반)
 */
export interface Penalty {
  omission: string[];
  violation: string[];
}

/** 단일 검출 결과 — 슬롯 하나의 평가. */
export interface Finding {
  /** UI 노출용 짧은 식별자 (예: "S-014"). */
  id: string;
  /** 백엔드 슬롯 식별자 (예: "WORKHOURS_OVERTIME_LIMIT"). */
  slotId: string;
  /** "제24조" 형식. */
  article: string;
  /** "연장근로". */
  articleTitle: string;
  /** 7단계 위험도. */
  risk: RiskLevel;
  /** 평가 상태. */
  status: FindingStatus;
  /** 한 줄 제목. */
  title: string;
  /** 사용자에게 보여줄 평가 사유 (서술형). */
  reason: string;
  /** 사업장 본문에서 추출한 인용. 누락의 경우 빈 문자열일 수 있다. */
  quote: string;
  /** 슬롯이 추출한 값 (사람이 읽을 수 있는 형식). */
  extracted: string;
  /** 마스터 DB 기준값 (사람이 읽을 수 있는 형식). */
  standard: string;
  /** 근거 법령·판례 등 (호버 popover 로 전문 노출). */
  laws: LawCitation[];
  /** 백엔드 분류된 벌칙 — 미기재 vs 법령 위반. */
  penalty?: Penalty;
  /** 시정 예시 본문. */
  suggested: string;
  /** 연관 주제 메타. */
  topics: string[];
}

/** 위험도별 카운트. */
export type RiskCounts = Partial<Record<RiskLevel, number>>;

/** 우선순위 카드용 짧은 요약. */
export interface PriorityItem {
  id: string;
  risk: RiskLevel;
  title: string;
  article: string;
}

/** 검토 종합 결과. */
export interface ReviewSummary {
  /** "부적정 (중대)" 등. */
  verdict: string;
  /** verdict 색상 단서. */
  verdictKey: RiskLevel;
  fileName: string;
  fileSize: string;
  /** ISO 시각 또는 사람용 표기. */
  reviewedAt: string;
  /** "1분 18초" 등. */
  duration: string;
  /** 총 슬롯 수. */
  totalSlots: number;
  counts: RiskCounts;
  /** 검사 대상 조 수. */
  articles: number;
  /** 우선순위 상위 3개. */
  topPriority: PriorityItem[];
}

/** 결과 페이지에 함께 들어가는 컨테이너 — 백엔드 응답을 그대로 받는 형태. */
export interface ReviewResult {
  summary: ReviewSummary;
  findings: Finding[];
}

/* ─────────────────────────────────────────────
 *  홈 화면 입력 — 검토 요청 페이로드
 * ───────────────────────────────────────────── */

/** 문서 종류 — 취업규칙·근로계약서 (임금명세서·노무제공자 계약서는 제외). */
export type DocumentType = 'work-rules' | 'employment-contract';

/** 사업장 컨텍스트 — 백엔드 `WorkplaceContext` 와 매핑. */
export interface WorkplaceContext {
  // ── 취업규칙용 ────────────────────────
  /** 교대근로 도입 — null = 모름(보수적). */
  shiftWorkUsed: boolean | null;
  /** 산업안전보건법 적용 업종. */
  oshaApplicable: boolean;
  /** 화학물질 취급. */
  chemicalHandling: boolean | null;
  /** 작업환경측정 대상. */
  workenvMeasurement: boolean | null;

  // ── 근로계약서용 ──────────
  /** 사업장 규모 — '5+' (5인 이상) / '5-' (5인 미만) / null (모름). */
  businessSize: '5+' | '5-' | null;
  /** 근로자 유형 다중 — 정규직/기간제/단시간/일용직/연소자/외국인/외국인-농축어업. */
  workerTypes: string[];
}

/** POST /api/review 응답. */
export interface CreateReviewResponse {
  reviewId: string;
}

/** GET /api/review/{id}/status 응답. */
export interface ReviewStatus {
  reviewId: string;
  /** 0 ~ 100. */
  progress: number;
  /** 사람용 표기. */
  message: string;
  /** 완료 여부. */
  done: boolean;
  /** done=true 일 때 결과 URL. */
  resultUrl?: string;
}
