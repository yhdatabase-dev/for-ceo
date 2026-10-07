'use client';

/**
 * 표준근로계약서 양식 화면 — 고용노동부 표준 서식(2019.6) 레이아웃 재현.
 *
 * 생성 텍스트 대신 **공식 표준 양식 모양 그대로** 보여주고, 사용자의 계약
 * 내용을 해당 칸에 채워 넣는다. 채움 규칙은 결정적(deterministic):
 *   1) structuredData(8섹션)의 value 를 양식 칸에 매핑 (LLM 자유 텍스트 파싱 금지)
 *   2) 분석 항목이 부적절/보완필요로 판정된 칸은
 *      - 사용자가 SuggestBlock 에서 담은 표현(userOverrides)이 "칸에 넣을 수
 *        있는 값"이면 그 값으로 (보완됨·override)
 *      - 아니면 공식 양식의 표준 문구로 (보완됨·standard)
 *      - 표준 문구가 없는 칸(금액 등)은 원래 값 유지 + 확인필요 표시
 *   3) 비어있으면 빈 밑줄 칸으로 둠
 *
 * 모든 칸은 controlled input — 수정 즉시 onChange 로 상위(page)에 전달되어
 * 다운로드(.docx)/복사/인쇄가 항상 최신 편집본을 사용한다.
 */
import { useCallback, useState } from 'react';

import type {
  EcAnalysisResult,
  EcStructuredData,
  EcStructuredField,
} from '@/lib/api/types';

import styles from './ContractFormView.module.css';

/* ───────────────────────── 타입 ───────────────────────── */

export type EcFormFieldId =
  | 'employerName'
  | 'workerName'
  | 'startDate'
  | 'workplace'
  | 'jobDesc'
  | 'workHours'
  | 'breakTime'
  | 'workDays'
  | 'weeklyHoliday'
  | 'wageAmount'
  | 'bonus'
  | 'otherAllowance'
  | 'payday'
  | 'payMethod'
  | 'annualLeave'
  | 'delivery'
  | 'compliance'
  | 'etcClause'
  | 'contractDate'
  | 'employerCompany'
  | 'employerPhone'
  | 'employerAddress'
  | 'employerRep'
  | 'workerAddress'
  | 'workerContact'
  | 'workerSignName';

export const INSURANCE_KEYS = [
  '고용보험',
  '산재보험',
  '국민연금',
  '건강보험',
] as const;
export type InsuranceKey = (typeof INSURANCE_KEYS)[number];

export interface MinorConsent {
  guardian: string;
  relation: string;
  contact: string;
}

export interface ContractFormState {
  fields: Record<EcFormFieldId, string>;
  insurance: Record<InsuranceKey, boolean>;
  /** 1번 조항 라벨 — 기간의 정함 여부에 따라 (structuredData 값으로 결정). */
  periodLabel: '근로개시일' | '근로계약기간';
  /** 근로자 유형 표시 라벨 (예: "기간제·단시간"). */
  contractType?: string;
  /** 분류 유형 목록 — 유형별 섹션 분기용. */
  workerTypes?: string[];
  /** 연소자(18세 미만) — 친권자(후견인) 동의 (해당 유형일 때만). */
  minor?: MinorConsent;
}

/**
 * 칸 표시 플래그.
 * - standard  : 표준 양식 문구로 보완됨 (초록 점)
 * - override  : 사용자가 담은 표현으로 보완됨 (초록 점)
 * - attention : 부적절/보완필요 판정인데 자동 보완 불가 — 직접 확인 (노랑 점)
 * - ok        : 사용자가 고친 뒤 재검토 결과 **적정** (초록 ✓, 팝오버 없음)
 * - invalid   : 사용자가 고친 뒤 재검토 결과 **부적정** (빨강 !)
 */
export type FieldFlag = 'standard' | 'override' | 'attention' | 'ok' | 'invalid';

export type EcFormFlags = Partial<
  Record<EcFormFieldId | 'insurance' | 'signature', FieldFlag>
>;

/** 칸 → 연관 분석 항목명(항목). 칩 클릭 시 우측 상세로 이동하는 데 사용. */
export type EcFormItems = Partial<
  Record<EcFormFieldId | 'insurance' | 'signature', string>
>;

export interface EcFormModel {
  state: ContractFormState;
  flags: EcFormFlags;
  items: EcFormItems;
  /** 칸 → 수정 권고안(개선권고 또는 사용자 보완 표현). 점 호버 팝오버·복사용. */
  suggestions: EcFormItems;
}

/* ───────────────────── 표준 양식 기본 문구 ───────────────────── */
/* 출처: 고용노동부 표준근로계약서(기간의 정함이 없는 경우) 서식 본문. */

const STANDARD_PHRASES: Partial<Record<EcFormFieldId, string>> = {
  payday: '매월(매주 또는 매일)      일 (휴일의 경우는 전일 지급)',
  payMethod: '근로자에게 직접지급 또는 근로자 명의 예금통장에 입금',
  annualLeave: '연차유급휴가는 근로기준법에서 정하는 바에 따라 부여함',
  delivery:
    '사업주는 근로계약을 체결함과 동시에 본 계약서를 사본하여 근로자의 교부요구와 관계없이 근로자에게 교부함(근로기준법 제17조 이행)',
  compliance:
    '사업주와 근로자는 각자가 근로계약, 취업규칙, 단체협약을 지키고 성실하게 이행하여야 함',
  etcClause: '이 계약에 정함이 없는 사항은 근로기준법령에 의함',
};

