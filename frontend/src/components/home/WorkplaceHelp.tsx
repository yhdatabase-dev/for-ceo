/**
 * 사업장 정보 라벨 호버 문구.
 *
 * 백엔드 `cgr/web/review_app/help_text.py` 의 풀이를 React JSX 로 옮긴 것.
 * "~인지" 식 단답형 대신 일반 사장님이 읽고 바로 이해할 수 있는 톤으로 다시 씀.
 */
import type { CSSProperties, ReactNode } from 'react';

const wrap: CSSProperties = {
  display: 'block',
  fontSize: 12.5,
  lineHeight: 1.6,
};

const lead: CSSProperties = {
  fontWeight: 700,
  color: '#fde68a',
  marginBottom: 6,
};

const example: CSSProperties = {
  marginTop: 8,
  padding: '8px 10px',
  background: 'rgba(255,255,255,0.06)',
  borderRadius: 6,
  fontSize: 12,
  lineHeight: 1.55,
};

const tag: CSSProperties = {
  display: 'inline-block',
  fontSize: 10.5,
  fontWeight: 700,
  padding: '2px 6px',
  borderRadius: 4,
  marginRight: 6,
  letterSpacing: 0.2,
};

export const HELP_SHIFT: ReactNode = (
  <span style={wrap}>
    <span style={lead}>📌 교대근로</span>
    직원을 두 개 이상의 조로 나눠 정해진 시간을 번갈아 근무시키는 방식이에요.
    <div style={example}>
      <strong>예시</strong> · 2조 2교대(주간·야간 격일), 3조 3교대(아침·저녁·야간), 4조 3교대 등
    </div>
    <div style={{ marginTop: 8 }}>
      도입한 경우 운영형태(2조 2교대 등)를 <strong>취업규칙에 반드시 적어야</strong> 해요 (근로기준법 제93조 제1호).
    </div>
  </span>
);

export const HELP_CHEM: ReactNode = (
  <span style={wrap}>
    <span style={lead}>📌 화학물질 취급</span>
    사업장에서 화학물질·화학제품을 만들거나 쓰거나 옮기거나 보관하는 모든 경우예요.
    <div style={example}>
      <span style={{ ...tag, background: '#3b3221', color: '#fbbf24' }}>해당</span>
      도료·접착제·세제·시약·연료·인쇄잉크·금속가공유, 살균·세척용 화학제품 사용 등
      <div style={{ marginTop: 6 }}>
        <span style={{ ...tag, background: '#1e293b', color: '#94a3b8' }}>미해당</span>
        일반 사무·교육·서비스업처럼 화학물질을 전혀 쓰지 않는 사업장
      </div>
    </div>
    <div style={{ marginTop: 8 }}>
      취급한다면 <strong>MSDS(물질안전보건자료)</strong> 를 작성·게시하고 직원 교육 의무가 생겨요 (산안법 제114조).
    </div>
  </span>
);

export const HELP_WORKENV: ReactNode = (
  <span style={wrap}>
    <span style={lead}>📌 작업환경측정 대상</span>
    소음·분진·유해화학물질·고열·진동 등에 직원이 노출되는 작업장은
    <strong> 6개월마다 한 번씩 측정</strong>해야 해요.
    <div style={example}>
      <span style={{ ...tag, background: '#3b3221', color: '#fbbf24' }}>대상</span>
      소음 90dB 이상, 분진 발생, 유해화학물질·고열·저온·진동·방사선 노출 작업장
      <div style={{ marginTop: 6 }}>
        <span style={{ ...tag, background: '#1e293b', color: '#94a3b8' }}>비대상</span>
        일반 사무직, 화학물질·소음·분진 노출이 없는 사업장
      </div>
    </div>
    <div style={{ marginTop: 8 }}>
      대상인데 측정을 안 하면 <strong>1천만원 이하 과태료</strong> 가 부과될 수 있어요 (산안법 제125조).
    </div>
  </span>
);

