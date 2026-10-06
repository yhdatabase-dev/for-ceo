-- ============================================================
-- 영세사업장 자율점검 — 통합 마스터 DB (SQLite)
--
-- 세 문서(취업규칙·근로계약서·임금명세서) 공통 정규화.
-- 슬롯·주제·법령·매핑이 한 곳에. 모든 검토 모듈이 이 DB 만 봄.
--
-- 원천 자산 매핑:
--   document_type        ← 코드에서 정적 정의
--   topic                ← obsidian/02_주제_노하우/*.md (31개)
--   topic_section        ← topic_corpus.json (1,769섹션)
--   law / law_article    ← lawExcerpts.ts + ANALYSIS_PROMPT 의 매핑 행
--   check_item           ← atomic_slots_ec.yaml + atomic_slots_v0.yaml
--   check_item_*         ← 위 슬롯의 필드들 분해 + 33-매핑 파싱
-- ============================================================

PRAGMA foreign_keys = ON;

-- ─── 1. 문서 종류 ───
CREATE TABLE IF NOT EXISTS document_type (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  code            TEXT    UNIQUE NOT NULL,        -- "employment_contract"
  name            TEXT    NOT NULL,               -- "근로계약서"
  bucket_count    INTEGER NOT NULL,               -- 3 (EC), 5 (WR)
  created_at      TEXT    DEFAULT (datetime('now'))
);

-- ─── 2. 주제 (노무사회 30+) ───
CREATE TABLE IF NOT EXISTS topic (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  code            TEXT    UNIQUE NOT NULL,        -- "DB_근로시간"
  name            TEXT    NOT NULL,               -- "근로시간"
  description     TEXT,
  source          TEXT,                            -- "노무사회 250825"
  created_at      TEXT    DEFAULT (datetime('now'))
);

-- ─── 3. 주제 섹션 (코퍼스 1,769) ───
CREATE TABLE IF NOT EXISTS topic_section (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  topic_id        INTEGER NOT NULL REFERENCES topic(id) ON DELETE CASCADE,
  section_no      TEXT    NOT NULL,               -- "2.1.1"
  title           TEXT,                            -- 짧은 제목/요약
  body_original   TEXT,                            -- 노무사회 원문 (마크다운)
  body_friendly   TEXT,                            -- LLM paraphrase
  law_refs        TEXT,                            -- JSON 배열 "[\"근로기준법 제50조\"]"
  case_refs       TEXT,                            -- JSON 배열 (판례)
  UNIQUE (topic_id, section_no)
);
CREATE INDEX IF NOT EXISTS idx_topic_section_topic ON topic_section(topic_id);

-- ─── 4. 법령 ───
CREATE TABLE IF NOT EXISTS law (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  code            TEXT    UNIQUE NOT NULL,        -- "근로기준법"
  full_name       TEXT,                            -- "근로기준법"
  external_base   TEXT                             -- "https://www.law.go.kr/법령/근로기준법"
);

-- ─── 5. 법령 조문 (제N조 제N항 제N호) ───
CREATE TABLE IF NOT EXISTS law_article (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  law_id          INTEGER NOT NULL REFERENCES law(id) ON DELETE CASCADE,
  article_no      TEXT    NOT NULL,               -- "제17조"
  paragraph_no    TEXT,                            -- "제1항"
  item_no         TEXT,                            -- "제1호"
  title           TEXT,                            -- "근로조건의 명시"
  body            TEXT,                            -- 본문 발췌
  penalty         TEXT,                            -- "500만원 이하 벌금"
  external_url    TEXT,                            -- law.go.kr 직접 링크
  UNIQUE (law_id, article_no, paragraph_no, item_no)
);
CREATE INDEX IF NOT EXISTS idx_law_article_law ON law_article(law_id);

-- ─── 6. 검사 항목 (슬롯) ───
CREATE TABLE IF NOT EXISTS check_item (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  document_type_id INTEGER NOT NULL REFERENCES document_type(id) ON DELETE CASCADE,
  code            TEXT    NOT NULL,               -- "SLOT_EC_01_사용자_정보"
  name            TEXT    NOT NULL,               -- "사용자 정보"
  required_content TEXT,                          -- "상호, 사업자등록번호, 대표자, …"
  purpose         TEXT,                            -- 기재 필요 이유
  category        TEXT,                            -- "공통" / "5인이상" / "기간제" / "단시간" / "일용직" / "연소자" / "외국인"
  comparator      TEXT    DEFAULT 'presence',     -- presence / numeric_gte / …
  display_order   INTEGER DEFAULT 0,
  UNIQUE (document_type_id, code)
);
CREATE INDEX IF NOT EXISTS idx_check_item_doc ON check_item(document_type_id);

-- ─── 7. 적용 조건 ───
CREATE TABLE IF NOT EXISTS check_item_applicability (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  check_item_id   INTEGER NOT NULL REFERENCES check_item(id) ON DELETE CASCADE,
  business_size   TEXT,                            -- "5+", "5-", "any"
  worker_types    TEXT,                            -- JSON 배열 "[\"정규직\",\"기간제\"]"
  written_duty    TEXT                             -- "필수_서면교부", "필수_명시", "기간제_필수", "단시간_필수"
);
CREATE INDEX IF NOT EXISTS idx_applic_check ON check_item_applicability(check_item_id);

-- ─── 8. 항목 위험도 ───
CREATE TABLE IF NOT EXISTS check_item_risk (
  check_item_id      INTEGER PRIMARY KEY REFERENCES check_item(id) ON DELETE CASCADE,
  missing_severity   TEXT,                         -- 미기재 시 — HIGH/MEDIUM/LOW
  violation_severity TEXT,                         -- 기재 부적절 시
  fix_example        TEXT
);

-- ─── 9. 항목 ↔ 주제 매핑 (33-매핑 단일 소스) ───
CREATE TABLE IF NOT EXISTS check_item_topic (
  check_item_id     INTEGER NOT NULL REFERENCES check_item(id) ON DELETE CASCADE,
  topic_section_id  INTEGER NOT NULL REFERENCES topic_section(id) ON DELETE CASCADE,
  weight            REAL    DEFAULT 1.0,
  PRIMARY KEY (check_item_id, topic_section_id)
);

-- ─── 10. 항목 ↔ 법령 조문 매핑 ───
CREATE TABLE IF NOT EXISTS check_item_law (
  check_item_id   INTEGER NOT NULL REFERENCES check_item(id) ON DELETE CASCADE,
  law_article_id  INTEGER NOT NULL REFERENCES law_article(id) ON DELETE CASCADE,
  PRIMARY KEY (check_item_id, law_article_id)
);

-- ─── 11. 검토 사례 (audit case) ───
CREATE TABLE IF NOT EXISTS audit_case (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  case_uid        TEXT    UNIQUE NOT NULL,        -- 외부에 노출하는 case_id
  document_type_id INTEGER REFERENCES document_type(id),
  filename        TEXT,
  business_size   TEXT,
  worker_types    TEXT,                            -- JSON 배열
  overall_status  TEXT,                            -- 위험/보완필요/적정
  risk_level      TEXT,                            -- 상/중/하
  elapsed_sec     REAL,
  created_at      TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_case_uid ON audit_case(case_uid);

-- ─── 12. 검토 결과 (항목별) ───
CREATE TABLE IF NOT EXISTS audit_finding (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id         INTEGER NOT NULL REFERENCES audit_case(id) ON DELETE CASCADE,
  check_item_id   INTEGER REFERENCES check_item(id),
  bucket          TEXT,                            -- 적절/보완필요/부적절 (또는 5-Bucket)
  found_text      TEXT,                            -- 본문에서 추출된 표현
  reason          TEXT,                            -- 판단이유 (meta 태그 정리 후)
  recommendation  TEXT,                            -- 개선권고
  user_override   TEXT,                            -- 사용자가 SuggestBlock 으로 직접 작성
  applied_at      TEXT                             -- 사용자가 '문서에 반영' 한 시각
);
CREATE INDEX IF NOT EXISTS idx_audit_finding_case ON audit_finding(case_id);
CREATE INDEX IF NOT EXISTS idx_audit_finding_item ON audit_finding(check_item_id);

-- ─── 편의 view: 한 항목의 "풀 컨텍스트" 한 번에 ───
CREATE VIEW IF NOT EXISTS v_check_item_full AS
SELECT
  ci.id            AS check_item_id,
  dt.code          AS document_type,
  ci.code          AS slot_code,
  ci.name          AS item_name,
  ci.category      AS category,
  ci.required_content,
  ci.purpose,
  cir.missing_severity,
  cir.violation_severity,
  cir.fix_example,
  (SELECT json_group_array(
      json_object(
        'topic',   t.name,
        'section', ts.section_no,
        'title',   ts.title,
        'body',    coalesce(ts.body_friendly, ts.body_original)
      ))
    FROM check_item_topic cit
    JOIN topic_section ts ON ts.id = cit.topic_section_id
    JOIN topic t          ON t.id = ts.topic_id
    WHERE cit.check_item_id = ci.id) AS topic_refs_json,
  (SELECT json_group_array(
      json_object(
        'law',     l.code,
        'article', la.article_no || coalesce(' ' || la.paragraph_no, '') || coalesce(' ' || la.item_no, ''),
        'penalty', la.penalty,
        'url',     la.external_url
      ))
    FROM check_item_law cil
    JOIN law_article la ON la.id = cil.law_article_id
    JOIN law l          ON l.id = la.law_id
    WHERE cil.check_item_id = ci.id) AS law_refs_json
FROM check_item ci
JOIN document_type dt ON dt.id = ci.document_type_id
LEFT JOIN check_item_risk cir ON cir.check_item_id = ci.id;

-- ============================================================
-- Phase 6 추가 — 임금명세서 계산형 위반 룰 토대
-- 설계: 임금명세서_DB모델링_설계.md (사용자 제공)
--
-- 4개 마스터 reference 테이블 — 트랜잭션 흐름 없이 즉시 가치 발생.
-- 트랜잭션 (payslip_*, inspection_run 등) 은 후속 Phase 에서 추가.
-- ============================================================

-- ─── 13. 최저임금 마스터 (연도별, 시점 관리) ───
CREATE TABLE IF NOT EXISTS minimum_wage_master (
  year                INTEGER PRIMARY KEY,             -- 적용 연도
  hourly_amount       INTEGER NOT NULL,                -- 시간급 (원)
  monthly_amount_209h INTEGER NOT NULL,                -- 월 환산 (주 40h × 4.345주 ≈ 209h)
  effective_from      TEXT    NOT NULL,                -- YYYY-MM-DD
  effective_to        TEXT,                            -- 다음해 효력 직전. 미래 연도는 NULL.
  source              TEXT,                            -- "최저임금위원회 고시 제2024-1호" 등
  notice_url          TEXT
);

-- ─── 14. 임금항목 카탈로그 (통상임금·평균임금 분류) ───
CREATE TABLE IF NOT EXISTS wage_item_catalog (
  item_code           TEXT    PRIMARY KEY,             -- BASIC, OT, NIGHT, HOLIDAY, MEAL, BONUS_FIXED ...
  item_name           TEXT    NOT NULL,                -- "기본급", "연장근로수당"
  item_category       TEXT    NOT NULL,                -- 기본급/법정수당/약정수당/실비변상/상여
  line_type           TEXT    NOT NULL DEFAULT 'PAYMENT', -- PAYMENT/DEDUCTION
  is_ordinary_wage    INTEGER NOT NULL DEFAULT 0,      -- 통상임금 포함 여부 (기본값, LLM 으로 override 가능)
  is_average_wage     INTEGER NOT NULL DEFAULT 0,      -- 평균임금 포함 여부
  is_taxable          INTEGER NOT NULL DEFAULT 1,
  legal_basis         TEXT,                            -- "근로기준법 제56조" 등
  description         TEXT,
  aliases             TEXT                             -- JSON 배열 — 사업장별 이형 명칭 매핑
);
CREATE INDEX IF NOT EXISTS idx_wage_item_category ON wage_item_catalog(item_category);

-- ─── 15. 위반유형 카탈로그 (V001 ~) ───
CREATE TABLE IF NOT EXISTS violation_type (
  violation_code      TEXT    PRIMARY KEY,             -- V001: 필수기재누락, V002: 최저임금미달 ...
  violation_name      TEXT    NOT NULL,
  severity            TEXT    NOT NULL,                -- HIGH/MID/LOW
  judgment_kind       TEXT    NOT NULL DEFAULT 'rule', -- rule(계산형) / llm(판단형)
  legal_article       TEXT,                            -- "근로기준법 제48조 제2항"
  law_article_id      INTEGER REFERENCES law_article(id),
  description         TEXT,
  penalty             TEXT
);
CREATE INDEX IF NOT EXISTS idx_violation_severity ON violation_type(severity);

-- ─── 16. 권고안 매핑 (위반 → 권고 텍스트 템플릿) ───
CREATE TABLE IF NOT EXISTS recommendation_mapping (
  recommendation_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  violation_code      TEXT    NOT NULL REFERENCES violation_type(violation_code) ON DELETE CASCADE,
  condition_expr      TEXT,                            -- 적용 조건 (예: "business_size='5-'")
  recommendation_text TEXT    NOT NULL,                -- 사용자에게 보여줄 권고 본문 (변수 치환용 {placeholder} 가능)
  template_fix        TEXT,                            -- 자동 수정 템플릿
  priority            INTEGER NOT NULL DEFAULT 100     -- 같은 위반의 여러 권고 중 우선순위 (낮을수록 우선)
);
CREATE INDEX IF NOT EXISTS idx_recommendation_violation ON recommendation_mapping(violation_code);

-- ─── 편의 view: 최저임금 — 항상 현재 연도 행 (CURRENT_DATE 기준) ───
CREATE VIEW IF NOT EXISTS v_minimum_wage_current AS
SELECT *
FROM minimum_wage_master
WHERE effective_from <= date('now')
  AND (effective_to IS NULL OR effective_to >= date('now'))
ORDER BY year DESC
LIMIT 1;

-- ============================================================
-- Phase 7 — 임금명세서 트랜잭션 + 룰엔진 도메인
-- 설계: 임금명세서_DB모델링_설계.md
-- ============================================================

-- ─── 17. 사업장 ───
CREATE TABLE IF NOT EXISTS workplace (
  id                      INTEGER PRIMARY KEY AUTOINCREMENT,
  business_no_hashed      TEXT    UNIQUE,             -- 사업자번호 SHA-256 hex
  workplace_name          TEXT,
  industry_code           TEXT,                        -- KSIC 코드 (5인미만 적용제외 판단)
  employee_count          INTEGER,                     -- 상시 근로자 수
  weekly_work_hours_std   REAL    DEFAULT 40.0,        -- 표준 주 소정근로시간
  pay_cycle_type          TEXT    DEFAULT 'monthly',   -- monthly / weekly / hourly / daily
  created_at              TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_workplace_bizno ON workplace(business_no_hashed);

-- ─── 18. 근로자 ───
CREATE TABLE IF NOT EXISTS employee (
  id                      INTEGER PRIMARY KEY AUTOINCREMENT,
  workplace_id            INTEGER NOT NULL REFERENCES workplace(id) ON DELETE CASCADE,
  emp_no_hashed           TEXT,                        -- 사원번호 해시
  name_masked             TEXT,                        -- "홍○○" 마스킹
  hire_date               TEXT,                        -- YYYY-MM-DD
  contract_type           TEXT    DEFAULT '정규직',      -- 정규직/기간제/단시간/일용직
  job_position            TEXT,
  hourly_wage_agreed      INTEGER,                     -- 약정 시급
  monthly_wage_agreed     INTEGER,                     -- 약정 월급
  weekly_contract_hours   REAL,                        -- 주 소정근로시간
  created_at              TEXT    DEFAULT (datetime('now')),
  UNIQUE (workplace_id, emp_no_hashed)
);
CREATE INDEX IF NOT EXISTS idx_employee_workplace ON employee(workplace_id);

-- ─── 19. 임금명세서 문서 (업로드 단위) ───
CREATE TABLE IF NOT EXISTS payslip_document (
  id                      INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_uid                 TEXT    UNIQUE NOT NULL,    -- 외부 노출 식별자
  workplace_id            INTEGER REFERENCES workplace(id),
  employee_id             INTEGER REFERENCES employee(id),
  pay_period_year         INTEGER,                     -- 임금 산정 대상기간
  pay_period_month        INTEGER,
  pay_period_start        TEXT,
  pay_period_end          TEXT,
  payment_date            TEXT,
  original_file_path      TEXT,                        -- 업로드 원본 (이미지/PDF)
  ocr_status              TEXT    DEFAULT 'PENDING',   -- PENDING/DONE/FAILED
  ocr_confidence_avg      REAL,
  uploaded_at             TEXT    DEFAULT (datetime('now')),
  uploaded_by             TEXT
);
CREATE INDEX IF NOT EXISTS idx_payslip_doc_uid ON payslip_document(doc_uid);
CREATE INDEX IF NOT EXISTS idx_payslip_doc_workplace ON payslip_document(workplace_id);

-- ─── 20. OCR 추출 결과 (raw) ───
CREATE TABLE IF NOT EXISTS payslip_ocr_raw (
  id                      INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id             INTEGER NOT NULL REFERENCES payslip_document(id) ON DELETE CASCADE,
  field_name              TEXT,                        -- '기본급', '연장근로수당' 등 라벨
  raw_text                TEXT,                        -- OCR 원문
  bbox_coords             TEXT,                        -- JSON: {x,y,w,h}
  confidence_score        REAL
);
CREATE INDEX IF NOT EXISTS idx_ocr_raw_doc ON payslip_ocr_raw(document_id);

-- ─── 21. 임금명세서 구조화 데이터 (확정값) ───
CREATE TABLE IF NOT EXISTS payslip (
  id                      INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id             INTEGER UNIQUE NOT NULL REFERENCES payslip_document(id) ON DELETE CASCADE,
  -- 필수기재 (시행령 제27조의2)
  worker_name             TEXT,                        -- ① 마스킹된 성명
  worker_birth_or_emp_no  TEXT,                        -- ② 생년월일/사번 (마스킹)
  total_work_days         REAL,                        -- ③-1 근로일수
  total_work_hours        REAL,                        -- ③-2 총 근로시간
  overtime_hours          REAL,                        -- ③-3 연장근로시간
  night_hours             REAL,                        -- ③-4 야간근로시간
  holiday_hours           REAL,                        -- ③-5 휴일근로시간
  payment_date            TEXT,                        -- ⑤ 임금지급일
  total_gross             INTEGER,                     -- ⑥ 임금총액 (지급)
  total_deduction         INTEGER,                     -- 공제총액
  total_net               INTEGER,                     -- 실수령액
  is_user_confirmed       INTEGER DEFAULT 0,           -- 사용자 검증 완료
  confirmed_at            TEXT
);

-- ─── 22. 임금명세서 명세 항목 (지급/공제 1:N) ───
CREATE TABLE IF NOT EXISTS payslip_line (
  id                      INTEGER PRIMARY KEY AUTOINCREMENT,
  payslip_id              INTEGER NOT NULL REFERENCES payslip(id) ON DELETE CASCADE,
  line_type               TEXT    NOT NULL,            -- PAYMENT / DEDUCTION
  item_code               TEXT    REFERENCES wage_item_catalog(item_code),
  item_name_original      TEXT,                        -- 명세서 원문 항목명 (예: "중식보조비")
  calculation_basis       TEXT,                        -- ④ 계산방법 (예: "시급×시간×1.5")
  unit_amount             INTEGER,                     -- 단가
  quantity                REAL,                        -- 수량
  amount                  INTEGER NOT NULL DEFAULT 0,  -- 금액
  is_ordinary_wage_final  INTEGER,                     -- LLM 판단 반영 최종 (NULL=catalog 기본값 사용)
  llm_judgment_id         INTEGER,                     -- 비계산적 판단 트레이스 FK (deferred)
  display_order           INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_payslip_line_slip ON payslip_line(payslip_id);
CREATE INDEX IF NOT EXISTS idx_payslip_line_type ON payslip_line(line_type);

-- ─── 23. LLM 비계산적 판단 이력 ───
CREATE TABLE IF NOT EXISTS llm_judgment (
  id                      INTEGER PRIMARY KEY AUTOINCREMENT,
  payslip_line_id         INTEGER REFERENCES payslip_line(id) ON DELETE CASCADE,
  question_type           TEXT,                        -- ORDINARY_WAGE / AVERAGE_WAGE / ...
  input_context           TEXT,                        -- 비식별화된 프롬프트 (JSON)
  llm_model_version       TEXT,
  llm_response_raw        TEXT,
  judgment_result         TEXT,                        -- TRUE / FALSE / UNCERTAIN
  user_override           INTEGER DEFAULT 0,           -- 사용자가 뒤집었는지
  judged_at               TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_llm_judgment_line ON llm_judgment(payslip_line_id);

-- ─── 24. 점검 실행 (룰셋 실행 단위) ───
CREATE TABLE IF NOT EXISTS inspection_run (
  id                      INTEGER PRIMARY KEY AUTOINCREMENT,
  run_uid                 TEXT    UNIQUE NOT NULL,
  payslip_id              INTEGER NOT NULL REFERENCES payslip(id) ON DELETE CASCADE,
  ruleset_version         TEXT    NOT NULL,            -- "v1.0" 등 — 시점 데이터
  minimum_wage_year       INTEGER NOT NULL,            -- 어느 연도 최저임금 기준
  total_violations        INTEGER DEFAULT 0,
  overall_status          TEXT,                        -- OK / WARN / VIOLATION
  executed_at             TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_inspection_run_payslip ON inspection_run(payslip_id);

-- ─── 25. 위반 탐지 결과 (룰 단위) ───
CREATE TABLE IF NOT EXISTS violation_finding (
  id                      INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id                  INTEGER NOT NULL REFERENCES inspection_run(id) ON DELETE CASCADE,
  violation_code          TEXT    NOT NULL REFERENCES violation_type(violation_code),
  payslip_line_id         INTEGER REFERENCES payslip_line(id) ON DELETE SET NULL,
  detected_value          TEXT,                        -- 탐지된 값 (예: "9500")
  expected_value          TEXT,                        -- 기준값 (예: "10030")
  difference_amount       INTEGER,                     -- 차액 (원)
  detail_description      TEXT,
  status                  TEXT    DEFAULT 'OPEN'       -- OPEN / FIXED / IGNORED
);
CREATE INDEX IF NOT EXISTS idx_violation_finding_run ON violation_finding(run_id);
CREATE INDEX IF NOT EXISTS idx_violation_finding_code ON violation_finding(violation_code);

-- ─── 26. 권고안 (사용자 제시용) ───
CREATE TABLE IF NOT EXISTS recommendation (
  id                      INTEGER PRIMARY KEY AUTOINCREMENT,
  finding_id              INTEGER NOT NULL REFERENCES violation_finding(id) ON DELETE CASCADE,
  recommendation_template_id INTEGER REFERENCES recommendation_mapping(recommendation_id),
  rendered_text           TEXT    NOT NULL,            -- 사용자별 변수 치환된 최종 텍스트
  suggested_amount        INTEGER,
  is_accepted             INTEGER DEFAULT 0,
  accepted_at             TEXT
);
CREATE INDEX IF NOT EXISTS idx_recommendation_finding ON recommendation(finding_id);

-- ─── 27. 수정 이력 ───
CREATE TABLE IF NOT EXISTS correction_log (
  id                      INTEGER PRIMARY KEY AUTOINCREMENT,
  payslip_line_id         INTEGER REFERENCES payslip_line(id) ON DELETE SET NULL,
  field_name              TEXT,
  before_value            TEXT,
  after_value             TEXT,
  correction_reason       TEXT,                        -- USER_EDIT / OCR_FIX / RECOMMENDATION_ACCEPT
  corrected_by            TEXT,
  corrected_at            TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_correction_log_line ON correction_log(payslip_line_id);

-- ============================================================
-- Phase 16 — 노무 가이드 DB (영세사업주 꿀팁 카탈로그)
--
-- 원천: "영세사업주를 위한 꿀팁.xlsx" 15 시트.
-- 자율점검 본질에 맞춰 **사업주 관점** 항목만 노출 — 진정·고발·구제 신청 류는
-- excluded_from_service=1 로 표시 → API 응답 기본 제외.
-- ============================================================

CREATE TABLE IF NOT EXISTS guide_item (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  code            TEXT    UNIQUE NOT NULL,
  audience        TEXT    NOT NULL,            -- worker / employer / both
  category        TEXT,
  title           TEXT    NOT NULL,
  worker_reason   TEXT,
  employer_reason TEXT,
  key_points      TEXT,
  related_laws    TEXT,
  priority        TEXT,
  applies_under_5 TEXT,
  note            TEXT,
  excluded_from_service INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_guide_item_audience ON guide_item(audience);
CREATE INDEX IF NOT EXISTS idx_guide_item_category ON guide_item(category);

CREATE TABLE IF NOT EXISTS obligation_timeline (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  code            TEXT    UNIQUE NOT NULL,
  stage           TEXT    NOT NULL,
  duty            TEXT    NOT NULL,
  description     TEXT,
  deadline        TEXT,
  legal_basis     TEXT,
  priority        TEXT,
  penalty         TEXT,
  excluded_from_service INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_obligation_stage ON obligation_timeline(stage);

CREATE TABLE IF NOT EXISTS wage_calc_formula (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  code            TEXT    UNIQUE NOT NULL,
  category        TEXT,
  calc_name       TEXT    NOT NULL,
  formula         TEXT    NOT NULL,
  conditions      TEXT,
  limits          TEXT,
  legal_basis     TEXT,
  note            TEXT,
  related_violation_code TEXT REFERENCES violation_type(violation_code)
);

CREATE TABLE IF NOT EXISTS guide_glossary (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  code            TEXT    UNIQUE NOT NULL,
  term            TEXT    UNIQUE NOT NULL,
  short_def       TEXT,
  full_def        TEXT,
  confusable_with TEXT,
  legal_basis     TEXT
);

CREATE TABLE IF NOT EXISTS form_template (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  code            TEXT    UNIQUE NOT NULL,
  category        TEXT,
  form_name       TEXT    NOT NULL,
  purpose         TEXT,
  submitter       TEXT,
  submit_to       TEXT,
  submit_method   TEXT,
  deadline        TEXT,
  legal_basis     TEXT,
  download_url    TEXT,                -- 폴백용 외부(고용노동부) URL — local_filename 없을 때 redirect
  local_filename  TEXT,                -- backend/data/forms/<filename> — 우리 서버에서 직접 다운로드 (Phase 18)
  local_mime      TEXT,                -- 'application/x-hwp', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/pdf' 등
  local_size      INTEGER,             -- bytes
  fetched_at      TEXT,                -- crawl 으로 받은 시각 ISO8601
  audience        TEXT    DEFAULT 'employer',
  excluded_from_service INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_form_template_audience ON form_template(audience);

CREATE TABLE IF NOT EXISTS gov_org (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  code            TEXT    UNIQUE NOT NULL,
  org_class       TEXT,
  org_name        TEXT    NOT NULL,
  duties          TEXT,
  common_cases    TEXT,
  phone           TEXT,
  online_channel  TEXT,
  jurisdiction    TEXT,
  note            TEXT,
  audience        TEXT    DEFAULT 'employer',
  excluded_from_service INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS audit_guide (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  code            TEXT    UNIQUE NOT NULL,
  kind            TEXT    NOT NULL,            -- 'type' / 'procedure'
  name            TEXT    NOT NULL,
  step_no         INTEGER,
  timing          TEXT,
  description     TEXT,
  period_covered  TEXT,
  legal_basis     TEXT
);

CREATE TABLE IF NOT EXISTS required_document (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  code            TEXT    UNIQUE NOT NULL,
  classification  TEXT,
  doc_name        TEXT    NOT NULL,
  description     TEXT,
  prep_time       TEXT,
  retention_period TEXT,
  legal_basis     TEXT,
  penalty         TEXT
);

CREATE TABLE IF NOT EXISTS recruit_compliance (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  code            TEXT    UNIQUE NOT NULL,
  stage           TEXT    NOT NULL,
  duty            TEXT    NOT NULL,
  description     TEXT,
  violation_examples TEXT,
  penalty         TEXT,
  applies_to      TEXT,
  legal_basis     TEXT,
  checkpoint      TEXT
);

CREATE TABLE IF NOT EXISTS size_threshold_duty (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  code            TEXT    UNIQUE NOT NULL,
  min_size        TEXT    NOT NULL,
  duty            TEXT    NOT NULL,
  description     TEXT,
  related_docs    TEXT,
  legal_basis     TEXT,
  note            TEXT
);
CREATE INDEX IF NOT EXISTS idx_size_threshold_size ON size_threshold_duty(min_size);

CREATE TABLE IF NOT EXISTS employment_lifecycle (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  code            TEXT    UNIQUE NOT NULL,
  phase           TEXT    NOT NULL,
  sub_topic       TEXT,
  requirement     TEXT,
  related_docs    TEXT,
  timing          TEXT,
  legal_basis     TEXT,
  note            TEXT
);

-- 편의 view: 사업주 노출용 가이드 (excluded·worker-only 제외)
CREATE VIEW IF NOT EXISTS v_guide_for_employer AS
SELECT 'guide_item' AS source, code, title AS name, category, related_laws AS legal_basis
  FROM guide_item   WHERE excluded_from_service = 0 AND audience IN ('employer','both')
UNION ALL
SELECT 'obligation_timeline', code, duty, stage, legal_basis
  FROM obligation_timeline WHERE excluded_from_service = 0
UNION ALL
SELECT 'form_template', code, form_name, category, legal_basis
  FROM form_template WHERE excluded_from_service = 0 AND audience IN ('employer','both')
UNION ALL
SELECT 'gov_org', code, org_name, org_class, NULL
  FROM gov_org WHERE excluded_from_service = 0;

-- ─── 편의 view: 한 검토(run) 의 풀 컨텍스트 ───
CREATE VIEW IF NOT EXISTS v_inspection_full AS
SELECT
  ir.id                AS run_id,
  ir.run_uid,
  ir.ruleset_version,
  ir.minimum_wage_year,
  ir.overall_status,
  ir.total_violations,
  ir.executed_at,
  p.id                 AS payslip_id,
  p.worker_name,
  p.total_gross,
  p.total_net,
  p.payment_date,
  pd.doc_uid           AS document_uid,
  w.workplace_name,
  e.name_masked        AS employee_name,
  (SELECT json_group_array(
      json_object(
        'finding_id',   vf.id,
        'violation',    vf.violation_code,
        'name',         vt.violation_name,
        'severity',     vt.severity,
        'detected',     vf.detected_value,
        'expected',     vf.expected_value,
        'diff',         vf.difference_amount,
        'detail',       vf.detail_description,
        'status',       vf.status
      ))
    FROM violation_finding vf
    JOIN violation_type vt ON vt.violation_code = vf.violation_code
    WHERE vf.run_id = ir.id) AS findings_json
FROM inspection_run ir
JOIN payslip p             ON p.id = ir.payslip_id
JOIN payslip_document pd   ON pd.id = p.document_id
LEFT JOIN workplace w      ON w.id = pd.workplace_id
LEFT JOIN employee e       ON e.id = pd.employee_id;