/* ───────────────── structuredData → 칸 매핑 스펙 ───────────────── */

interface FieldSpec {
  /** structuredData 우선 탐색 섹션들. */
  sections: string[];
  /** 후보 키들 (여러 표기 허용 — 정확 일치 → 정규화 포함 순). */
  keys: string[];
  /**
   * 분석 결과 항목명 매칭 패턴 (정규화 후 비교).
   * '=' 접두는 정확 일치만 허용 (예: '=임금' 은 '임금 구성항목' 과 매칭 안 됨).
   */
  patterns: string[];
}

const FIELD_SPECS: Record<EcFormFieldId, FieldSpec> = {
  employerName: {
    sections: ['기본정보'],
    keys: ['사업장명', '사업주성명', '상호', '회사명'],
    patterns: [],
  },
  workerName: {
    sections: ['기본정보'],
    keys: ['근로자성명', '성명'],
    patterns: [],
  },
  startDate: {
    sections: ['계약사항'],
    keys: ['근로계약기간', '근로개시일', '계약기간'],
    patterns: ['근로개시일', '근로계약기간'],
  },
  workplace: {
    sections: ['계약사항'],
    keys: ['근무장소', '근무지'],
    patterns: ['근무장소'],
  },
  jobDesc: {
    sections: ['계약사항'],
    keys: ['업무내용', '업무의내용', '담당업무'],
    patterns: ['업무내용', '업무의내용'],
  },
  workHours: {
    sections: ['근로시간'],
    keys: ['소정근로시간'],
    patterns: ['소정근로시간'],
  },
  breakTime: {
    sections: ['근로시간'],
    keys: ['휴게시간'],
    patterns: ['휴게시간'],
  },
  workDays: {
    sections: ['휴일휴가'],
    keys: ['근무일', '근로일'],
    patterns: ['근무일휴일', '=근무일', '=근로일'],
  },
  weeklyHoliday: {
    sections: ['휴일휴가'],
    keys: ['주휴일'],
    patterns: ['근무일휴일', '주휴일'],
  },
  wageAmount: {
    sections: ['임금'],
    keys: ['임금총액', '기본급', '월급', '일당', '시간급'],
    patterns: ['=임금', '임금총액', '임금계산방법', '=일당'],
  },
  bonus: {
    sections: ['임금'],
    keys: ['상여금'],
    patterns: ['상여금'],
  },
  otherAllowance: {
    sections: ['임금'],
    keys: ['제수당', '기타급여', '수당'],
    patterns: ['제수당', '기타급여', '임금구성항목'],
  },
  payday: {
    sections: ['임금'],
    keys: ['임금지급일', '지급일'],
    patterns: ['임금지급시기', '임금지급일'],
  },
  payMethod: {
    sections: ['임금'],
    keys: ['임금지급방법', '지급방법'],
    patterns: ['임금지급방법', '지급방법'],
  },
  annualLeave: {
    sections: ['휴일휴가'],
    keys: ['연차유급휴가', '연차'],
    patterns: ['연차유급휴가', '=연차'],
  },
  delivery: {
    sections: ['계약사항', '계약체결'],
    keys: ['근로계약서교부', '계약서교부'],
    patterns: ['근로계약서교부', '계약서교부'],
  },
  compliance: { sections: [], keys: [], patterns: [] },
  etcClause: { sections: [], keys: [], patterns: [] },
  contractDate: {
    sections: ['계약체결'],
    keys: ['계약서작성일', '작성일'],
    patterns: ['계약서작성일', '작성일'],
  },
  employerCompany: {
    sections: ['기본정보'],
    keys: ['사업장명', '상호', '회사명'],
    patterns: ['사용자정보', '사업주정보'],
  },
  employerPhone: {
    sections: ['기본정보'],
    keys: ['사업장전화', '회사전화', '대표전화'],
    patterns: [],
  },
  employerAddress: {
    sections: ['기본정보'],
    keys: ['사업장소재지', '사업장주소', '소재지'],
    patterns: [],
  },
  employerRep: {
    sections: ['기본정보'],
    keys: ['사업주성명', '대표자', '대표자성명'],
    patterns: [],
  },
  workerAddress: {
    sections: ['기본정보'],
    keys: ['근로자주소'],
    patterns: ['근로자정보'],
  },
  workerContact: {
    sections: ['기본정보'],
    keys: ['근로자연락처', '근로자전화'],
    patterns: [],
  },
  workerSignName: {
    sections: ['기본정보'],
    keys: ['근로자성명'],
    patterns: [],
  },
};

const FIELD_IDS = Object.keys(FIELD_SPECS) as EcFormFieldId[];

/* ───────────────────────── 헬퍼 ───────────────────────── */

function isFieldMap(v: unknown): v is Record<string, EcStructuredField> {
  return (
    typeof v === 'object' &&
    v !== null &&
    !Array.isArray(v) &&
    Object.values(v).every(
      (x) =>
        x !== null &&
        typeof x === 'object' &&
        'value' in (x as Record<string, unknown>),
    )
  );
}

/** 매칭용 정규화 — 공백·구두점 제거. */
function norm(s: string): string {
  return s.replace(/[\s·.\-_/()\[\]]/g, '');
}

