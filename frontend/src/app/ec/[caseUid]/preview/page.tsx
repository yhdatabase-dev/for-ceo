'use client';

import { useCallback, useEffect, useMemo, useRef, useState, use } from 'react';
import Link from 'next/link';

import ContractFormView, {
  buildContractText,
  buildEcFormModel,
  type ContractFormState,
} from '@/features/ec/components/ContractFormView';
import ChatPanel from '@/components/review/ChatPanel';
import { getCase } from '@/features/history/store';
import { downloadEcDocx, postEcValidateField } from '@/features/ec/api';
import { ApiCallError } from '@/lib/api/client';

import styles from './page.module.css';
import { routes } from '@/lib/routes';

/**
 * Step4 — 표준 근로계약서 페이지.
 *
 * 두 가지 보기:
 * - **양식 보기 (기본)** — 고용노동부 표준 서식 모양 그대로 렌더, 사용자의
 *   계약 내용(structuredData)을 결정적으로 칸에 채움. 부적절/보완필요 칸은
 *   표준 문구(또는 사용자 담은 표현)로 보완 + '보완됨' 표시. 모든 칸 편집 가능.
 * - **텍스트 보기** — 기존 LLM 생성 본문 textarea (그대로 유지).
 *
 * 다운로드·복사·인쇄는 항상 현재 보기의 최신 편집본을 사용한다.
 * 훅 순서 주의 — 모든 훅은 조기 return 위에서 호출 (이전 hook-order 버그 재발 금지).
 */
