/**
 * 근로계약서 풀 이식 — 4단계 API 클라이언트.
 *
 * 개발표준정의서 Directory 구성도: 업무 기능은 features/<도메인>/ (기존: lib/api/ec.ts)
 * 프로그램명세서 AI-P02-001~009·WEB-P02-004: /api/cgr/ec/<리소스> (기존: /api/v1/ec/extract/start 등)
 *
 * 기존 `1. 근로계약서/기존/src/api/contractApi.js` 와 1:1 매핑.
 * 백엔드 라우터: `cgr/api/routes/ec.py`
 *
 * 흐름:
 *   extract → structure → (사용자 검토·수정) → analyze → generate
 *
 * 각 단계가 독립 호출 가능하므로 사용자가 검토 페이지에서 머무는 동안
 * 클라이언트 메모리에 결과를 보관 (features/ec/store) 한 뒤 다음 단계로 진행.
 */
import {
  ApiCallError,
  apiGet,
  apiPostForm,
  apiPostJson,
  apiPostJsonBlob,
  triggerDownload,
} from '@/lib/api/client';
import type {
  EcAnalyzeOut,
  EcAnalysisResult,
  EcExtractOut,
  EcGenerateOut,
  EcStructureOut,
  EcStructuredData,
} from '@/lib/api/types';

/** 공통 폴링 헬퍼 — start 로 job_id 받고 result 를 폴링. */
async function pollJob<T>(
  resultPath: (jobId: string) => string,
  jobId: string,
  pick: (res: Record<string, unknown>) => T | undefined,
  opts: { signal?: AbortSignal; label?: string } = {},
): Promise<T> {
  const POLL_MS = 2000;
  const MAX_WAIT_MS = 6 * 60 * 1000;
  const startedAt = Date.now();
  for (;;) {
    await sleep(POLL_MS, opts.signal);
    const res = await apiGet<Record<string, unknown>>(resultPath(jobId), {
      signal: opts.signal,
    });
    const status = res.status as string;
    if (status === 'done') {
      const v = pick(res);
      if (v !== undefined && v !== null) return v;
      throw new ApiCallError(500, `${opts.label ?? '작업'} 결과가 비어있어요. 다시 시도해 주세요.`);
    }
    if (status === 'error') {
      throw new ApiCallError(500, (res.error as string) || `${opts.label ?? '작업'}에 실패했어요. 다시 시도해 주세요.`);
    }
    if (Date.now() - startedAt > MAX_WAIT_MS) {
      throw new ApiCallError(504, `${opts.label ?? '작업'}이 너무 오래 걸려요. 잠시 후 다시 시도해 주세요.`);
    }
  }
}

/**
 * 1단계(접수): 파일 1건 추출 요청 — job_id 와 서버가 발급한 검토 건 번호(case_id)를 바로 받는다.
 * 프로그램명세서 AI-P02-001: 검토 건 번호(case_id)는 서버가 UUID 로 발급해 응답에 돌려준다.
 *   첫 장은 case_id 없이 보내 번호를 받고, 이후 장은 그 번호를 실어 보낸다.
 *   (기존: 브라우저가 tmp_ 번호를 만들어 보내고 job_id 만 받음)
 */
export async function startEcExtract(
  file: File,
  opts: { signal?: AbortSignal; caseId?: string; service?: string } = {},
): Promise<{ jobId: string; caseId: string }> {
  const form = new FormData();
  form.append('file', file);
  // 업로드 기록을 검토 건과 연결 (case_id) — service 로 라벨 분기(EC/취업규칙 공용 추출).
  if (opts.caseId) form.append('case_id', opts.caseId);
  if (opts.service) form.append('service', opts.service);
  const { job_id, case_id } = await apiPostForm<{ job_id: string; case_id: string }>(
    '/ec/extractions',
    form,
    { signal: opts.signal },
  );
  return { jobId: job_id, caseId: case_id };
}