/** 미기재/판독불가 등 placeholder 면 '' 로. */
function usable(v: string | undefined | null): string {
  if (!v) return '';
  const t = String(v).trim();
  if (!t) return '';
  const n = norm(t);
  if (
    n.startsWith('미기재') ||
    n.startsWith('판독불가') ||
    n === '해당없음' ||
    n === '알수없음' ||
    n === '-'
  ) {
    return '';
  }
  return t;
}

/**
 * structuredData 에서 칸 값 추출 — 여러 표기를 관대하게 시도.
 * 1) 지정 섹션의 후보 키 정확 일치 → 2) 정규화 포함 일치 → 3) 전체 섹션 fallback.
 */
export function pick(
  sd: EcStructuredData,
  sections: string[],
  keys: string[],
): string {
  if (keys.length === 0) return '';
  const named: Record<string, EcStructuredField>[] = [];
  for (const s of sections) {
    const sec = sd[s];
    if (isFieldMap(sec)) named.push(sec);
  }
  const all: Record<string, EcStructuredField>[] = [];
  for (const [k, v] of Object.entries(sd)) {
    if (k !== '기타사항' && isFieldMap(v)) all.push(v);
  }
  const tryMaps = (maps: Record<string, EcStructuredField>[]): string => {
    // 1) 정확 일치
    for (const m of maps) {
      for (const k of keys) {
        if (m[k]) {
          const v = usable(m[k].value);
          if (v) return v;
        }
      }
    }
    // 2) 정규화 포함 일치
    for (const m of maps) {
      for (const k of keys) {
        const nk = norm(k);
        if (!nk) continue;
        for (const [mk, f] of Object.entries(m)) {
          const nmk = norm(mk);
          if (nmk.includes(nk) || nk.includes(nmk)) {
            const v = usable(f.value);
            if (v) return v;
          }
        }
      }
    }
    return '';
  };
  return tryMaps(named) || tryMaps(all);
}

/** 분석 결과에서 이 칸과 연관된 부적절/보완필요 항목 찾기 (부적절 우선). */
function findFlag(
  analysis: EcAnalysisResult | null,
  patterns: string[],
): { status?: '부적절' | '보완필요'; item?: string } {
  if (!analysis || patterns.length === 0) return {};
  let best: { status: '부적절' | '보완필요'; item: string } | null = null;
  for (const r of analysis.results ?? []) {
    const a = r.적절성;
    if (a !== '부적절' && a !== '보완필요') continue;
    const itemN = norm(r.항목 ?? '');
    if (!itemN) continue;
    const hit = patterns.some((p) =>
      p.startsWith('=') ? itemN === norm(p.slice(1)) : itemN.includes(norm(p)),
    );
    if (!hit) continue;
    if (!best || (a === '부적절' && best.status === '보완필요')) {
      best = { status: a, item: r.항목 };
    }
    if (best.status === '부적절') break;
  }
  return best ?? {};
}

/**
 * userOverrides 값이 "칸에 넣을 수 있는 값"인지 — 설명문이면 버린다.
 * (개선권고·담은 표현은 종종 "~하시기 바랍니다" 류 설명 문장)
 */
function usableOverride(raw: string | undefined): string {
  if (!raw) return '';
  const t = raw.trim().replace(/\s+/g, ' ');
  if (!t || t.length > 120) return '';
  if (/(입니다|합니다|하세요|해주세요|바랍니다|습니다|니다)[.!\s]*$/.test(t)) return '';
  if (/(권고|필요합니다|검토가 필요|보완이 필요|위반 가능|위반될|위반입니다)/.test(t)) return '';
  return t;
}

/* ───────────────────── 모델 빌드 (결정적) ───────────────────── */

/**
 * structuredData + 분석 결과 + 사용자 담은 표현 → 양식 칸 초기값 + 플래그.
 * 순수 함수 — 같은 입력이면 항상 같은 출력 (LLM 텍스트 파싱 없음).
 */