export default function EcContractPage(
  props: {
    params: Promise<{ caseUid: string }>;
  }
) {
  const params = use(props.params);
  const caseId = params.caseUid;

  // ─── HOOK ORDER — 모든 훅은 조기 return 보다 위 ───
  const [mounted, setMounted] = useState(false);
  const [entry, setEntry] = useState<ReturnType<typeof getCase>>(null);
  const [draft, setDraft] = useState<string>('');
  const originalRef = useRef<string>('');
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [downloadingDocx, setDownloadingDocx] = useState(false);
  /** 양식 편집 상태 — null 이면 자동 채움(초기값) 그대로. */
  const [formState, setFormState] = useState<ContractFormState | null>(null);
  /** 칸별 재검토 결과 — 사용자가 고친 뒤 AI 재판정(✓ 적정 / ! 부적정). */
  const [revalidated, setRevalidated] = useState<
    Record<string, { flag: 'ok' | 'invalid'; reason?: string; example?: string }>
  >({});
  const [validating, setValidating] = useState<Record<string, boolean>>({});
  const lastCheckedRef = useRef<Record<string, string>>({});

  useEffect(() => {
    setMounted(true);
    const e = getCase(caseId);
    setEntry(e);
    const text = e?.ec?.generatedContract ?? '';
    setDraft(text);
    originalRef.current = text;
  }, [caseId]);

  /**
   * 양식 모델 — structuredData/analysis/userOverrides 만으로 결정적 채움.
   * generatedContract(LLM 자유 텍스트)는 절대 파싱하지 않는다.
   */
  const formModel = useMemo(() => {
    const ec = entry?.ec;
    if (!ec?.structuredData) return null;
    try {
      // 근로자 유형 — 분류 확정값 우선, 없으면 폼 입력값. 유형별 서식 분기에 사용.
      const workerTypes =
        ec.classify?.workerTypes ?? ec.workerTypes ?? [];
      const typeLabel = ec.classify?.docKind ?? '';
      return buildEcFormModel(
        ec.structuredData,
        ec.analysisResult ?? null,
        ec.userOverrides ?? {},
        workerTypes,
        typeLabel,
      );
    } catch {
      return null;
    }
  }, [entry]);

  // 양식을 만들 수 있으면 항상 양식, 아니면(structuredData 없음) 텍스트 폴백.
  const activeView: 'form' | 'text' = formModel ? 'form' : 'text';
  const effectiveForm = formState ?? formModel?.state ?? null;

  /** 다운로드·복사에 쓰일 현재 보기의 텍스트. */
  const activeText =
    activeView === 'form' && effectiveForm
      ? buildContractText(effectiveForm)
      : draft;

  const filenameBase =
    (entry?.originalFilename || '근로계약서')
      .replace(/\.[^.]+$/, '')
      .trim() || '근로계약서';

  const dirty = draft.trim() !== originalRef.current.trim();
  const formDirty = formState !== null;

  const pushToast = (msg: string) => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast(msg);
    toastTimer.current = setTimeout(() => setToast(null), 2400);
  };

  const handleDownloadDocx = useCallback(async () => {
    if (!activeText) return;
    setDownloadingDocx(true);
    try {
      await downloadEcDocx({
        contract_text: activeText,
        filename: `${filenameBase}_표준양식.docx`,
      });
      pushToast('✓ Word 문서로 저장됨');
    } catch (err) {
      const msg =
        err instanceof ApiCallError
          ? err.detail
          : err instanceof Error
            ? err.message
            : String(err);
      pushToast(`DOCX 변환 실패: ${msg}`);
    } finally {
      setDownloadingDocx(false);
    }
  }, [activeText, filenameBase]);

  const handlePrint = useCallback(() => {
    if (typeof window === 'undefined') return;
    window.print();
  }, []);

  const handleReset = () => {
    if (activeView === 'form') {
      setFormState(null);
      setRevalidated({});
      lastCheckedRef.current = {};
      pushToast('자동 입력값으로 되돌렸어요');
    } else {
      setDraft(originalRef.current);
      pushToast('LLM 원본으로 되돌렸어요');
    }
  };

  // 칸 편집 후 포커스 아웃 → 그 칸만 AI 재검토 → 점 ✓(적정)/!(부적정). (값 변화 없으면 skip)
  const handleFieldBlur = useCallback(
    async (id: string, value: string, label: string) => {
      const v = (value || '').trim();
      if (lastCheckedRef.current[id] === v) return;
      lastCheckedRef.current[id] = v;
      const ec = getCase(caseId)?.ec;
      const items = formModel?.items as Record<string, string> | undefined;
      const fieldName = items?.[id] || label;
      if (!fieldName) return;
      setValidating((s) => ({ ...s, [id]: true }));
      try {
        const out = await postEcValidateField({
          field: fieldName,
          value: v,
          business_size: ec?.businessSize ?? '',
          worker_types: ec?.classify?.workerTypes ?? ec?.workerTypes ?? [],
        });
        // 부적정(빈칸·위반)만 빨강 ! — 적절·보완필요(기재됨)는 초록 ✓.
        // (보완필요를 빨강으로 두면 '하란대로 채웠는데 안 바뀜'으로 혼란)
        const flag: 'ok' | 'invalid' = out.적절성 === '부적정' ? 'invalid' : 'ok';
        setRevalidated((s) => ({
          ...s,
          [id]: { flag, reason: out.이유, example: out.작성예시 },
        }));
      } catch {
        /* 실패 시 원래 점 유지 */
      } finally {
        setValidating((s) => ({ ...s, [id]: false }));
      }
    },
    [formModel, caseId],
  );

  // ─── 조기 return — 훅은 모두 위에서 끝남 ───

  if (!mounted) {
    return <main className={styles.page} aria-hidden />;
  }

  if (!originalRef.current && !formModel) {
    return (
      <main className={styles.page}>
        <div className={styles.layout}>
          <div className={styles.notFound}>
            <h1 className={styles.title}>생성된 계약서가 없습니다</h1>
            <p>
              <Link href={routes.ecReview(caseId)}>← 검토 결과로 돌아가기</Link>
            </p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className={styles.page}>
      <div className={styles.layout}>
        {toast && (
          <div className={styles.toast} role="status" aria-live="polite">
            {toast}
          </div>
        )}
        <div className={`${styles.backRow} noPrint`}>
          <Link href={routes.ecReview(caseId)} className={styles.btnSecondary}>
            ← 검토 결과로
          </Link>
        </div>
        <div className={styles.head}>
          {activeView === 'text' && dirty && (
            <span className={styles.dirtyBadge}>✎ 편집됨</span>
          )}
          {activeView === 'form' && formDirty && (
            <span className={styles.dirtyBadge}>✎ 편집됨</span>
          )}
        </div>
        <h1 className={styles.title}>표준 근로계약서</h1>
        <div className={styles.subtitle}>
          {activeView === 'form' ? (
            <>
              <strong>고용노동부 표준 서식</strong>에 검토하신 계약 내용을{' '}
              <strong>그대로 채워 넣은 양식</strong>이에요. 칸 옆{' '}
              <span className={styles.legendFix}>보완됨</span> 점은
              부적절·보완필요 판정을 표준 문구(또는 직접 담은 표현)로 채운
              칸, <span className={styles.legendWarn}>확인필요</span> 점은
              직접 확인 후 입력이 필요한 칸이에요. 모든 칸은 클릭해서 수정할 수
              있습니다.
            </>
          ) : (
            <>
              <strong>분석 결과의 보완사항</strong>을 반영해 LLM 이 생성한{' '}
              <strong>초안</strong>이에요. 본문을 클릭해{' '}
              <strong>사업장 정보·금액·날짜를 직접 채워 넣을 수 있고</strong>,
              수정한 내용 그대로 다운로드·복사·인쇄됩니다.
            </>
          )}
        </div>

        {activeView === 'form' && effectiveForm && formModel ? (
          <ContractFormView
            value={effectiveForm}
            flags={formModel.flags}
            onChange={setFormState}
            suggestions={formModel.suggestions}
            revalidated={revalidated}
            validating={validating}
            onFieldBlur={handleFieldBlur}
          />
        ) : (
          <textarea
            className={styles.contractEditor}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            spellCheck={false}
            placeholder="생성된 계약서 본문이 없어요. [양식 보기]를 사용해 주세요."
            aria-label="표준 근로계약서 본문 (편집 가능)"
          />
        )}

        {/* 다운로드·인쇄 — 양식 하단 */}
        <div className={`${styles.actions} noPrint`}>
          <button
            type="button"
            className={styles.btnPrimary}
            onClick={handleDownloadDocx}
            disabled={downloadingDocx}
            title="MS Word 호환 .docx — 사내 워드에서 그대로 편집·인쇄"
          >
            {downloadingDocx ? '변환 중…' : '⬇ Word 문서 (.docx)'}
          </button>
          <button
            type="button"
            className={styles.btnSecondary}
            onClick={handlePrint}
          >
            🖨 인쇄 / PDF
          </button>
          {((activeView === 'form' && formDirty) ||
            (activeView === 'text' && dirty)) && (
            <button
              type="button"
              className={styles.btnSecondary}
              onClick={handleReset}
            >
              {activeView === 'form'
                ? '↺ 자동입력으로 되돌리기'
                : '↺ 원본으로 되돌리기'}
            </button>
          )}
        </div>

        <div className={styles.copyHint}>
          ※ 표준 양식은 참고용입니다. 사업장 실정에 맞게 사업주·근로자가 협의하여 확정·서명해 주세요.
          {activeView === 'text' && dirty && (
            <>
              {' '}
              <strong>현재 편집본이 다운로드·복사에 그대로 사용됩니다.</strong>
            </>
          )}
          {activeView === 'form' && (
            <>
              {' '}
              <strong>양식에 입력한 내용 그대로 다운로드·복사·인쇄됩니다.</strong>
            </>
          )}
        </div>
      </div>

      {/* 우하단 노무 가이드 챗봇 — 작성하며 질문 (인쇄 제외) */}
      <div className="noPrint">
        <ChatPanel
          analysis={
            (entry?.ec?.analysisResult as unknown as Record<string, unknown>) ?? null
          }
          docLabel="근로계약서"
          quickPrompts={[
            '이 칸은 어떻게 써야 하나요?',
            '소정근로시간·휴게시간 기준이 뭔가요?',
            '수습기간·기간제 계약 주의점은?',
            '4대보험 가입은 어떻게 표기하나요?',
          ]}
        />
      </div>
    </main>
  );
}
