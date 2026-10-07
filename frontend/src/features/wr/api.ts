/**
 * 검토 API — `/api/cgr/review` (BFF) 를 통한 POST/GET.
 *
 * 문서 종류(document_type) 분기:
 *  - 'work_rules' (기본) → ReviewFullOut (5-Bucket)
 *  - 'employment_contract' → EcReviewOut (3-Bucket)
 */
import {
  ApiCallError,
  apiGet,
  apiPostForm,
  apiPostJson,
  apiPostJsonBlob,
  triggerDownload,
} from '@/lib/api/client';
import { mapReviewResult } from './mappers';
import type {
  AnyReviewOut,
  EcReviewOut,
  ReviewSummaryOut,
} from '@/lib/api/types';
import { isEcReview } from '@/lib/api/types';
import type { DocumentType, ReviewResult, WorkplaceContext } from '@/types/review';

/** boolean | null → multipart Form 값 ("true"/"false"/null). */
function boolToFormValue(v: boolean | null): string {
  if (v === null) return '';
  return v ? 'true' : 'false';
}

/** 프론트 DocumentType → 백엔드 document_type 문자열. */
function mapDocumentType(d: DocumentType): string {
  switch (d) {
    case 'work-rules':
      return 'work_rules';
    case 'employment-contract':
      return 'employment_contract';
  }
}

export interface PostReviewOptions {
  files: File[];
  context: WorkplaceContext;
  documentType?: DocumentType;
  signal?: AbortSignal;
  /** 리뷰 세션 id — 홈에서 보관한 원본 파일과 이 검토 로그를 연결(관리자 열람용). */
  caseId?: string;
}

/** 취업규칙 검토 — 결과를 프론트 `ReviewResult` 형식으로 변환. */
export async function postReviewWorkRules(opts: PostReviewOptions): Promise<ReviewResult> {
  const out = await postReviewRaw(opts);
  if (isEcReview(out)) {
    throw new Error('근로계약서 응답을 받았으나 취업규칙 결과를 기대했습니다.');
  }
  return mapReviewResult(out);
}

/** 근로계약서 검토 — 백엔드 응답을 그대로 반환 (3-Bucket). */
export async function postReviewEmploymentContract(
  opts: PostReviewOptions,
): Promise<EcReviewOut> {
  const out = await postReviewRaw(opts);
  if (!isEcReview(out)) {
    throw new Error('취업규칙 응답을 받았으나 근로계약서 결과를 기대했습니다.');
  }
  return out;
}

/** 취업규칙 근로환경 AI 1차 분류 결과 — null 은 본문만으로 판단 불가(모름). */
export interface WrClassifyOut {
  shift_work_used: boolean | null;
  osha_applicable: boolean | null;
  chemical_handling: boolean | null;
  workenv_measurement: boolean | null;
  doc_kind: string;
  reason: string;
}

/**
 * 취업규칙 근로환경 AI 1차 분류 — start + poll (EC /ec/classify 와 동일 패턴).
 *
 * 사업장들이 잘 모르는 교대제·산안법·화학물질·작업환경측정을 AI 가 취업규칙
 * 본문에서 추정하고, 사용자는 추출 확인 화면에서 [맞아요/아니에요]만 누른다.
 */