export function buildEcFormModel(
  sd: EcStructuredData,
  analysis: EcAnalysisResult | null,
  overrides: Record<string, string>,
  workerTypes: string[] = [],
  typeLabel = '',
): EcFormModel {
  const fields = {} as Record<EcFormFieldId, string>;
  const flags: EcFormFlags = {};
  const items: EcFormItems = {};
  const suggestions: EcFormItems = {};

  // 항목명 → 수정 권고안(개선권고 또는 사용자 보완 표현) 한 줄 추출 헬퍼.
  const suggestFor = (itemName: string): string =>
    (overrides[itemName] ??
      analysis?.results?.find((r) => r.항목 === itemName)?.개선권고 ??
      '').trim();

  // ── 1) 원본 값 추출 ──
  for (const id of FIELD_IDS) {
    const spec = FIELD_SPECS[id];
    fields[id] = pick(sd, spec.sections, spec.keys);
  }
  // 소정근로시간 — 시업/종업 시각이 따로 있으면 "HH:MM ~ HH:MM" 으로 합성
  const begin = pick(sd, ['근로시간'], ['시업시각', '시업시간', '출근시각']);
  const end = pick(sd, ['근로시간'], ['종업시각', '종업시간', '퇴근시각']);
  if (begin && end) {
    fields.workHours = `${begin} ~ ${end}`;
  }

  // ── 2) 부적절/보완필요 칸 보완 (override → 표준 문구 → 확인필요) ──
  for (const id of FIELD_IDS) {
    const spec = FIELD_SPECS[id];
    const { status, item } = findFlag(analysis, spec.patterns);
    if (!status) continue;
    if (item) {
      items[id] = item;
      const sug = suggestFor(item);
      if (sug) suggestions[id] = sug;
    }
    const ov = usableOverride(item ? overrides[item] : undefined);
    if (ov) {
      fields[id] = ov;
      flags[id] = 'override';
    } else if (STANDARD_PHRASES[id]) {
      fields[id] = STANDARD_PHRASES[id] as string;
      flags[id] = 'standard';
    } else {
      flags[id] = 'attention';
    }
  }

  // ── 3) 고정 조항 — 항상 표준 문구로 채움 (9·10·11조) ──
  if (!fields.compliance) fields.compliance = STANDARD_PHRASES.compliance ?? '';
  if (!fields.etcClause) fields.etcClause = STANDARD_PHRASES.etcClause ?? '';
  // 교부 조항 — 원본 값이 "교부함" 같은 단답이면 표준 문장으로
  if (flags.delivery !== 'override' && fields.delivery.length < 15) {
    fields.delivery = STANDARD_PHRASES.delivery ?? '';
  }

  // ── 4) 1번 조항 라벨 — 유형(기간제·일용직) 우선, 없으면 값 형태로 결정 ──
  const hasTerm = workerTypes.some((t) => /기간제|일용/.test(t));
  const periodLabel: ContractFormState['periodLabel'] =
    hasTerm || /[~∼]|까지/.test(fields.startDate)
      ? '근로계약기간'
      : '근로개시일';

  // ── 5) 사회보험 체크박스 ──
  const insurance = {
    고용보험: false,
    산재보험: false,
    국민연금: false,
    건강보험: false,
  } as Record<InsuranceKey, boolean>;
  const insRaw = pick(
    sd,
    ['사회보험'],
    ['4대보험가입여부', '4대보험', '사회보험', '보험가입'],
  );
  const insFlag = findFlag(analysis, ['사회보험', '4대보험']);
  if (insFlag.status) {
    // 부적절/보완필요 → 표준 양식 기본(4대 보험 모두 체크)으로 보완
    for (const k of INSURANCE_KEYS) insurance[k] = true;
    flags.insurance = 'standard';
    if (insFlag.item) {
      items.insurance = insFlag.item;
      const sug = suggestFor(insFlag.item);
      if (sug) suggestions.insurance = sug;
    }
  } else if (insRaw) {
    const t = norm(insRaw);
    insurance.고용보험 = t.includes('고용');
    insurance.산재보험 = t.includes('산재');
    insurance.국민연금 = t.includes('국민연금') || t.includes('연금');
    insurance.건강보험 = t.includes('건강');
    const anyNamed = INSURANCE_KEYS.some((k) => insurance[k]);
    if (!anyNamed && /4대|전부|모두|가입|적용/.test(t) && !/미가입|미적용|제외/.test(t)) {
      for (const k of INSURANCE_KEYS) insurance[k] = true;
    }
  }

  // ── 6) 서명란 — 자동 보완 불가, 판정만 표시 ──
  const signFlag = findFlag(analysis, ['당사자서명날인', '서명날인', '서명']);
  if (signFlag.status) {
    flags.signature = 'attention';
    if (signFlag.item) {
      items.signature = signFlag.item;
      const sug = suggestFor(signFlag.item);
      if (sug) suggestions.signature = sug;
    }
  }

  // ── 7) 유형별 분기 — 단시간(요일별 근로시간)·연소자(친권자 동의) ──
  const isMinor = workerTypes.some((t) => /연소/.test(t));
  const contractType = typeLabel || workerTypes.join('·') || '';

  const state: ContractFormState = {
    fields,
    insurance,
    periodLabel,
    contractType,
    workerTypes,
  };
  if (isMinor) {
    state.minor = { guardian: '', relation: '', contact: '' };
  }

  return { state, flags, items, suggestions };
}

/* ───────────────────── 텍스트 렌더 (.docx/복사용) ───────────────────── */

function blank(v: string, n = 10): string {
  const t = v.trim();
  return t ? t : '_'.repeat(n);
}

