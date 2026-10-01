'use client';

import { useEffect, useMemo, useRef, useState, use } from 'react';
import Link from 'next/link';

import SiteHeader from '@/components/layout/SiteHeader';
import WsPayslipFormView from '@/components/review/WsPayslipFormView';
import { getCase, updateWs } from '@/lib/reviewStore';
import { downloadWsDocx, downloadWsFormDocx, type WsPayslipForm } from '@/lib/api/ws';
import { ApiCallError } from '@/lib/api/client';

import styles from './page.module.css';

/**
 * 임금명세서 — 공식 서식 비주얼 뷰 (구조화 생성 결과를 칸별로 바인딩).
 *
 * 좌: 원본 임금명세서(참고) · 우: 공식 서식 양식 뷰(보완 칸 하이라이트).
 * 구버전(텍스트만 있는 케이스)은 하단 textarea 폴백.
 */

/** 구조화 폼 → 공식 서식 텍스트 (.docx/.txt 내보내기용). */
function formToText(f: WsPayslipForm): string {
  const L: string[] = [];
  const won = (v?: string) => {
    const s = (v ?? '').trim();
    return s ? (/[원,]/.test(s) ? s : `${s}원`) : '';
  };
  L.push('[임금명세서]');
  L.push(`산정 기간    : ${f.settlementPeriod || ''}`);
  L.push(`지급일       : ${f.paymentDate || ''}`);
  L.push(`교부 방식    : ${f.deliveryMethod || ''}`);
  L.push('');
  L.push('[사용자(사업자) 정보]');
  L.push(`상호         : ${f.employer?.company || ''}`);
  L.push(`사업자등록번호: ${f.employer?.businessNo || ''}`);
  L.push(`대표자       : ${f.employer?.ceo || ''}`);
  L.push(`주소         : ${f.employer?.address || ''}`);
  L.push('');
  L.push('[근로자 정보]');
  L.push(`성명         : ${f.worker?.name || ''}`);
  L.push(`사번/생년월일 : ${f.worker?.idOrBirth || ''}`);
  L.push(`부서/직급    : ${[f.worker?.dept, f.worker?.position].filter(Boolean).join(' / ')}`);
  L.push('');
  L.push('[근로시간]');
  L.push(
    `근로일수 ${f.workTime?.days || '-'} · 근로시간 ${f.workTime?.hours || '-'} · ` +
      `연장 ${f.workTime?.overtime || '-'} · 야간 ${f.workTime?.night || '-'} · 휴일 ${f.workTime?.holiday || '-'}`,
  );
  L.push('');
  L.push('[지급 내역]');
  for (const p of f.payments || []) {
    L.push(`- ${p.name} : ${won(p.amount)}${p.basis ? ` (${p.basis})` : ''}`);
  }
  L.push(`지급 총액    : ${won(f.paymentTotal)}`);
  L.push('');
  L.push('[공제 내역]');
  for (const d of f.deductions || []) {
    L.push(`- ${d.name} : ${won(d.amount)}${d.basis ? ` (${d.basis})` : ''}`);
  }
  L.push(`공제 총액    : ${won(f.deductionTotal)}`);
  L.push('');
  L.push(`[실수령액]  ${won(f.netPay)}`);
  if (Array.isArray(f.notes) && f.notes.length) {
    L.push('');
    L.push('[비고]');
    for (const n of f.notes) L.push(`- ${n}`);
  }
  return L.join('\n');
}

