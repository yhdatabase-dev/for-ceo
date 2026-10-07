/**
 * 화면 경로 — 한 곳에서 정의한다. basePath(/cgr)는 Next 가 자동으로 붙이므로 여기에는 넣지 않는다.
 *
 * 프로그램명세서 화면 URL(LC-001-01~LC-004-01, WR-001-01~WR-003-01, CM-002-03) 기준 (신규 — 기존: 화면마다 /review/[id]/... 직접 작성)
 *
 * 근로계약서(ec): 업로드 → 계약서 내용 확인(contract) → 검토결과(review) → 개선안 미리보기(preview)
 * 취업규칙(wr)  : 업로드 → 추출 텍스트 확인(text) → 검토결과(review) → 신구대조표(comparison)
 */
export const routes = {
  home: '/',
  history: '/history',

  ecUpload: '/ec',
  ecLoading: (caseUid: string) => `/ec/${caseUid}/loading`,
  ecContract: (caseUid: string) => `/ec/${caseUid}/contract`,
  ecReview: (caseUid: string) => `/ec/${caseUid}/review`,
  ecPreview: (caseUid: string) => `/ec/${caseUid}/preview`,

  wrUpload: '/wr',
  wrLoading: (caseUid: string) => `/wr/${caseUid}/loading`,
  wrText: (caseUid: string) => `/wr/${caseUid}/text`,
  wrReview: (caseUid: string) => `/wr/${caseUid}/review`,
  wrComparison: (caseUid: string) => `/wr/${caseUid}/comparison`,
  wrFinding: (caseUid: string, findingId: string) => `/wr/${caseUid}/findings/${findingId}`,
};