/** 채워진 양식 → 조항 순서대로 평문 렌더 — downloadEcDocx / 복사에 사용. */
export function buildContractText(state: ContractFormState): string {
  const f = state.fields;
  const box = (on: boolean) => (on ? '■' : '□');
  const L: string[] = [];
  L.push('표 준 근 로 계 약 서');
  if (state.contractType) L.push(`(유형: ${state.contractType})`);
  L.push('');
  L.push(
    `${blank(f.employerName, 12)} (이하 “사업주”라 함)과(와) ${blank(f.workerName, 12)} (이하 “근로자”라 함)은 다음과 같이 근로계약을 체결한다.`,
  );
  L.push('');
  L.push(`1. ${state.periodLabel} : ${blank(f.startDate)}`);
  L.push(`2. 근 무 장 소 : ${blank(f.workplace)}`);
  L.push(`3. 업무의 내용 : ${blank(f.jobDesc)}`);
  L.push(
    `4. 소정근로시간 : ${blank(f.workHours)} (휴게시간 : ${blank(f.breakTime)})`,
  );
  L.push(
    `5. 근무일/휴일 : 근무일 ${blank(f.workDays)}, 주휴일 ${blank(f.weeklyHoliday)}`,
  );
  L.push('6. 임  금');
  L.push(`  - 월(일, 시간)급 : ${blank(f.wageAmount)}`);
  L.push(`  - 상여금 : ${blank(f.bonus)}`);
  L.push(`  - 기타급여(제수당 등) : ${blank(f.otherAllowance)}`);
  L.push(`  - 임금지급일 : ${blank(f.payday)}`);
  L.push(`  - 지급방법 : ${blank(f.payMethod)}`);
  L.push('7. 연차유급휴가');
  L.push(`  - ${blank(f.annualLeave)}`);
  L.push('8. 사회보험 적용여부(해당란에 체크)');
  L.push(
    `  ${box(state.insurance.고용보험)} 고용보험  ${box(state.insurance.산재보험)} 산재보험  ${box(state.insurance.국민연금)} 국민연금  ${box(state.insurance.건강보험)} 건강보험`,
  );
  L.push('9. 근로계약서 교부');
  L.push(`  - ${blank(f.delivery)}`);
  L.push('10. 근로계약, 취업규칙 등의 성실한 이행의무');
  L.push(`  - ${blank(f.compliance)}`);
  L.push('11. 기  타');
  L.push(`  - ${blank(f.etcClause)}`);
  if (state.minor) {
    L.push('');
    L.push('12. 친권자(후견인) 동의 (연소근로자)');
    L.push(`  - 친권자(후견인) 성명 : ${blank(state.minor.guardian)}`);
    L.push(`  - 근로자와의 관계 : ${blank(state.minor.relation)}`);
    L.push(`  - 연락처 : ${blank(state.minor.contact, 8)}`);
    L.push('  - 첨부 : 가족관계증명서, 친권자(후견인) 동의서');
  }
  L.push('');
  L.push(f.contractDate.trim() ? f.contractDate.trim() : '        년    월    일');
  L.push('');
  L.push(
    `(사업주) 사업체명 : ${blank(f.employerCompany)} (전화 : ${blank(f.employerPhone, 8)})`,
  );
  L.push(`         주    소 : ${blank(f.employerAddress, 16)}`);
  L.push(`         대 표 자 : ${blank(f.employerRep)} (서명)`);
  L.push(`(근로자) 주    소 : ${blank(f.workerAddress, 16)}`);
  L.push(`         연 락 처 : ${blank(f.workerContact, 8)}`);
  L.push(`         성    명 : ${blank(f.workerSignName)} (서명)`);
  return L.join('\n');
}

/* ───────────────────────── 컴포넌트 ───────────────────────── */

/** 근로자 유형 → 고용노동부 표준근로계약서 공식 제목(괄호 변형). */
function ecOfficialTitle(workerTypes: string[] = []): string {
  const has = (re: RegExp) => workerTypes.some((t) => re.test(t));
  if (has(/연소/)) return '표준근로계약서(연소근로자)';
  if (has(/외국인/)) return '표준근로계약서(외국인근로자)';
  if (has(/단시간/)) return '표준근로계약서(단시간근로자)';
  if (has(/기간제|일용/)) return '표준근로계약서(기간의 정함이 있는 경우)';
  return '표준근로계약서(기간의 정함이 없는 경우)';
}

const FLAG_WRAP_CLASS: Record<FieldFlag, string> = {
  standard: styles.flagFix,
  override: styles.flagFix,
  attention: styles.flagWarn,
  ok: styles.flagOk,
  invalid: styles.flagInvalid,
};

/**
 * 칸 옆 상태 점(dot) — 텍스트 배지가 양식 레이아웃을 깨뜨려 색 점으로 표시.
 * 색: 초록=보완됨, 주황=확인 필요. 의미는 title/aria-label.
 *
 * 수정 권고안(suggestion)이 있으면 **호버 시 팝오버**로 그 권고안을 보여주고
 * '복사' 로 바로 붙여넣을 수 있다. (onClick 이 있으면 검토 결과 네비용 클릭 점 —
 * 현재 작성 화면에선 미사용.)
 */
function DotMarker({
  flag,
  suggestion,
  onClick,
}: {
  flag: FieldFlag | undefined;
  suggestion?: string;
  onClick?: () => void;
}) {
  const [copied, setCopied] = useState(false);
  if (!flag) return null;

  // 재검토 결과 — 적정(✓)·부적정(!) 은 점 대신 글리프로(요청: 고치면 점→✓/!).
  if (flag === 'ok') {
    return (
      <span
        className={`${styles.mark} ${styles.markOk}`}
        title="재검토 결과: 적정"
        aria-label="적정"
      >
        ✓
      </span>
    );
  }
  if (flag === 'invalid') {
    const m = (
      <span
        className={`${styles.mark} ${styles.markInvalid}`}
        title={suggestion ? `부적정 — ${suggestion}` : '재검토 결과: 부적정'}
        aria-label="부적정"
        tabIndex={suggestion ? 0 : undefined}
      >
        !
      </span>
    );
    if (!suggestion) return m;
    return (
      <span className={styles.dotWrap}>
        {m}
        <span className={styles.dotPop} role="tooltip">
          <span className={`${styles.dotPopTag} ${styles.dotPopTagWarn}`}>
            부적정 — 사유
          </span>
          <span className={styles.dotPopText}>{suggestion}</span>
        </span>
      </span>
    );
  }

  const isWarn = flag === 'attention';
  const label = isWarn ? '확인 필요' : '보완됨';
  const dotCls = `${styles.dot} ${isWarn ? styles.dotWarn : styles.dotFix}`;

  if (onClick) {
    return (
      <button
        type="button"
        className={`${dotCls} ${styles.dotBtn}`}
        onClick={onClick}
        title={`${label} — 상세 보기`}
        aria-label={label}
      />
    );
  }

  if (!suggestion) {
    return <span className={dotCls} title={label} aria-label={label} />;
  }

  const copy = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(suggestion);
      } else {
        const ta = document.createElement('textarea');
        ta.value = suggestion;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        ta.remove();
      }
    } catch {
      /* noop */
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <span className={styles.dotWrap}>
      <span className={dotCls} title={label} aria-label={label} tabIndex={0} />
      <span className={styles.dotPop} role="tooltip">
        <span
          className={`${styles.dotPopTag} ${isWarn ? styles.dotPopTagWarn : styles.dotPopTagFix}`}
        >
          {isWarn ? '확인 필요 — 권고안' : '보완 예시'}
        </span>
        <span className={styles.dotPopText}>{suggestion}</span>
        <button
          type="button"
          className={styles.dotPopCopy}
          onClick={copy}
          onMouseDown={(e) => e.preventDefault()}
        >
          {copied ? '✓ 복사됨' : '📋 복사해서 붙여넣기'}
        </button>
      </span>
    </span>
  );
}

