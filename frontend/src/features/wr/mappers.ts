/**
 * 백엔드 응답 → 프론트 도메인 타입 매핑.
 *
 * 백엔드 `FindingOut` 에 부족한 필드(title / standard / laws / topics)는
 * 합리적 fallback 으로 채운다. 백엔드 확장 시 fallback 분기 제거.
 */
import { pickTopPriority } from '@/data/sample';
import type {
  Finding,
  FindingStatus,
  LawCitation,
  Penalty,
  PriorityItem,
  ReviewResult,
  ReviewSummary,
  RiskCounts,
  RiskLevel,
} from '@/types/review';

import type {
  ArticleResultOut,
  FindingOut,
  ReviewFullOut,
} from '@/lib/api/types';

/** 백엔드 한글 bucket → 프론트 RiskLevel 키. */
const BUCKET_TO_RISK: Record<string, RiskLevel> = {
  '누락': 'missing',
  '위반': 'violation',
  '주의': 'warn',
  '검토필요': 'ambiguous',
  '적정': 'ok',
};

/** 백엔드 overall_label → frontend verdictKey. */
function toVerdictKey(label: string, counts: RiskCounts): RiskLevel {
  if (label.includes('적정') && !label.includes('부')) return 'ok';
  if ((counts.missing ?? 0) > 0) return 'missing';
  if ((counts.violation ?? 0) > 0) return 'violation';
  if ((counts.warn ?? 0) > 0) return 'warn';
  if ((counts.ambiguous ?? 0) > 0) return 'ambiguous';
  return 'ok';
}

/** "{N} bytes" → 사람용 표기 (KB/MB). 백엔드가 파일 크기를 안 줄 때 alternative. */
function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

/** 초 → "1분 18초" 형식. */
function humanDuration(sec: number): string {
  const total = Math.max(0, Math.round(sec));
  if (total < 60) return `${total}초`;
  const m = Math.floor(total / 60);
  const s = total % 60;
  return s === 0 ? `${m}분` : `${m}분 ${s}초`;
}

/** ISO/현재 시각 → "YYYY-MM-DD HH:mm" */
function formatTs(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** 한국어 첫 문장 추출 — "title" fallback. 마침표/줄바꿈 기준 50자 제한. */
function firstSentence(text: string, max = 60): string {
  if (!text) return '';
  const cleaned = text.replace(/\*\*/g, '').replace(/\s+/g, ' ').trim();
  const period = cleaned.search(/[.。?]/);
  const head = period > 0 ? cleaned.slice(0, period) : cleaned;
  return head.length > max ? head.slice(0, max - 1) + '…' : head;
}

/** "근로기준법 제53조" 같은 법령명 추출. penalty 문자열에서 첫 매치. */
const LAW_RE =
  /(근로기준법|남녀고용평등(?:과 일·가정 양립 지원에 관한)? ?법(?:률)?|산업안전보건법|근로자퇴직급여 ?보장법|근로자의 ?날 ?제정에 ?관한 ?법률|고용상 ?연령차별금지[가-힣]*법(?:률)?)\s*제\s*\d+조(?:의\d+)?(?:\s*제\s*\d+(?:항|호))*/g;

function extractLawsFromPenalty(items: string[]): LawCitation[] {
  const seen = new Set<string>();
  const out: LawCitation[] = [];
  for (const line of items) {
    const matches = line.match(LAW_RE);
    if (!matches) continue;
    for (const name of matches) {
      const key = name.replace(/\s+/g, ' ').trim();
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ name: key, text: line });
    }
  }
  return out;
}

/** comparator 추정 — extracted_value 와 기준 차이 (백엔드 미제공이라 빈 string fallback). */
function inferStandard(_f: FindingOut): string {
  // 백엔드가 standard 를 안 주므로 빈 값. 추후 backend FindingOut 확장 시 채움.
  return '';
}

/**
 * 슬롯 추출 dict 의 key → 한국어 라벨.
 *
 * 백엔드 슬롯 카탈로그의 `extracted_value` dict 가 사용자 화면에 그대로 노출되면
 * `{"default_months":12,"special_extension_months":null}` 같은 raw JSON 이 보이는데,
 * 이건 자율점검 사용자에게 부적절. 이 매핑 + `formatExtractedValue` 로 자연어로 변환.
 *
 * 신규 슬롯이 추가되어 매핑이 없는 key 도 보기 좋게 처리 — snake_case 를
 * 공백 구분 단어로 변환해 fallback.
 */
const EXTRACTED_KEY_LABELS: Record<string, string> = {
  // 휴직·휴가
  default_months: '기본 기간',
  special_extension_months: '특별연장 기간',
  default_days: '기본 일수',
  extension_days: '연장 일수',
  paid: '유급 여부',
  // 임금
  hourly_wage: '시급',
  monthly_wage: '월급',
  base_wage: '기본급',
  allowance: '수당',
  // 시간
  daily_hours: '1일 근로시간',
  weekly_hours: '1주 근로시간',
  break_minutes: '휴게시간(분)',
  // 일반
  amount: '금액',
  rate: '비율',
  count: '건수',
  years: '연수',
  months: '개월',
  days: '일수',
  hours: '시간',
  percent: '비율(%)',
  yes: '예',
  no: '아니오',
  description: '설명',
  note: '비고',
  type: '구분',
  text: '문구',
  value: '값',
};