export async function postWrClassify(
  extractedText: string,
  opts: { signal?: AbortSignal } = {},
): Promise<WrClassifyOut> {
  const { job_id } = await apiPostJson<{ job_id: string }>(
    '/wr/classifications',
    { extracted_text: extractedText },
    { signal: opts.signal },
  );
  const POLL_MS = 2000;
  const MAX_WAIT_MS = 3 * 60 * 1000;
  const startedAt = Date.now();
  for (;;) {
    await reviewSleep(POLL_MS, opts.signal);
    const res = await apiGet<Record<string, unknown>>(
      `/wr/classifications/${job_id}`,
      { signal: opts.signal },
    );
    if (res.status === 'done') {
      // doc_kind 는 항상 채워짐 — done 판별 키 (shift_work_used 등은 null 가능)
      if (res.doc_kind == null) {
        throw new ApiCallError(500, '분류 결과가 비어있어요. 다시 시도해 주세요.');
      }
      return {
        shift_work_used: (res.shift_work_used as boolean | null) ?? null,
        osha_applicable: (res.osha_applicable as boolean | null) ?? null,
        chemical_handling: (res.chemical_handling as boolean | null) ?? null,
        workenv_measurement: (res.workenv_measurement as boolean | null) ?? null,
        doc_kind: res.doc_kind as string,
        reason: (res.reason as string) ?? '',
      };
    }
    if (res.status === 'error') {
      throw new ApiCallError(
        500,
        (res.error as string) || '문서 분류에 실패했어요. 다시 시도해 주세요.',
      );
    }
    if (Date.now() - startedAt > MAX_WAIT_MS) {
      throw new ApiCallError(504, '문서 분류가 너무 오래 걸려요. 잠시 후 다시 시도해 주세요.');
    }
  }
}

function reviewSleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    if (signal) {
      signal.addEventListener(
        'abort',
        () => {
          clearTimeout(t);
          reject(new DOMException('Aborted', 'AbortError'));
        },
        { once: true },
      );
    }
  });
}

/**
 * 공통 POST — document_type 으로 백엔드가 분기. 비동기 잡(start + poll) 방식.
 *
 * 취업규칙 검토는 Excel 로드 + 전 조항 LLM 검토를 한 번에 하므로 동기 요청 시
 * Render cold start 와 합쳐져 Vercel 60초 함수 한도를 넘겨 'Unterminated JSON'
 * 으로 끊겼다. 이제 POST /wr/reviews 로 job_id 만 받고 GET /wr/reviews/{job_id} 를 폴링 —
 * 각 요청 1초 미만이라 아무리 느려도(검토가 길어도) 끊기지 않는다.
 */
export async function postReviewRaw(opts: PostReviewOptions): Promise<AnyReviewOut> {
  const { files, context, documentType = 'work-rules', signal, caseId } = opts;
  if (files.length === 0) {
    throw new Error('파일이 비어있습니다.');
  }

  const form = new FormData();
  form.append('file', files[0]);
  form.append('document_type', mapDocumentType(documentType));
  // 원본 파일(홈 추출 단계에서 보관)과 이 검토 로그를 연결하는 키.
  if (caseId) form.append('case_id', caseId);

  // 취업규칙용
  form.append('shift_work_used', boolToFormValue(context.shiftWorkUsed));
  form.append('osha_applicable', boolToFormValue(context.oshaApplicable));
  form.append('chemical_handling', boolToFormValue(context.chemicalHandling));
  form.append('workenv_measurement', boolToFormValue(context.workenvMeasurement));

  // 근로계약서용
  form.append('business_size', context.businessSize ?? '');
  form.append('worker_types', context.workerTypes.join(','));

  // 1) 시작 — job_id 즉시 수령
  const { job_id } = await apiPostForm<{ job_id: string }>('/wr/reviews', form, {
    signal,
  });

  // 2) 폴링
  const POLL_MS = 2500;
  const MAX_WAIT_MS = 6 * 60 * 1000;
  const startedAt = Date.now();
  for (;;) {
    await reviewSleep(POLL_MS, signal);
    const res = await apiGet<{
      status: string;
      result: AnyReviewOut | null;
      error: string | null;
      elapsed_sec: number;
    }>(`/wr/reviews/${job_id}`, { signal });

    if (res.status === 'done' && res.result) {
      return res.result;
    }
    if (res.status === 'error') {
      throw new ApiCallError(500, res.error || '검토에 실패했어요. 다시 시도해 주세요.');
    }
    if (Date.now() - startedAt > MAX_WAIT_MS) {
      throw new ApiCallError(
        504,
        '검토가 너무 오래 걸려요. 문서가 길거나 서버가 혼잡할 수 있어요. 잠시 후 다시 시도해 주세요.',
      );
    }
  }
}