interface ContractFormViewProps {
  value: ContractFormState;
  flags: EcFormFlags;
  onChange: (next: ContractFormState) => void;
  /** 칸 → 연관 분석 항목명. onFlagClick 과 함께 있으면 칩이 클릭 가능해짐. */
  flagItems?: EcFormItems;
  /** 칩 클릭 시 호출(항목명 전달) — 검토 결과 우측 상세로 이동에 사용. */
  onFlagClick?: (item: string) => void;
  /** 칸 → 수정 권고안. 점 호버 시 팝오버로 보여주고 복사 가능. */
  suggestions?: EcFormItems;
  /** 칸별 재검토 결과 — 사용자가 고친 뒤 AI 재판정(✓ 적정 / ! 부적정). flags 를 덮어쓴다. */
  revalidated?: Partial<
    Record<
      EcFormFieldId,
      { flag: 'ok' | 'invalid'; reason?: string; example?: string }
    >
  >;
  /** 칸별 재검토 진행 중 표시. */
  validating?: Partial<Record<EcFormFieldId, boolean>>;
  /** 칸 편집 후 포커스 아웃 시 호출 — 부모가 그 칸만 재검토. (label = 칸 표시명) */
  onFieldBlur?: (id: EcFormFieldId, value: string, label: string) => void;
}

