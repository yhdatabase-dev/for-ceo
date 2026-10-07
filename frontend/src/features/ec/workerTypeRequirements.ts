/**
 * 근로자 유형별 근로계약서 필수 기재사항.
 *
 * 기존 `1. 근로계약서/기존/server/prompts.json` 의 analysis 프롬프트 33-매핑 테이블을
 * UI 안내용으로 옮겨놓은 것. 결과 페이지의 "유형별 필수 기재" 박스에서 참조.
 */

export interface RequirementGroup {
  /** 그룹 키 — 사용자 컨텍스트(business_size, worker_types) 와 매칭. */
  key:
    | '공통'
    | '5인이상'
    | '기간제'
    | '단시간'
    | '일용직'
    | '연소자'
    | '외국인'
    | '외국인-농축어업';
  label: string;
  description: string;
  /** 짧은 항목명 — 칩으로 표시. */
  items: string[];
}

export const REQUIREMENT_GROUPS: RequirementGroup[] = [
  {
    key: '공통',
    label: '공통 필수',
    description: '모든 근로자에게 공통으로 적용되는 필수 기재사항입니다.',
    items: [
      '사용자 정보',
      '근로자 정보',
      '근로개시일',
      '근무 장소',
      '업무 내용',
      '소정근로시간',
      '휴게시간',
      '근무일·휴일',
      '임금 (총액·구성항목·계산방법·지급방법·지급시기)',
      '퇴직금',
      '사회보험 (4대보험 가입 여부)',
      '수습기간',
      '근로계약서 교부',
      '계약서 작성일',
      '당사자 서명·날인',
    ],
  },
  {
    key: '5인이상',
    label: '5인 이상 사업장',
    description: '상시근로자 5인 이상이면 추가로 필요합니다.',
    items: ['연차유급휴가 (15일)', '연장·야간·휴일근로 (가산 50% 이상)'],
  },
  {
    key: '기간제',
    label: '기간제 근로자',
    description: '계약기간이 정해진 근로자에게 추가됩니다.',
    items: ['근로계약기간 (시작일~종료일, 최대 2년)'],
  },
  {
    key: '단시간',
    label: '단시간(알바) 근로자',
    description: '주 소정근로시간이 통상 근로자보다 짧은 근로자에게 추가됩니다.',
    items: ['근로계약기간', '근로일 및 근로일별 근로시간'],
  },
  {
    key: '일용직',
    label: '일용직 근로자',
    description: '1일 단위로 고용하는 근로자에게 추가됩니다.',
    items: ['근로계약기간 (1일 단위)', '일당'],
  },
  {
    key: '연소자',
    label: '연소자 (만 18세 미만)',
    description: '15~17세 근로자 사용 시 추가 의무가 있습니다.',
    items: [
      '연령증명서 (가족관계증명서 등)',
      '친권자 동의서',
      '근로시간 제한 (1일 7시간, 주 35시간)',
      '야간·휴일근로 제한 (원칙 금지)',
    ],
  },
  {
    key: '외국인',
    label: '외국인 근로자',
    description: '비자로 입국한 외국인 근로자에게 추가됩니다.',
    items: ['체류자격 (비자 종류·체류기간)', '숙식제공 여부 (제공 시 비용공제 명시)'],
  },
  {
    key: '외국인-농축어업',
    label: '외국인 (농축어업)',
    description: '농림수산업 외국인 근로자는 근로시간 특례가 적용됩니다.',
    items: ['근로시간/휴게/휴일 특례 적용 (근로기준법 제63조)'],
  },
];

/**
 * 사용자의 사업장 컨텍스트(규모·근로자 유형) 에 해당하는 그룹만 골라낸다.
 * - 공통은 항상 포함
 * - business_size === '5+' 면 '5인이상' 포함
 * - worker_types 에 들어있는 유형만 포함 (정규직은 별도 그룹이 없으므로 공통만)
 */
export function filterApplicableGroups(
  businessSize: string,
  workerTypes: string[],
): RequirementGroup[] {
  const out: RequirementGroup[] = [REQUIREMENT_GROUPS[0]]; // 공통은 항상 첫 줄에
  if (businessSize === '5+' || businessSize === '5인이상') {
    const g = REQUIREMENT_GROUPS.find((x) => x.key === '5인이상');
    if (g) out.push(g);
  }
  for (const wt of workerTypes) {
    const norm = wt.trim();
    if (!norm || norm === '정규직') continue;
    // 외국인-농축어업 변형 매칭
    if (norm === '외국인(농축어업)' || norm === '외국인-농축어업') {
      const g = REQUIREMENT_GROUPS.find((x) => x.key === '외국인-농축어업');
      if (g) out.push(g);
      continue;
    }
    const g = REQUIREMENT_GROUPS.find((x) => x.key === (norm as RequirementGroup['key']));
    if (g) out.push(g);
  }
  return out;
}