/** 1단계(결과): 추출 잡 완료까지 폴링 — 이미지 OCR 이 느릴 수 있어 비동기 잡으로 타임아웃 우회. */
export async function waitEcExtract(
  jobId: string,
  opts: { signal?: AbortSignal } = {},
): Promise<EcExtractOut> {
  return pollJob<EcExtractOut>(
    (id) => `/ec/extractions/${id}`,
    jobId,
    (res) =>
      res.extracted_text != null
        ? ({
            extracted_text: res.extracted_text as string,
            filename: (res.filename as string) ?? '',
            elapsed_sec: (res.elapsed_sec as number) ?? 0,
            model: (res.model as string) ?? '',
            case_id: (res.case_id as string) ?? '',
          } as EcExtractOut)
        : undefined,
    { signal: opts.signal, label: '문서 추출' },
  );
}

/** 1단계: 파일 → 텍스트 (이미지면 OCR) — 접수 + 결과 대기. */
export async function postEcExtract(
  file: File,
  opts: { signal?: AbortSignal; caseId?: string; service?: string } = {},
): Promise<EcExtractOut> {
  const { jobId } = await startEcExtract(file, opts);
  return waitEcExtract(jobId, { signal: opts.signal });
}

/** 2단계: 텍스트 → 8섹션 구조화 JSON — 비동기 잡. */
export async function postEcStructure(
  extractedText: string,
  opts: { signal?: AbortSignal } = {},
): Promise<EcStructureOut> {
  const { job_id } = await apiPostJson<{ job_id: string }>(
    '/ec/structures',
    { extracted_text: extractedText },
    { signal: opts.signal },
  );
  return pollJob<EcStructureOut>(
    (id) => `/ec/structures/${id}`,
    job_id,
    (res) =>
      res.structured_data != null
        ? ({
            structured_data: res.structured_data as Record<string, unknown>,
            elapsed_sec: (res.elapsed_sec as number) ?? 0,
            model: (res.model as string) ?? '',
          } as unknown as EcStructureOut)
        : undefined,
    { signal: opts.signal, label: '문서 정리' },
  );
}

/** AI 1차 분류 결과 — 근로자 유형·문서 종류 추정. */
export interface EcClassifyOut {
  worker_types: string[];
  doc_kind: string;
  reason: string;
}

/**
 * 2.5단계: AI 1차 분류 — 추출 텍스트로 근로자 유형(정규직·기간제 등)과
 * 문서 종류를 먼저 판단. 사용자는 검토 페이지에서 "맞아요/아니에요" 로 확인만 한다.
 *
 * structure 와 병렬 호출되며, 실패해도 폼 입력값 fallback 으로 흐름이 끊기지 않는다.
 */
export async function postEcClassify(
  extractedText: string,
  opts: { signal?: AbortSignal } = {},
): Promise<EcClassifyOut> {
  const { job_id } = await apiPostJson<{ job_id: string }>(
    '/ec/classifications',
    { extracted_text: extractedText },
    { signal: opts.signal },
  );
  return pollJob<EcClassifyOut>(
    (id) => `/ec/classifications/${id}`,
    job_id,
    (res) =>
      res.worker_types != null
        ? {
            worker_types: res.worker_types as string[],
            doc_kind: (res.doc_kind as string) ?? '',
            reason: (res.reason as string) ?? '',
          }
        : undefined,
    { signal: opts.signal, label: '문서 분류' },
  );
}

/** 폴링 sleep — AbortSignal 지원. */
function sleep(ms: number, signal?: AbortSignal): Promise<void> {
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
 * 3단계: 33매핑 분석 — 비동기 잡(start + poll) 방식.
 *
 * 동기 단일 요청은 Render cold start + 분석 시간이 합쳐져 Vercel 60초 함수
 * 타임아웃에 걸려 'Unterminated JSON' 으로 실패했다. 이제:
 *   1) POST /ec/analyses 로 job_id 만 즉시 받고 (백엔드는 백그라운드 스레드 실행)
 *   2) GET /ec/analyses/{job_id} 를 짧게 폴링 — 각 요청 1초 미만이라 타임아웃 무관
 * 분석이 아무리 오래 걸려도(느려도) 끊기지 않고 반드시 완료된다.
 */