/** 취업규칙 수정본 생성 — 사용자가 담은 수정 항목 1건. */
export interface WrCorrection {
  /** 항목명 (예: 제24조 연차유급휴가). */
  name: string;
  /** 현재 표현 (원문 발견 내용). */
  now: string;
  /** 수정 문구 (사용자 확정 표현). */
  fix: string;
}

export interface WrGenerateOut {
  revised_text: string;
  elapsed_sec: number;
  model: string;
}

/**
 * 취업규칙 수정본 생성 — 원문 + 수정 목록 → 수정본 전문. 비동기 잡(start + poll).
 *
 * 철학: 문제없는 조항은 원문 그대로 두고, 사용자가 담은 항목만 교체·추가.
 */
export async function postWrGenerate(
  originalText: string,
  corrections: WrCorrection[],
  opts: { signal?: AbortSignal } = {},
): Promise<WrGenerateOut> {
  const { job_id } = await apiPostJson<{ job_id: string }>(
    '/wr/revisions',
    { original_text: originalText, corrections },
    { signal: opts.signal },
  );

  const POLL_MS = 2500;
  const MAX_WAIT_MS = 6 * 60 * 1000;
  const startedAt = Date.now();
  for (;;) {
    await reviewSleep(POLL_MS, opts.signal);
    const res = await apiGet<{
      status: string;
      revised_text: string | null;
      error: string | null;
      elapsed_sec: number;
      model: string;
    }>(`/wr/revisions/${job_id}`, { signal: opts.signal });

    if (res.status === 'done' && res.revised_text != null) {
      return {
        revised_text: res.revised_text,
        elapsed_sec: res.elapsed_sec,
        model: res.model,
      };
    }
    if (res.status === 'error') {
      throw new ApiCallError(500, res.error || '수정본 생성에 실패했어요. 다시 시도해 주세요.');
    }
    if (Date.now() - startedAt > MAX_WAIT_MS) {
      throw new ApiCallError(504, '수정본 생성이 너무 오래 걸려요. 잠시 후 다시 시도해 주세요.');
    }
  }
}

/** 취업규칙 수정본 본문 → .docx 다운로드 — 호출 즉시 사용자 다운로드 트리거. */
export async function downloadWrDocx(
  body: { contract_text: string; filename?: string },
): Promise<void> {
  const fname = body.filename ?? '취업규칙_수정본.docx';
  const { blob, filename } = await apiPostJsonBlob('/wr/revision-documents', body);
  triggerDownload(blob, filename ?? fname);
}

/** 신구대조표(표) + 의견청취서 양식 .docx 다운로드 — 표가 깨지지 않게 진짜 Word 표로. */
export async function downloadWrComparisonDocx(body: {
  rows: {
    article: string;
    title: string;
    before: string;
    after: string;
    remark: string;
  }[];
  effective_date?: string;
  filename?: string;
}): Promise<void> {
  const fname = body.filename ?? '취업규칙_신구대조표.docx';
  const { blob, filename } = await apiPostJsonBlob('/wr/comparison-documents', body);
  triggerDownload(blob, filename ?? fname);
}

/** legacy alias — 기존 호출처 호환. */
export const postReview = postReviewWorkRules;

/** GET /review/{case_id} — 이력 요약 조회. */
export async function getReviewSummary(caseId: string): Promise<ReviewSummaryOut> {
  return apiGet<ReviewSummaryOut>(`/wr/review-summaries/${encodeURIComponent(caseId)}`);
}

/** 응답 자체를 분기 처리하는 헬퍼 export. */
export { isEcReview, type AnyReviewOut, type EcReviewOut };