export default function ContractFormView({
  value,
  flags,
  onChange,
  flagItems,
  onFlagClick,
  suggestions,
  revalidated,
  validating,
  onFieldBlur,
}: ContractFormViewProps) {
  // 칩 클릭 핸들러 — 해당 칸에 연관 항목명이 있고 onFlagClick 이 있을 때만.
  const chipClick = (
    key: EcFormFieldId | 'insurance' | 'signature',
  ): (() => void) | undefined => {
    const item = flagItems?.[key];
    return item && onFlagClick ? () => onFlagClick(item) : undefined;
  };
  const setField = useCallback(
    (id: EcFormFieldId, v: string) => {
      onChange({ ...value, fields: { ...value.fields, [id]: v } });
    },
    [value, onChange],
  );

  const toggleInsurance = useCallback(
    (k: InsuranceKey) => {
      onChange({
        ...value,
        insurance: { ...value.insurance, [k]: !value.insurance[k] },
      });
    },
    [value, onChange],
  );

  const autoGrow = useCallback((el: HTMLTextAreaElement | null) => {
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, []);

  const setMinor = useCallback(
    (key: keyof MinorConsent, v: string) => {
      const base: MinorConsent = value.minor ?? {
        guardian: '',
        relation: '',
        contact: '',
      };
      onChange({ ...value, minor: { ...base, [key]: v } });
    },
    [value, onChange],
  );

  // 주의: 컴포넌트가 아닌 일반 함수 — 매 렌더 새 컴포넌트 타입이 되면
  // input 이 remount 되어 포커스를 잃는다.
  // 재검토 결과(revalidated)가 있으면 원래 flag 를 덮어쓴다. 점 호버 텍스트도 재검토 사유 우선.
  const effFlag = (id: EcFormFieldId): FieldFlag | undefined =>
    revalidated?.[id]?.flag ?? flags[id];
  const effSuggestion = (id: EcFormFieldId): string | undefined =>
    revalidated?.[id] ? revalidated[id]?.reason : suggestions?.[id];

  // 부적정 재검토 칸 밑줄에 띄울 간단 작성 예시.
  // 재검토 작성예시(rv.example)가 비면 그 항목의 기존 개선권고(suggestions)로 폴백 →
  // 부적정인데 예시가 안 뜨는 일이 없도록.
  const renderExample = (id: EcFormFieldId) => {
    const rv = revalidated?.[id];
    if (!rv || rv.flag !== 'invalid') return null;
    const ex = (rv.example || '').trim() || (suggestions?.[id] || '').trim();
    if (!ex) return null;
    return (
      <span className={styles.fieldExample}>
        <span className={styles.fieldExampleTag}>작성 예시</span>
        {ex}
      </span>
    );
  };

  const renderField = (
    id: EcFormFieldId,
    label: string,
    w: 'sm' | 'md' | 'lg' | 'xl' | 'full' = 'md',
  ) => {
    const flag = effFlag(id);
    return (
      <>
        <span
          className={`${styles.fieldWrap} ${flag ? FLAG_WRAP_CLASS[flag] : ''}`}
        >
          <input
            type="text"
            className={`${styles.field} ${styles[`w_${w}`]}`}
            value={value.fields[id]}
            onChange={(e) => setField(id, e.target.value)}
            onBlur={(e) => onFieldBlur?.(id, e.target.value, label)}
            aria-label={label}
            spellCheck={false}
          />
          {validating?.[id] ? (
            <span className={styles.revalidating} title="재검토 중" aria-label="재검토 중">
              ⟳
            </span>
          ) : (
            <DotMarker flag={flag} suggestion={effSuggestion(id)} onClick={chipClick(id)} />
          )}
        </span>
        {renderExample(id)}
      </>
    );
  };

  const renderArea = (id: EcFormFieldId, label: string) => {
    const flag = effFlag(id);
    return (
      <>
        <span
          className={`${styles.areaWrap} ${flag ? FLAG_WRAP_CLASS[flag] : ''}`}
        >
          <textarea
            ref={autoGrow}
            rows={2}
            className={styles.area}
            value={value.fields[id]}
            onChange={(e) => setField(id, e.target.value)}
            onInput={(e) => autoGrow(e.currentTarget)}
            onBlur={(e) => onFieldBlur?.(id, e.target.value, label)}
            aria-label={label}
            spellCheck={false}
          />
          {validating?.[id] ? (
            <span className={styles.revalidating} title="재검토 중" aria-label="재검토 중">
              ⟳
            </span>
          ) : (
            <DotMarker flag={flag} suggestion={effSuggestion(id)} onClick={chipClick(id)} />
          )}
        </span>
        {renderExample(id)}
      </>
    );
  };

  return (
    <div className={styles.paper}>
      <div className={styles.titleBox}>
        <h2 className={styles.formTitle}>{ecOfficialTitle(value.workerTypes)}</h2>
        {value.contractType && (
          <div className={styles.typeBadgeRow}>
            <span className={styles.typeBadge}>{value.contractType}</span>
          </div>
        )}
      </div>

      <p className={styles.intro}>
        {renderField('employerName', '사업주 명칭', 'md')}
        <span className={styles.introText}>(이하 “사업주”라 함)과(와)</span>
        {renderField('workerName', '근로자 성명', 'md')}
        <span className={styles.introText}>
          (이하 “근로자”라 함)은 다음과 같이 근로계약을 체결한다.
        </span>
      </p>

      <ol className={styles.clauses}>
        <li className={styles.clause}>
          <span className={styles.clauseLabel}>1. {value.periodLabel} :</span>
          {renderField('startDate', value.periodLabel, 'lg')}
        </li>

        <li className={styles.clause}>
          <span className={styles.clauseLabel}>2. 근 무 장 소 :</span>
          {renderField('workplace', '근무장소', 'lg')}
        </li>

        <li className={styles.clause}>
          <span className={styles.clauseLabel}>3. 업무의 내용 :</span>
          {renderField('jobDesc', '업무의 내용', 'lg')}
        </li>

        <li className={styles.clause}>
          <span className={styles.clauseLabel}>4. 소정근로시간 :</span>
          {renderField('workHours', '소정근로시간', 'md')}
          <span className={styles.inlineText}>(휴게시간 :</span>
          {renderField('breakTime', '휴게시간', 'md')}
          <span className={styles.inlineText}>)</span>
        </li>

        <li className={styles.clause}>
          <span className={styles.clauseLabel}>5. 근무일/휴일 :</span>
          <span className={styles.inlineText}>근무일</span>
          {renderField('workDays', '근무일', 'md')}
          <span className={styles.inlineText}>, 주휴일</span>
          {renderField('weeklyHoliday', '주휴일', 'sm')}
        </li>

        <li className={styles.clause}>
          <span className={styles.clauseLabel}>6. 임 금</span>
          <ul className={styles.subList}>
            <li className={styles.subLine}>
              <span className={styles.subLabel}>- 월(일, 시간)급 :</span>
              {renderField('wageAmount', '임금 (월·일·시간급)', 'lg')}
            </li>
            <li className={styles.subLine}>
              <span className={styles.subLabel}>- 상여금 :</span>
              {renderField('bonus', '상여금', 'lg')}
            </li>
            <li className={styles.subLine}>
              <span className={styles.subLabel}>- 기타급여(제수당 등) :</span>
              {renderField('otherAllowance', '기타급여(제수당 등)', 'lg')}
            </li>
            <li className={styles.subLine}>
              <span className={styles.subLabel}>- 임금지급일 :</span>
              {renderField('payday', '임금지급일', 'xl')}
            </li>
            <li className={styles.subLine}>
              <span className={styles.subLabel}>- 지급방법 :</span>
              {renderField('payMethod', '임금 지급방법', 'xl')}
            </li>
          </ul>
        </li>

        <li className={styles.clause}>
          <span className={styles.clauseLabel}>7. 연차유급휴가</span>
          <ul className={styles.subList}>
            <li className={styles.subLine}>
              <span className={styles.subLabel}>-</span>
              {renderField('annualLeave', '연차유급휴가', 'full')}
            </li>
          </ul>
        </li>

        <li className={styles.clause}>
          <span className={styles.clauseLabel}>
            8. 사회보험 적용여부(해당란에 체크)
            <DotMarker
              flag={flags.insurance}
              suggestion={suggestions?.insurance}
              onClick={chipClick('insurance')}
            />
          </span>
          <div className={styles.checkRow}>
            {INSURANCE_KEYS.map((k) => (
              <label key={k} className={styles.checkItem}>
                <input
                  type="checkbox"
                  checked={value.insurance[k]}
                  onChange={() => toggleInsurance(k)}
                  aria-label={k}
                />
                <span>{k}</span>
              </label>
            ))}
          </div>
        </li>

        <li className={styles.clause}>
          <span className={styles.clauseLabel}>9. 근로계약서 교부</span>
          <div className={styles.subLine}>
            <span className={styles.subLabel}>-</span>
            {renderArea('delivery', '근로계약서 교부')}
          </div>
        </li>

        <li className={styles.clause}>
          <span className={styles.clauseLabel}>
            10. 근로계약, 취업규칙 등의 성실한 이행의무
          </span>
          <div className={styles.subLine}>
            <span className={styles.subLabel}>-</span>
            {renderArea('compliance', '성실한 이행의무')}
          </div>
        </li>

        <li className={styles.clause}>
          <span className={styles.clauseLabel}>11. 기 타</span>
          <div className={styles.subLine}>
            <span className={styles.subLabel}>-</span>
            {renderArea('etcClause', '기타')}
          </div>
        </li>

        {value.minor && (
          <li className={styles.clause}>
            <span className={styles.clauseLabel}>
              12. 친권자(후견인) 동의 <em className={styles.typeMini}>연소근로자</em>
            </span>
            <ul className={styles.subList}>
              <li className={styles.subLine}>
                <span className={styles.subLabel}>- 친권자(후견인) 성명 :</span>
                <span className={styles.fieldWrap}>
                  <input
                    type="text"
                    className={`${styles.field} ${styles.w_lg}`}
                    value={value.minor.guardian}
                    onChange={(e) => setMinor('guardian', e.target.value)}
                    aria-label="친권자 성명"
                  />
                </span>
              </li>
              <li className={styles.subLine}>
                <span className={styles.subLabel}>- 근로자와의 관계 :</span>
                <span className={styles.fieldWrap}>
                  <input
                    type="text"
                    className={`${styles.field} ${styles.w_md}`}
                    value={value.minor.relation}
                    onChange={(e) => setMinor('relation', e.target.value)}
                    aria-label="근로자와의 관계"
                  />
                </span>
              </li>
              <li className={styles.subLine}>
                <span className={styles.subLabel}>- 연락처 :</span>
                <span className={styles.fieldWrap}>
                  <input
                    type="text"
                    className={`${styles.field} ${styles.w_lg}`}
                    value={value.minor.contact}
                    onChange={(e) => setMinor('contact', e.target.value)}
                    aria-label="친권자 연락처"
                  />
                </span>
              </li>
              <li className={styles.subLine}>
                <span className={styles.subLabel}>- 첨부 :</span>
                <span className={styles.inlineText}>
                  가족관계증명서, 친권자(후견인) 동의서
                </span>
              </li>
            </ul>
          </li>
        )}
      </ol>

      <div className={styles.dateRow}>
        {renderField('contractDate', '계약서 작성일', 'lg')}
      </div>

      <div className={styles.signBlock}>
        {flags.signature && (
          <div className={styles.signNotice}>
            <DotMarker
              flag={flags.signature}
              suggestion={suggestions?.signature}
              onClick={chipClick('signature')}
            />
            <span>서명·날인 누락이 지적됐어요 — 출력 후 양측 서명이 필요해요.</span>
          </div>
        )}
        <div className={styles.signGroup}>
          <span className={styles.signParty}>(사업주)</span>
          <div className={styles.signRows}>
            <div className={styles.signRow}>
              <span className={styles.signLabel}>사업체명 :</span>
              {renderField('employerCompany', '사업체명', 'md')}
              <span className={styles.inlineText}>(전화 :</span>
              {renderField('employerPhone', '사업체 전화', 'sm')}
              <span className={styles.inlineText}>)</span>
            </div>
            <div className={styles.signRow}>
              <span className={styles.signLabel}>주 소 :</span>
              {renderField('employerAddress', '사업체 주소', 'xl')}
            </div>
            <div className={styles.signRow}>
              <span className={styles.signLabel}>대 표 자 :</span>
              {renderField('employerRep', '대표자', 'md')}
              <span className={styles.inlineText}>(서명)</span>
            </div>
          </div>
        </div>
        <div className={styles.signGroup}>
          <span className={styles.signParty}>(근로자)</span>
          <div className={styles.signRows}>
            <div className={styles.signRow}>
              <span className={styles.signLabel}>주 소 :</span>
              {renderField('workerAddress', '근로자 주소', 'xl')}
            </div>
            <div className={styles.signRow}>
              <span className={styles.signLabel}>연 락 처 :</span>
              {renderField('workerContact', '근로자 연락처', 'md')}
            </div>
            <div className={styles.signRow}>
              <span className={styles.signLabel}>성 명 :</span>
              {renderField('workerSignName', '근로자 성명', 'md')}
              <span className={styles.inlineText}>(서명)</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
