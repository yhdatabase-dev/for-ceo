'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { useRouter } from 'next/navigation';

import Button from '@/components/ui/Button';
import Icon from '@/components/ui/Icon';

import SiteHeader from '@/components/layout/SiteHeader';
import Hero from '@/components/home/Hero';
import SectionHeading from '@/components/home/SectionHeading';
import DocTypePicker from '@/components/home/DocTypePicker';
import FileDropzone from '@/components/home/FileDropzone';
import MobileUploadE from '@/components/home/MobileUploadE';
import WorkplaceForm, {
  DEFAULT_WORKPLACE,
  toWorkplaceContext,
  type WorkplaceFormState,
} from '@/components/home/WorkplaceForm';

import { postEcClassify, postEcExtract, postEcStructure } from '@/lib/api/ec';
import { postWrClassify } from '@/lib/api/review';
import { extractAllText, fileToDisplayDataUrl } from '@/lib/uploadPrep';
import { ApiCallError } from '@/lib/api/client';
import {
  makeTempCaseId,
  setCaseError,
  startCase,
  updateEc,
  updateWr,
} from '@/lib/reviewStore';

import type { DocumentType } from '@/types/review';

import styles from './page.module.css';

/* ─────────────────────────────────────────────
 *  모바일(≤720px) 2단계 플로 — 시안 s-home / s-upload 카드 데이터.
 *  4종 모두 활성 (시안의 '예정' 배지는 이 앱에선 미사용).
 * ───────────────────────────────────────────── */

interface MobileDocCard {
  id: DocumentType;
  title: string;
  sub: string;
  icon: ReactNode;
  /** true 면 화면에서 숨김 (코드·라우트는 유지 — 나중에 false 로 되살림). */
  hidden?: boolean;
}

const MOBILE_DOC_CARDS: MobileDocCard[] = [
  {
    id: 'employment-contract',
    title: '근로계약서',
    sub: '개별 근로자 계약서',
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
        <rect x="4" y="3" width="16" height="18" rx="2" />
        <path d="M8 8h8M8 12h6" />
        <path d="M14 17l2 2 3-3" />
      </svg>
    ),
  },
  {
    id: 'work-rules',
    title: '취업규칙',
    sub: '사업장 단위 규정',
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
        <rect x="4" y="3" width="16" height="18" rx="2" />
        <path d="M8 8h8M8 12h8M8 16h5" />
      </svg>
    ),
  },
];

/**
 * 홈 — 문서 종류 + 업로드 + 사업장 정보.
 *
 * 시안 `screens-home.jsx` 의 흐름을 그대로 옮긴 클라이언트 페이지.
 * 검토 시작은 다음 단계에서 백엔드 `POST /api/review` 로 교체.
 * 모바일(≤720px)에선 시안 `근로계약서 검토 앱.html` 의 2단계 플로
 * (select → upload)로 분기 — 상태·제출 로직은 데스크톱과 공유.
 */