export async function postEcAnalyze(
  structuredData: EcStructuredData,
  businessSize: string,
  workerTypes: string[],
  opts: { legalGuidelines?: string; signal?: AbortSignal; caseId?: string } = {},
): Promise<EcAnalyzeOut> {
  const { job_id } = await apiPostJson<{ job_id: string }>(
    '/ec/analyses',
    {
      structured_data: structuredData,
      business_size: businessSize,
      worker_types: workerTypes,
      legal_guidelines: opts.legalGuidelines ?? '',
      case_id: opts.caseId ?? '',
    },
    { signal: opts.signal },
  );

  const POLL_MS = 2500;
  const MAX_WAIT_MS = 6 * 60 * 1000; // 6분 하드 캡
  const startedAt = Date.now();
  // 첫 폴링 전 약간 대기 — 짧은 작업이면 한 번에 done
  for (;;) {
    await sleep(POLL_MS, opts.signal);
    const res = await apiGet<{
      status: string;
      analysis_result: EcAnalysisResult | null;
      error: string | null;
      elapsed_sec: number;
      model: string;
    }>(`/ec/analyses/${job_id}`, { signal: opts.signal });

    if (res.status === 'done' && res.analysis_result) {
      return {
        analysis_result: res.analysis_result,
        elapsed_sec: res.elapsed_sec,
        model: res.model,
      };
    }
    if (res.status === 'error') {
      throw new ApiCallError(500, res.error || '분석에 실패했어요. 다시 시도해 주세요.');
    }
    if (Date.now() - startedAt > MAX_WAIT_MS) {
      throw new ApiCallError(
        504,
        '분석이 너무 오래 걸려요. 문서가 길거나 서버가 혼잡할 수 있어요. 잠시 후 다시 시도해 주세요.',
      );
    }
  }
}

/** 단일 항목 즉시 재검토 — 표준 계약서 작성 화면에서 칸을 고친 뒤 점(✓/!) 갱신용. */
export async function postEcValidateField(
  body: {
    field: string;
    value: string;
    business_size?: string;
    worker_types?: string[];
  },
  opts: { signal?: AbortSignal } = {},
): Promise<{
  적절성: '적절' | '보완필요' | '부적정' | string;
  이유: string;
  작성예시: string;
}> {
  return apiPostJson('/ec/field-validations', body, { signal: opts.signal });
}

/** 4단계: 분석 결과 → 표준 근로계약서 텍스트.
 *
 * `userOverrides` 는 사용자가 SuggestBlock 으로 직접 작성한 보완 표현
 * (항목명 → 본인 입력 텍스트). 백엔드 프롬프트의 별도 섹션으로 전달되어
 * 표준 계약서 본문에 그대로 반영된다.
 */
export async function postEcGenerate(
  analysisResult: EcAnalysisResult,
  opts: {
    userOverrides?: Record<string, string>;
    signal?: AbortSignal;
  } = {},
): Promise<EcGenerateOut> {
  // analyze 와 동일하게 비동기 잡(start + poll)로 — 게이트웨이 타임아웃 우회.
  const { job_id } = await apiPostJson<{ job_id: string }>(
    '/ec/drafts',
    {
      analysis_result: analysisResult,
      user_overrides: opts.userOverrides ?? {},
    },
    { signal: opts.signal },
  );

  const POLL_MS = 2500;
  const MAX_WAIT_MS = 6 * 60 * 1000;
  const startedAt = Date.now();
  for (;;) {
    await sleep(POLL_MS, opts.signal);
    const res = await apiGet<{
      status: string;
      contract_text: string | null;
      error: string | null;
      elapsed_sec: number;
      model: string;
    }>(`/ec/drafts/${job_id}`, { signal: opts.signal });

    if (res.status === 'done' && res.contract_text != null) {
      return {
        contract_text: res.contract_text,
        elapsed_sec: res.elapsed_sec,
        model: res.model,
      };
    }
    if (res.status === 'error') {
      throw new ApiCallError(500, res.error || '계약서 생성에 실패했어요. 다시 시도해 주세요.');
    }
    if (Date.now() - startedAt > MAX_WAIT_MS) {
      throw new ApiCallError(504, '계약서 생성이 너무 오래 걸려요. 잠시 후 다시 시도해 주세요.');
    }
  }
}

/** 표준 근로계약서 본문 → .docx 다운로드. */
export async function downloadEcDocx(
  body: { contract_text: string; filename?: string },
): Promise<void> {
  const fname = body.filename ?? '표준_근로계약서.docx';
  const { blob, filename } = await apiPostJsonBlob('/ec/documents', body);
  triggerDownload(blob, filename ?? fname);
}