function humanizeKey(key: string): string {
  if (EXTRACTED_KEY_LABELS[key]) return EXTRACTED_KEY_LABELS[key];
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function humanizeValue(v: unknown): string {
  if (v === null || v === undefined) return '없음';
  if (typeof v === 'string') {
    if (!v.trim()) return '없음';
    return v;
  }
  if (typeof v === 'number') {
    // 큰 숫자엔 천단위 콤마
    return v.toLocaleString('ko-KR');
  }
  if (typeof v === 'boolean') return v ? '예' : '아니오';
  if (Array.isArray(v)) {
    if (v.length === 0) return '없음';
    return v.map((x) => humanizeValue(x)).join(', ');
  }
  // object — 재귀적으로 풀기
  return formatExtractedObject(v as Record<string, unknown>);
}

function formatExtractedObject(obj: Record<string, unknown>): string {
  const entries = Object.entries(obj);
  if (entries.length === 0) return '없음';
  return entries
    .map(([k, val]) => `${humanizeKey(k)}: ${humanizeValue(val)}`)
    .join(' · ');
}

/**
 * `extracted_value` → 사람용 자연어 문자열.
 *
 * - 문자열·숫자·불리언은 그대로
 * - 배열·객체는 자연어 한 줄로 정리 (`{default_months:12, special_extension_months:null}`
 *   → `기본 기간: 12 · 특별연장 기간: 없음`)
 * - JSON 파싱 가능한 문자열도 객체로 풀어줌 (백엔드가 JSON 문자열로 줄 수 있음)
 */
function formatExtracted(v: unknown): string {
  if (v === null || v === undefined) return '';
  if (typeof v === 'string') {
    const trimmed = v.trim();
    if (!trimmed) return '';
    // 백엔드가 dict 를 JSON 문자열로 직렬화해 보낼 수 있음 — 그 경우 풀어줌
    if (
      (trimmed.startsWith('{') && trimmed.endsWith('}')) ||
      (trimmed.startsWith('[') && trimmed.endsWith(']'))
    ) {
      try {
        const parsed = JSON.parse(trimmed);
        return humanizeValue(parsed);
      } catch {
        // JSON 아니면 문자열 그대로
      }
    }
    return trimmed;
  }
  if (typeof v === 'number') return v.toLocaleString('ko-KR');
  if (typeof v === 'boolean') return v ? '있음' : '없음';
  if (Array.isArray(v)) return humanizeValue(v);
  if (typeof v === 'object') return formatExtractedObject(v as Record<string, unknown>);
  return String(v);
}

/** FindingOut → Finding. ar.title 을 articleTitle 로 같이 받아온다. */
export function mapFinding(f: FindingOut, articleTitle: string, runningIdx: number): Finding {
  const risk = BUCKET_TO_RISK[f.bucket] ?? 'ok';
  const reason = (f.user_reason || f.reason || '').trim();
  const extracted = formatExtracted(f.extracted_value);
  const laws = extractLawsFromPenalty([
    ...(f.penalty_omission ?? []),
    ...(f.penalty_violation ?? []),
  ]);
  const penalty: Penalty = {
    omission: f.penalty_omission ?? [],
    violation: f.penalty_violation ?? [],
  };

  return {
    // 사용자 노출용 짧은 ID — 백엔드 slot_id 만 받으므로 일련번호로 보완
    id: `F-${String(runningIdx + 1).padStart(3, '0')}`,
    slotId: f.slot_id,
    article: `제${f.article}조`,
    articleTitle,
    risk,
    status: (f.status as FindingStatus) ?? 'OK',
    title: firstSentence(reason) || f.slot_id,
    reason,
    quote: f.quote ?? '',
    extracted,
    standard: inferStandard(f),
    laws,
    penalty,
    suggested: f.fix_example ?? '',
    topics: [], // 백엔드 미제공 — 추후 slot meta join
  };
}

/** ReviewFullOut → ReviewResult (summary + findings 평탄화). */
export function mapReviewResult(r: ReviewFullOut): ReviewResult {
  const counts: RiskCounts = {
    missing: r.summary['누락'] ?? 0,
    violation: r.summary['위반'] ?? 0,
    warn: r.summary['주의'] ?? 0,
    ambiguous: r.summary['검토필요'] ?? 0,
    ok: r.summary['적정'] ?? 0,
    skipped: 0, // 백엔드 별도 채널 (optional_displays)
  };

  // findings 평탄화 + articleTitle 채움
  const findings: Finding[] = [];
  let idx = 0;
  for (const ar of r.article_results ?? []) {
    for (const f of ar.findings) {
      findings.push(mapFinding(f, ar.title || '', idx));
      idx++;
    }
  }

  const total = (counts.missing ?? 0) + (counts.violation ?? 0) +
    (counts.warn ?? 0) + (counts.ambiguous ?? 0) + (counts.ok ?? 0);

  const summary: ReviewSummary = {
    verdict: r.overall_label || '검토 완료',
    verdictKey: toVerdictKey(r.overall_label, counts),
    fileName: r.filename || 'review.docx',
    fileSize: '', // 백엔드 미제공
    reviewedAt: formatTs(new Date()),
    duration: humanDuration(r.elapsed_sec),
    totalSlots: total,
    counts,
    articles: 98, // 표준취업규칙 마스터 총 조 수
    topPriority: pickTopPriority(findings, 3),
  };

  return { summary, findings };
}

// 활용도 낮은 함수지만 export 유지 — humanSize 는 fileSize 채울 때 쓸 수 있음
export { humanSize, formatTs };

// 미사용 import 경고 회피용 — PriorityItem 는 mapReviewResult 가 간접 사용
export type _UnusedPriorityItem = PriorityItem;