export default function HomePage() {
  const router = useRouter();

  // 기본 진입은 근로계약서 — 풀 이식의 메인 트랙.
  const [docType, setDocType] = useState<DocumentType>('employment-contract');
  const [files, setFiles] = useState<File[]>([]);
  const [workplace, setWorkplace] = useState<WorkplaceFormState>(DEFAULT_WORKPLACE);
  const [submitting, setSubmitting] = useState(false);

  // 모바일(≤720px) 분기 — 시안 2단계 플로(select → upload).
  // SSR 첫 페인트는 데스크톱 → 마운트 후 matchMedia 로 동기화.
  const [isMobile, setIsMobile] = useState(false);
  const [mobileStep, setMobileStep] = useState<'select' | 'upload'>('select');
  // 모바일 — 업로드 후 '사업장 규모' 확인 팝업(바텀시트). 확인 시 검토 시작.
  const [sizeSheetOpen, setSizeSheetOpen] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 720px)');
    const sync = () => setIsMobile(mq.matches);
    sync();
    mq.addEventListener('change', sync);
    return () => mq.removeEventListener('change', sync);
  }, []);

  // work-rules / employment-contract 허용.
  const docReady = docType === 'work-rules' || docType === 'employment-contract';
  const canSubmit = files.length > 0 && docReady && !submitting;

  const startReview = async () => {
    if (files.length === 0 || !docReady) return;
    setSubmitting(true);

    const caseId = makeTempCaseId();

    // 결과 페이지 좌측 미리보기용 — 첫 파일이 이미지면 blob URL 만들어 store 에 동봉.
    // docx/hwp/pdf 는 미리보기 없이 카드만.
    const first = files[0];
    const isImage = first.type.startsWith('image/');
    // 사진은 다운스케일 data: URL 로 — 새로고침·검토 이력 복원 후에도 좌측 원본
    // 미리보기가 살아있게(저장소에 직렬화 가능). 변환 실패 시 blob URL 폴백.
    const originalUrl = isImage
      ? (await fileToDisplayDataUrl(first)) ?? URL.createObjectURL(first)
      : undefined;
    startCase(caseId, docType, {
      originalUrl,
      originalFilename: first.name,
      originalKind: isImage ? 'image' : 'doc',
    });

    // 로딩 페이지로 즉시 이동
    router.push(`/review/${caseId}/loading`);

    // 백엔드 호출 (백그라운드) — document_type 으로 분기.
    try {
      const ctx = toWorkplaceContext(workplace);
      if (docType === 'employment-contract') {
        // 풀 이식 4단계 — 1) extract + 2) structure 까지 자동 연쇄.
        // 사용자가 검토 페이지(Step2)에서 표를 수정한 뒤 analyze → result → contract 로 진행.
        updateEc(caseId, { phase: 'extracting' });
        // 여러 장(여러 페이지) 지원 + 이미지는 업로드 전 자동 압축(413 방지).
        const extractedText = await extractAllText(files, postEcExtract, {
          caseId,
          service: '근로계약서',
        });

        updateEc(caseId, {
          phase: 'structuring',
          extractedText,
        });
        // AI 1차 분류(/ec/classify)를 structure 와 병렬 실행 — 분류는 부가 정보라
        // 실패해도 흐름을 막지 않는다 (catch → null → 폼 workerTypes fallback).
        const [structured, cls] = await Promise.all([
          postEcStructure(extractedText),
          postEcClassify(extractedText).catch(() => null),
        ]);

        // 응답 검증 — LLM 이 가끔 빈 dict 나 누락된 응답을 줄 때가 있어, 그대로 review 단계로
        // 넘어가면 사용자 화면에 "구조화 데이터가 없어요" 가 뜬다. 명시적 검증으로 catch 로 보냄.
        const sd = structured?.structured_data;
        if (!sd || typeof sd !== 'object' || Object.keys(sd).length === 0) {
          throw new Error(
            '계약서 구조화 결과가 비어있어요. OCR 텍스트가 짧거나 형식이 표준 계약서가 아닐 수 있습니다.',
          );
        }

        // 사업장 컨텍스트(폼에서 받은 것)를 ec 워크플로에 같이 박아둠.
        // 사용자가 검토 페이지에서 다시 바꿀 수 있고, analyze 호출 직전에 최신값으로 덮어씀.
        // workerTypes(폼 값)는 분류 실패·레거시 경로의 fallback 으로 그대로 유지.
        updateEc(caseId, {
          phase: 'review',
          structuredData: sd,
          businessSize: ctx.businessSize ?? '',
          workerTypes: ctx.workerTypes,
          classify: cls
            ? {
                workerTypes: cls.worker_types,
                docKind: cls.doc_kind,
                reason: cls.reason,
              }
            : undefined,
        });
        // LoadingScreen 이 status='done' 을 트리거로 다음 라우트로 보내므로,
        // EC 풀 이식에선 result 가 아닌 phase='review' 가 그 신호.
        // → LoadingScreen 측 폴링에서 phase 를 보고 /ec/review 로 라우팅.
      } else {
        // 취업규칙 — 추출 후 사용자 확인 단계로.
        //   1) /ec/extractions (범용 parse_to_text — docx/hwp/pdf/txt/이미지) 파일 → 텍스트
        //   2) AI 근로환경 1차 분류 (교대제·산안법·화학물질·작업환경측정 추정)
        //      — 실패해도 흐름 계속 (확인 배너만 생략, 보수적 기본값 검사)
        //   3) (사용자 확인·수정) /review/[id]/wr/review — '분석 시작' 시 postReviewWorkRules 호출.
        const wrText = await extractAllText(files, postEcExtract, {
          caseId,
          service: '취업규칙',
        });
        const wrCls = await postWrClassify(wrText).catch(() => null);

        updateWr(caseId, {
          phase: 'review',
          extractedText: wrText,
          context: ctx,
          ...(wrCls
            ? {
                classify: {
                  shiftWorkUsed: wrCls.shift_work_used,
                  oshaApplicable: wrCls.osha_applicable,
                  chemicalHandling: wrCls.chemical_handling,
                  workenvMeasurement: wrCls.workenv_measurement,
                  docKind: wrCls.doc_kind,
                  reason: wrCls.reason,
                },
              }
            : {}),
        });
        // LoadingScreen 은 wr.phase='review' 를 보고 /review/[id]/wr/review 로 라우팅.
      }
    } catch (err) {
      const rawMsg =
        err instanceof ApiCallError
          ? err.detail
          : err instanceof Error
            ? err.message
            : String(err);
      // 사용자 친화 변환 — 빈번한 백엔드 메시지를 한국어로 풀어 안내
      const friendly = humanizeError(rawMsg, err instanceof ApiCallError ? err.status : undefined);
      setCaseError(caseId, friendly);
    } finally {
      setSubmitting(false);
    }
  };

  /**
   * 백엔드 에러를 사용자가 이해할 수 있는 메시지로 변환.
   * 원본 detail 도 부가 정보로 포함 (운영자가 트러블슈팅 시 유용).
   */
  function humanizeError(detail: string, status?: number): string {
    const d = (detail || '').toLowerCase();
    // OCR 관련
    if (d.includes('텍스트 추출 실패') || d.includes('parse_to_text') || d.includes('ocr')) {
      return (
        '📷 OCR 텍스트 추출에 실패했어요.\n' +
        '  • 이미지가 흐릿하거나 빛 반사가 있는 경우, 글자가 선명한 사진으로 다시 시도해 주세요.\n' +
        '  • PDF 가 스캔본이면 같은 페이지를 PNG/JPG 로 저장해서 올려주세요.\n' +
        `(상세: ${detail.slice(0, 200)})`
      );
    }
    if (d.includes('quota') || d.includes('rate limit') || d.includes('429')) {
      return (
        '⏳ LLM 요청이 잠시 몰리고 있어요.\n' +
        '  잠시 후 (10~30초) 다시 시도해 주세요.'
      );
    }
    if (d.includes('timeout') || d.includes('timed out')) {
      return (
        '⏱ 검토에 시간이 오래 걸려서 끊겼어요.\n' +
        '  파일이 너무 크거나 OCR 이 무거운 경우입니다.\n' +
        '  더 작은 파일·이미지로 다시 시도해 주세요.'
      );
    }
    if (status === 401 || d.includes('api key')) {
      return (
        '🔑 인증 키 문제로 백엔드에 접근하지 못했어요. 운영자에게 문의해 주세요.\n' +
        `(상세: ${detail.slice(0, 120)})`
      );
    }
    if (status === 503 || d.includes('503')) {
      return (
        '🚧 백엔드 서비스가 일시적으로 사용 불가입니다. 잠시 후 다시 시도해 주세요.'
      );
    }
    if (d.includes('502') || d.includes('백엔드 호출 실패') || d.includes('connect')) {
      return (
        '🔌 백엔드 연결에 실패했어요.\n' +
        '  네트워크 상태를 확인하시거나 잠시 후 다시 시도해 주세요.'
      );
    }
    if (d.includes('analysis_result') || d.includes('응답 형식이 올바르지 않')) {
      return (
        '⚠️ AI 응답을 해석하지 못했어요.\n' +
        '  파일 내용이 너무 짧거나 형식이 명세서·계약서가 아닐 수 있어요.'
      );
    }
    if (!detail) {
      return '알 수 없는 오류가 발생했어요. 새로고침 후 다시 시도해 주세요.';
    }
    // 기본 — 원본 detail 그대로
    return detail;
  }

  // ───────── 모바일(≤720px) — 시안 2단계 앱 플로 ─────────
  if (isMobile) {
    const selectedCard =
      MOBILE_DOC_CARDS.find((c) => c.id === docType) ?? MOBILE_DOC_CARDS[0];

    if (mobileStep === 'select') {
      return (
        <div className={styles.mPage}>
          {/* 시안 .home-hero */}
          <div className={styles.mHero}>
            <div className={styles.mLogo}>
              <span className={styles.mLogoMark}>
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" aria-hidden>
                  <path d="M12 3l8 3v6c0 5-4 8-8 9-4-1-8-4-8-9V6l8-3z" />
                </svg>
              </span>
              <span className={styles.mLogoName}>
                노동법 자율점검
                <small>고용노동부 기준 검토</small>
              </span>
            </div>
            <h1 className={styles.mTitle}>
              우리 사업장의 노동법 서류,
              <br />
              <span className={styles.mTitleBrand}>스스로 점검해 보세요.</span>
            </h1>
            <p className={styles.mLead}>
              서류를 올리면 위반·누락 항목을 위험도별로 정리하고, 어떻게
              시정하면 되는지 법령 근거와 함께 안내합니다.
            </p>
          </div>

          {/* 시안 .doctype — 4종 모두 활성 */}
          <div className={styles.mDoctype}>
            <div className={styles.mLab}>무엇을 검토할까요?</div>
            {MOBILE_DOC_CARDS.filter((c) => !c.hidden).map((c) => (
              <button
                key={c.id}
                type="button"
                className={styles.mDtCard}
                onClick={() => {
                  setDocType(c.id);
                  setMobileStep('upload');
                }}
              >
                <span className={styles.mDtIcon}>{c.icon}</span>
                <span className={styles.mDtTitleCenter}>{c.title}</span>
                <svg
                  className={styles.mDtChevron}
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  aria-hidden
                >
                  <path d="M9 6l6 6-6 6" />
                </svg>
              </button>
            ))}
          </div>
        </div>
      );
    }

    // mobileStep === 'upload' — 시안 s-upload
    return (
      <div className={styles.mPage}>
        {/* 시안 .appbar */}
        <div className={styles.mAppbar}>
          <button
            type="button"
            className={styles.mAppbarBack}
            onClick={() => setMobileStep('select')}
            aria-label="문서 선택으로 돌아가기"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
              <path d="M15 18l-6-6 6-6" />
            </svg>
          </button>
          <div className={styles.mAppbarTitle}>{selectedCard.title} 올리기</div>
        </div>

        <div className={styles.mBody}>
          {/* 선택 문서 확인 카드는 제거 — 앱바 제목('○○ 올리기')이 이미 안내.
              업로드 E안 — 촬영 우선 + 스캔 + 다중 촬영 트레이 (모바일).
              사업장 규모는 인라인이 아니라 '검토 시작' 시 팝업으로 묻는다(아래 시트). */}
          <MobileUploadE docType={docType} value={files} onChange={setFiles} />
        </div>

        {/* 시안 .home-cta — 하단 고정 CTA */}
        <div className={styles.mCta}>
          <button
            type="button"
            className={styles.mCtaBtn}
            disabled={!canSubmit}
            onClick={() => setSizeSheetOpen(true)}
          >
            {submitting ? '검토 준비 중…' : '검토 시작하기'}
          </button>
          <div className={styles.mCtaTip}>
            파일은 검토 후 즉시 삭제되며 회원가입이 필요 없습니다
          </div>
        </div>

        {/* ── 사업장 규모 확인 바텀시트 ── */}
        <div
          className={`${styles.mSizeScrim} ${sizeSheetOpen ? styles.mSizeScrimOn : ''}`}
          onClick={() => setSizeSheetOpen(false)}
          aria-hidden
        />
        <div
          className={`${styles.mSizeSheet} ${sizeSheetOpen ? styles.mSizeSheetOn : ''}`}
          role="dialog"
          aria-modal={sizeSheetOpen}
          aria-label="사업장 규모"
        >
          <div className={styles.mSizeGrab} />
          <div className={styles.mSizeTitle}>사업장 규모를 알려주세요</div>
          <div className={styles.mSizeSub}>
            상시 근로자 수에 따라 적용 규정이 달라요. 잘 모르겠으면 ‘5인 이상’으로 두세요.
          </div>
          <div className={styles.mSizeOpts}>
            {[
              { v: '5+', label: '5인 이상' },
              { v: '5-', label: '5인 미만' },
            ].map((o) => {
              const active = workplace.businessSize === o.v;
              return (
                <button
                  key={o.v}
                  type="button"
                  className={`${styles.mSizeOpt} ${active ? styles.mSizeOptOn : ''}`}
                  aria-pressed={active}
                  onClick={() =>
                    setWorkplace({ ...workplace, businessSize: o.v as typeof workplace.businessSize })
                  }
                >
                  {o.label}
                </button>
              );
            })}
          </div>
          <button
            type="button"
            className={styles.mSizeGo}
            disabled={submitting}
            onClick={() => {
              setSizeSheetOpen(false);
              void startReview();
            }}
          >
            {submitting ? '검토 준비 중…' : '이 내용으로 검토 시작'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <SiteHeader />

      <div className={styles.container}>
        <Hero />

        {/* 1. 문서 종류 */}
        <section className={styles.section}>
          <SectionHeading step={1} title="어떤 문서를 검토하시나요?" />
          <DocTypePicker value={docType} onChange={setDocType} />
        </section>

        {/* 2. 업로드 */}
        <section className={styles.sectionTight}>
          <SectionHeading
            step={2}
            title="파일을 올려주세요"
            hint={
              <>
                <Icon name="shield" size={11} /> 파일은 검토 후 즉시 삭제됩니다
              </>
            }
          />
          <FileDropzone value={files} onChange={setFiles} />
        </section>

        {/* 3. 사업장 정보 */}
        <section className={styles.section}>
          <SectionHeading step={3} title="사업장 기본 정보" />
          <WorkplaceForm
            value={workplace}
            onChange={setWorkplace}
            documentType={docType}
          />
        </section>

        {/* CTA */}
        <Button
          variant="primary"
          size="lg"
          fullWidth
          icon="search"
          disabled={!canSubmit}
          onClick={startReview}
          className={styles.cta}
        >
          {submitting ? '검토 준비 중…' : '검토 시작하기'}
        </Button>
        <div className={styles.footnote}>
          평균 1~2분 소요됩니다 · 결과는 PDF로 저장하여 사업장 보관 가능
        </div>
      </div>
    </div>
  );
}