export default function WsContractPage(props: { params: Promise<{ id: string }> }) {
  const params = use(props.params);
  const caseId = params.id;

  const [mounted, setMounted] = useState(false);
  const [entry, setEntry] = useState<ReturnType<typeof getCase>>(null);
  // 편집 가능한 양식 상태 — store 의 생성본으로 초기화, 편집 시 store 에 영속화.
  const [form, setForm] = useState<WsPayslipForm | null>(null);
  const [dirty, setDirty] = useState(false);
  const originalRef = useRef<WsPayslipForm | null>(null);

  useEffect(() => {
    setMounted(true);
    const e = getCase(caseId);
    setEntry(e);
    const f = e?.ws?.generatedWageForm ?? null;
    setForm(f);
    originalRef.current = f;
  }, [caseId]);

  const legacyText = entry?.ws?.generatedWageText ?? '';

  // 인라인 편집 커밋 — 상태 갱신 + store 영속화(새로고침해도 유지).
  const handleFormChange = (next: WsPayslipForm) => {
    setForm(next);
    setDirty(true);
    updateWs(caseId, { generatedWageForm: next });
  };
  const handleRestore = () => {
    const o = originalRef.current;
    setForm(o);
    setDirty(false);
    updateWs(caseId, { generatedWageForm: o ?? undefined });
  };

  const baseName = useMemo(() => {
    const base = entry?.originalFilename || '임금명세서';
    return base.replace(/\.(png|jpe?g|pdf|docx?|hwp|txt)$/i, '');
  }, [entry]);

  const exportText = useMemo(
    () => (form ? formToText(form) : legacyText),
    [form, legacyText],
  );

  const [downloadingDocx, setDownloadingDocx] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  if (!mounted) {
    return <main className={styles.page} aria-hidden />;
  }

  if (!form && !legacyText) {
    return (
      <main className={styles.page}>
        <SiteHeader />
        <div className={styles.containerSimple}>
          <div className={styles.notFound}>
            <h1>수정된 명세서가 없습니다</h1>
            <p>
              <Link href={`/review/${caseId}/ws`}>← 검토 결과로 돌아가기</Link>
            </p>
          </div>
        </div>
      </main>
    );
  }

  const handleDownloadDocx = async () => {
    setDownloadingDocx(true);
    setDownloadError(null);
    try {
      if (form) {
        // 공식 서식 표 레이아웃 docx (화면 양식과 동일)
        await downloadWsFormDocx(form, `${baseName}_표준명세서.docx`);
      } else {
        await downloadWsDocx({
          wage_text: exportText,
          filename: `${baseName}_표준명세서.docx`,
        });
      }
    } catch (err) {
      const msg =
        err instanceof ApiCallError
          ? err.detail
          : err instanceof Error
            ? err.message
            : String(err);
      setDownloadError(msg);
    } finally {
      setDownloadingDocx(false);
    }
  };

  return (
    <main className={styles.page}>
      <SiteHeader />
      <div className={styles.layout}>
        {/* 검토 결과로 — 맨 위 */}
        <div className={`${styles.backRow} noPrint`}>
          <Link href={`/review/${caseId}/ws`} className={styles.btnSecondary}>
            ← 검토 결과로
          </Link>
        </div>

        <header className={styles.topbar}>
          <div className={styles.topbarLeft}>
            <span className={styles.eyebrow}>임금명세서 · 표준 양식</span>
            <h1 className={styles.title}>
              시정 반영 표준 임금명세서
              {dirty && <span className={styles.dirtyBadge}>✎ 편집됨</span>}
            </h1>
            <p className={styles.subtitle}>
              분석에서 지적된 누락·부적절 항목을 모두 반영해 공식 서식 칸에 채웠습니다.{' '}
              <span className={styles.supLegend}>보완</span> 표시는 새로 보완된 칸이에요.
              {form && ' 각 칸을 눌러 직접 수정할 수 있고, 수정은 자동 저장됩니다.'}
            </p>
            {dirty && (
              <button
                type="button"
                className={`${styles.btnTertiary} noPrint`}
                onClick={handleRestore}
                title="AI 생성 원본으로 되돌리기"
              >
                ↺ 생성 원본으로 되돌리기
              </button>
            )}
          </div>
        </header>

        {/* 공식 서식 양식 뷰 — 단일 컬럼, 가로 폭에 맞춤. 각 칸 인라인 편집. */}
        <section className={styles.formPanel} aria-label="표준 임금명세서 양식">
          {form ? (
            <WsPayslipFormView form={form} editable onChange={handleFormChange} />
          ) : (
            <pre className={`${styles.body} ${styles.bodyReadonly}`}>{legacyText}</pre>
          )}
        </section>

        {/* 액션 바 */}
        <div className={`${styles.actionBar} noPrint`}>
          <button
            type="button"
            className={styles.btnSecondary}
            onClick={() => window.print()}
            title="브라우저 인쇄 — PDF 저장 가능"
          >
            📄 인쇄·PDF
          </button>
          <button
            type="button"
            className={styles.btnPrimary}
            onClick={handleDownloadDocx}
            disabled={downloadingDocx}
            title="MS Word 호환 .docx"
          >
            {downloadingDocx ? '변환 중…' : '⬇ Word 문서 (.docx)'}
          </button>
        </div>

        {downloadError && (
          <div
            style={{
              marginTop: 8,
              padding: '10px 14px',
              background: '#fee2e2',
              border: '1px solid #fca5a5',
              borderRadius: 8,
              color: '#991b1b',
              fontSize: 13,
            }}
            className="noPrint"
          >
            <strong>다운로드 실패:</strong> {downloadError}
          </div>
        )}

        <footer className={styles.footer}>
          <span className={styles.footerNote}>
            ⚠️ 이 양식은 AI 가 생성한 표준안입니다. 실제 임금 금액·세금 공제율 등
            정확한 수치는 사업장 자체 검토가 필요합니다.
          </span>
        </footer>
      </div>
    </main>
  );
}
