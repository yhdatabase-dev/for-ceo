'use client';

import { useEffect, useState, use } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

import WsTypeConfirm from '@/components/review/WsTypeConfirm';
import { postWsAnalyze } from '@/lib/api/ws';
import { ApiCallError } from '@/lib/api/client';
import { getCase, setCaseError, updateWs } from '@/lib/reviewStore';

import styles from './page.module.css';

/**
 * 임금명세서 — 분석 전 '계약 유형 확인' 페이지.
 *
 * (변경) 기존 OCR 텍스트 수정 단계를 제거했다. 추출 텍스트는 그대로 분석에
 * 쓰고, 사용자는 AI 가 1차 판단한 계약 유형을 [맞아요/아니에요]로 확인만 한다.
 * '분석 시작' → 확정한 계약 유형으로 /ws/analyze 호출 (모바일·데스크톱 공용).
 */
export default function WsReviewPage(props: { params: Promise<{ id: string }> }) {
  const params = use(props.params);
  const router = useRouter();
  const caseId = params.id;

  // SSR / client mount 간 hydration 일관성 — store 는 mount 후에만.
  const [mounted, setMounted] = useState(false);
  const [entry, setEntry] = useState<ReturnType<typeof getCase>>(null);
  const [submitting, setSubmitting] = useState(false);
  // 사용자가 확정한 계약 유형 (controlled). null = 마운트 전.
  const [confirmedType, setConfirmedType] = useState<string | null>(null);

  useEffect(() => {
    setMounted(true);
    const e = getCase(caseId);
    setEntry(e);
    setConfirmedType(
      e?.ws?.classify?.contractType ?? e?.ws?.contractType ?? '정규직',
    );
  }, [caseId]);

  if (!mounted) {
    return <main className={styles.page} aria-hidden />;
  }

  // 케이스 없음 / 추출 텍스트 없음 — 새로고침으로 저장소가 비었거나 잘못된 URL.
  if (!entry || !entry.ws?.extractedText) {
    return (
      <main className={styles.page}>
        <div className={styles.container}>
          <div className={styles.notFound}>
            <h1 className={styles.title}>분석할 내용을 찾을 수 없습니다</h1>
            <p className={styles.notFoundDesc}>
              세션 ID <code className={styles.code}>{caseId}</code> 의 추출
              결과를 찾지 못했어요. 브라우저 저장소가 비워졌거나 다른 기기에서
              시작한 검토일 수 있습니다.
            </p>
            {entry?.ws?.errorMessage && (
              <p className={styles.notFoundError}>
                이전 오류: {entry.ws.errorMessage.slice(0, 200)}
              </p>
            )}
            <p>
              <Link href="/" className={styles.notFoundLink}>
                ← 새로 검토 시작하기
              </Link>
            </p>
          </div>
        </div>
      </main>
    );
  }

  const ws = entry.ws;
  const cls = ws.classify;

  // AI 가 명세서에서 읽어낸 산정 대상·지급주기 요약 (투명성 표시).
  const periodBits: string[] = [];
  if (cls?.payPeriodYear) {
    periodBits.push(
      cls.payPeriodMonth
        ? `${cls.payPeriodYear}년 ${cls.payPeriodMonth}월분`
        : `${cls.payPeriodYear}년`,
    );
  }
  if (cls?.payCycle) periodBits.push(cls.payCycle);

  const startAnalyze = () => {
    const finalType = confirmedType ?? ws.contractType ?? '정규직';
    setSubmitting(true);
    updateWs(caseId, {
      phase: 'analyzing',
      errorMessage: undefined,
      contractType: finalType,
      // 백엔드 슬롯 분기는 worker_types 를 사용 — 계약 유형 단일값으로 동기화.
      workerTypes: [finalType],
    });
    router.push(`/review/${caseId}/loading`);
    // 백그라운드 fetch — 페이지 이탈 후에도 promise 는 살아있다.
    postWsAnalyze({
      wage_text: ws.extractedText ?? '',
      business_size: ws.businessSize ?? '',
      worker_types: [finalType],
      pay_period_year: ws.payPeriodYear ?? undefined,
      pay_period_month: ws.payPeriodMonth ?? undefined,
      contract_type: finalType,
      pay_cycle: ws.payCycle ?? undefined,
      weekly_hours: ws.weeklyHours ?? undefined,
      case_id: caseId,
    })
      .then((out) => {
        updateWs(caseId, {
          phase: 'result',
          analysisResult: out.analysis_result,
        });
      })
      .catch((err) => {
        const msg =
          err instanceof ApiCallError
            ? err.detail
            : err instanceof Error
              ? err.message
              : String(err);
        // setCaseError 는 entry 를 새로 만들며 ws 를 비우므로, 재시도 가능 상태 보존.
        setCaseError(caseId, msg);
        updateWs(caseId, {
          phase: 'review',
          errorMessage: msg,
          contractType: finalType,
          businessSize: ws.businessSize,
          workerTypes: [finalType],
          payPeriodYear: ws.payPeriodYear,
          payPeriodMonth: ws.payPeriodMonth,
          payCycle: ws.payCycle,
          weeklyHours: ws.weeklyHours,
          classify: ws.classify,
        });
      });
  };

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <h1 className={styles.title}>임금명세서를 분석할게요</h1>
        <p className={styles.subtitle}>
          업로드하신 명세서를 <strong>AI 가 읽고 계약 유형을 판단</strong>했어요.
          맞는지 확인한 뒤 <strong>&ldquo;분석 시작&rdquo;</strong>을 눌러
          주세요. 최저임금·필수 기재항목 기준이 계약 유형에 따라 달라집니다.
        </p>

        <div className={styles.confirmWrap}>
          <WsTypeConfirm
            docKind={cls?.docKind ?? '임금명세서'}
            reason={cls?.reason}
            aiType={cls?.contractType ?? ws.contractType ?? '정규직'}
            value={confirmedType ?? ''}
            onChange={setConfirmedType}
          />
          {cls && (
            <p className={styles.detected}>
              {periodBits.length > 0 ? (
                <>
                  📅 AI가 읽은 산정 대상 ·{' '}
                  <strong>{periodBits.join(' · ')}</strong>
                </>
              ) : (
                <>
                  📅 명세서에서 <strong>산정 기간·지급 주기 표기를 찾지
                  못했어요</strong> — 필수 기재사항이라 분석에서 누락 여부를
                  확인합니다.
                </>
              )}
            </p>
          )}
        </div>

        {ws.errorMessage && (
          <div className={styles.error}>
            <strong>분석 실패:</strong> {ws.errorMessage}
          </div>
        )}

        <div className={styles.ctaBar}>
          <Link href="/" className={styles.btnSecondary}>
            ← 처음으로
          </Link>
          <button
            type="button"
            className={styles.btnPrimary}
            onClick={startAnalyze}
            disabled={submitting}
          >
            {submitting ? '분석 준비 중…' : '분석 시작'}
          </button>
        </div>
      </div>
    </main>
  );
}