export const HELP_BUSINESS_SIZE: ReactNode = (
  <span style={wrap}>
    <span style={lead}>📌 사업장 규모</span>
    <strong>상시근로자 수</strong>가 5명 이상인지 미만인지로 구분해요.
    근로기준법 일부 조항이 5인 이상 사업장에만 적용되거든요.
    <div style={example}>
      <span style={{ ...tag, background: '#3b3221', color: '#fbbf24' }}>5인 이상</span>
      취업규칙 작성·신고 의무, 연차·연장근로 가산수당, 부당해고 구제, 휴업수당 등 적용
      <div style={{ marginTop: 6 }}>
        <span style={{ ...tag, background: '#1e293b', color: '#94a3b8' }}>5인 미만</span>
        근로기준법 일부만 적용 — 근로계약서 작성, 임금 지급, 주휴수당, 출산휴가 등 핵심 조항은 동일
      </div>
    </div>
    <div style={{ marginTop: 8 }}>
      상시근로자 수에는 <strong>대표·동거가족은 제외</strong>, 일용·기간제·외국인은 포함이에요.
    </div>
  </span>
);

export const HELP_WORKER_TYPES: ReactNode = (
  <span style={wrap}>
    <span style={lead}>📌 근로자 유형 (다중 선택)</span>
    사업장에 <strong>실제로 근무하는 근로자 종류를 모두</strong> 선택해요.
    유형마다 근로계약서·임금명세서에 적어야 할 항목이 달라요.
    <div style={example}>
      <span style={{ ...tag, background: '#1e293b', color: '#94a3b8' }}>정규직</span>
      기간 정함 없는 통상 근로자
      <div style={{ marginTop: 4 }}>
        <span style={{ ...tag, background: '#1e293b', color: '#94a3b8' }}>기간제</span>
        계약기간이 정해진 근로자 (최대 2년)
      </div>
      <div style={{ marginTop: 4 }}>
        <span style={{ ...tag, background: '#1e293b', color: '#94a3b8' }}>단시간</span>
        1주 소정근로시간이 통상 근로자보다 짧은 근로자
      </div>
      <div style={{ marginTop: 4 }}>
        <span style={{ ...tag, background: '#1e293b', color: '#94a3b8' }}>일용직</span>
        1일 단위로 계약하는 근로자
      </div>
      <div style={{ marginTop: 4 }}>
        <span style={{ ...tag, background: '#1e293b', color: '#94a3b8' }}>연소자</span>
        만 18세 미만 (15~17세)
      </div>
      <div style={{ marginTop: 4 }}>
        <span style={{ ...tag, background: '#1e293b', color: '#94a3b8' }}>외국인</span>
        체류자격·숙식 제공 명시 필요
      </div>
    </div>
    <div style={{ marginTop: 8 }}>
      여러 유형이 함께 있으면 <strong>모두 체크</strong>해 주세요. 각 유형에 필요한 항목을 함께 검사해요.
    </div>
  </span>
);

export const HELP_OSHA: ReactNode = (
  <span style={wrap}>
    <span style={lead}>📌 산업안전보건법 적용 업종</span>
    산안법은 거의 모든 업종에 적용되지만, 시행령 별표1 에 따라 일부 업종은 제외돼요.
    대부분의 일반 사업장은 적용 업종에 해당합니다.
    <div style={example}>
      <span style={{ ...tag, background: '#3b3221', color: '#fbbf24' }}>적용 (체크 유지)</span>
      제조업, 건설업, 운수창고업, 농림수산업 일부 등
      <div style={{ marginTop: 6 }}>
        <span style={{ ...tag, background: '#1e293b', color: '#94a3b8' }}>적용제외 (체크 해제)</span>
        사무금융, 교육서비스, 보건업 일부, 사회복지서비스, 예술·스포츠·여가, 협회·단체, 가구내고용 등
      </div>
    </div>
    <div style={{ marginTop: 8 }}>
      적용이라면 안전보건교육·방호조치·보호구·건강진단 등 5개 조항을 추가로 검토해요.
    </div>
  </span>
);
