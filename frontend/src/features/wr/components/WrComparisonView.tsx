'use client';

/**
 * 취업규칙 신구대조표 — 개정 전 | 개정 후 | 비고(변경사유·관련 법령) 3열 편집 표.
 *
 * 데이터는 검토 결과 findings 에서 **결정적으로** 구성한다(별도 LLM 호출 없음):
 *   - 개정 전(구) = finding.quote (원문 그대로 — 요약 금지)
 *   - 개정 후(신) = finding.suggested(시정 예시) / standard
 *   - 비고        = finding.reason(변경사유) + finding.laws(우리 DB 법령 인용)
 *   - 누락(MISSING)·인용 없음 → 신설로 보고 '개정 전'에 '(현행 규정 없음 — 신설)'
 *
 * 모든 칸은 클릭해 직접 편집 가능. 붙임의 주의사항(삭제 표시·원문 그대로·최신법령·가독성)을
 * 화면 상단 배너로 항상 노출한다. 인쇄(PDF) + Word(.docx) 다운로드.
 */
import { useCallback, useState } from 'react';

import type { Finding } from '@/types/review';
import { downloadWrComparisonDocx } from '@/features/wr/api';
import { ApiCallError } from '@/lib/api/client';

import styles from './WrComparisonView.module.css';

export interface WrCompareRow {
  id: string;
  article: string; // 제24조
  title: string; // 연차유급휴가
  before: string; // 개정 전(구) — 원문 그대로
  after: string; // 개정 후(신)
  remark: string; // 비고 — 변경사유 + 관련 법령
  isNew: boolean; // 현행 규정 없음(신설)
}

/** 변경이 필요한 상태만 신구대조표에 포함 (적정 OK·오류는 제외). */
const CHANGE_STATUSES = new Set(['VIOLATION', 'MISSING', 'WARN', 'AMBIGUOUS']);

function buildRemark(f: Finding): string {
  const parts: string[] = [];
  if (f.reason && f.reason.trim()) parts.push(f.reason.trim());
  const lawNames = (f.laws || []).map((l) => l.name).filter(Boolean);
  if (lawNames.length) parts.push(`관련 법령: ${lawNames.join(', ')}`);
  return parts.join('\n');
}

/** findings → 신구대조표 행 (결정적). */
export function buildWrComparisonRows(findings: Finding[]): WrCompareRow[] {
  return (findings || [])
    .filter((f) => CHANGE_STATUSES.has(f.status))
    .map((f) => {
      const quote = (f.quote || '').trim();
      const isNew = f.status === 'MISSING' || !quote;
      return {
        id: f.id,
        article: f.article || '',
        title: f.articleTitle || f.title || '',
        before: isNew ? '(현행 규정 없음 — 신설)' : quote,
        after: (f.suggested || f.standard || '').trim() || '(개정안을 직접 작성해 주세요)',
        remark: buildRemark(f),
        isNew,
      };
    });
}

const NOTICES: { k: string; v: string }[] = [
  { k: '삭제 조항 표기', v: "삭제되는 조항은 개정 후 칸에 '삭제'라고 적습니다." },
  { k: '요약 금지', v: '개정 전 칸은 원문 그대로 두어야 비교가 정확합니다.' },
  { k: '최신 법령 반영', v: '근로기준법·남녀고용평등법·산업안전보건법 등 관련 법령 문구와 동일하게 작성합니다.' },
  { k: '가독성', v: '문장이 길면 항목(①②③)별로 나누어 정리합니다.' },
];

export default function WrComparisonView({
  findings,
  filename,
}: {
  findings: Finding[];
  filename: string;
}) {
  const [rows, setRows] = useState<WrCompareRow[]>(() => buildWrComparisonRows(findings));
  const [effectiveDate, setEffectiveDate] = useState('');
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const autoGrow = useCallback((el: HTMLTextAreaElement | null) => {
    if (!el) return;
    // 측정은 레이아웃 확정 후(rAF)에 — 표 셀 폭이 잡히기 전에 재면 줄바꿈이
    // 폭주해 scrollHeight 가 비정상적으로 커지는 버그를 막는다.
    requestAnimationFrame(() => {
      el.style.height = 'auto';
      el.style.height = `${Math.min(el.scrollHeight, 1200)}px`;
    });
  }, []);

  const setCell = (id: string, key: 'before' | 'after' | 'remark', v: string) => {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, [key]: v } : r)));
  };
  const setHead = (id: string, key: 'article' | 'title', v: string) => {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, [key]: v } : r)));
  };
  const removeRow = (id: string) => setRows((prev) => prev.filter((r) => r.id !== id));
  const addRow = () =>
    setRows((prev) => [
      ...prev,
      {
        id: `manual-${prev.length}-${prev.reduce((n, r) => n + r.id.length, 0)}`,
        article: '',
        title: '',
        before: '',
        after: '',
        remark: '',
        isNew: false,
      },
    ]);

  const handlePrint = () => window.print();

  const handleDocx = async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      const base = filename.replace(/\.(txt|docx?|pdf|png|jpe?g|hwpx?)$/i, '');
      await downloadWrComparisonDocx({
        rows: rows.map((r) => ({
          article: r.article,
          title: r.title,
          before: r.before,
          after: r.after,
          remark: r.remark,
        })),
        effective_date: effectiveDate,
        filename: `${base}_신구대조표.docx`,
      });
    } catch (err) {
      setDownloadError(
        err instanceof ApiCallError
          ? err.detail
          : err instanceof Error
            ? err.message
            : String(err),
      );
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className={styles.wrap}>
      {/* 신구대조표 인쇄는 A4 가로 — 이 화면이 마운트된 라우트의 인쇄에만 적용
          (전역 @page 는 A4 세로. @page 는 선택자 스코프가 없어 문서 단위로만 걸리므로,
          이 컴포넌트가 렌더된 동안에만 style 태그로 덮어쓴다) */}
      <style>{`@media print { @page { size: A4 landscape; margin: 12mm 14mm; } }`}</style>
      {/* 주의사항 — 붙임 반영, 항상 노출 */}
      <div className={`${styles.notice} noPrint`}>
        <div className={styles.noticeHead}>⚠️ 신구대조표 작성 주의사항</div>
        <ul className={styles.noticeList}>
          {NOTICES.map((n) => (
            <li key={n.k}>
              <strong>{n.k}</strong> — {n.v}
            </li>
          ))}
        </ul>
      </div>

      {/* 종이 카드 — 인쇄 시 그대로 출력 */}
      <div className={styles.paper}>
        <h2 className={styles.docTitle}>취업규칙 신구대조표</h2>
        <div className={styles.metaRow}>
          <span className={styles.metaLabel}>개정 취업규칙 시행일</span>
          <input
            className={styles.metaInput}
            value={effectiveDate}
            onChange={(e) => setEffectiveDate(e.target.value)}
            placeholder="예: 2026.01.01"
            aria-label="개정 시행일"
          />
        </div>

        {rows.length === 0 ? (
          <p className={styles.empty}>
            변경이 필요한 조항이 없어요. (위반·누락·보완 항목이 신구대조표에 표시됩니다.)
          </p>
        ) : (
          <table className={styles.table}>
            <colgroup>
              <col style={{ width: '38%' }} />
              <col style={{ width: '38%' }} />
              <col style={{ width: '24%' }} />
            </colgroup>
            <thead>
              <tr>
                <th>개정 전 (현행)</th>
                <th>개정 후 (개정안)</th>
                <th>비고 (변경사유·관련 법령)</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className={styles.beforeCell}>
                    <div className={styles.cellHead}>
                      <input
                        className={styles.headInput}
                        value={r.article}
                        onChange={(e) => setHead(r.id, 'article', e.target.value)}
                        placeholder="제○조"
                        aria-label="조"
                      />
                      <input
                        className={styles.headInputWide}
                        value={r.title}
                        onChange={(e) => setHead(r.id, 'title', e.target.value)}
                        placeholder="조항 제목"
                        aria-label="조항 제목"
                      />
                    </div>
                    <textarea
                      ref={autoGrow}
                      className={styles.cellArea}
                      value={r.before}
                      onChange={(e) => setCell(r.id, 'before', e.target.value)}
                      onInput={(e) => autoGrow(e.currentTarget)}
                      spellCheck={false}
                    />
                    {/* 인쇄 미러 — textarea 는 보이는 높이만 인쇄되고 페이지를 못 넘어가
                        긴 내용이 잘린다. 인쇄 시에는 div 로 흘려 페이지 분할 허용 */}
                    <div className={`${styles.cellPrint} printOnly`}>{r.before}</div>
                  </td>
                  <td>
                    <textarea
                      ref={autoGrow}
                      className={styles.cellArea}
                      value={r.after}
                      onChange={(e) => setCell(r.id, 'after', e.target.value)}
                      onInput={(e) => autoGrow(e.currentTarget)}
                      spellCheck={false}
                    />
                    <div className={`${styles.cellPrint} printOnly`}>{r.after}</div>
                  </td>
                  <td>
                    <textarea
                      ref={autoGrow}
                      className={`${styles.cellArea} ${styles.remarkArea}`}
                      value={r.remark}
                      onChange={(e) => setCell(r.id, 'remark', e.target.value)}
                      onInput={(e) => autoGrow(e.currentTarget)}
                      spellCheck={false}
                    />
                    <div className={`${styles.cellPrint} ${styles.remarkPrint} printOnly`}>
                      {r.remark}
                    </div>
                    <button
                      type="button"
                      className={`${styles.rowDel} noPrint`}
                      onClick={() => removeRow(r.id)}
                      title="이 행 삭제"
                    >
                      행 삭제
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <button type="button" className={`${styles.addRow} noPrint`} onClick={addRow}>
          + 행 추가
        </button>
      </div>

      <div className={`${styles.actions} noPrint`}>
        <button type="button" className={styles.btnSecondary} onClick={handlePrint}>
          📄 인쇄·PDF
        </button>
        <button
          type="button"
          className={styles.btnPrimary}
          onClick={handleDocx}
          disabled={downloading}
          title="MS Word 호환 .docx"
        >
          {downloading ? '변환 중…' : '⬇ Word 문서 (.docx)'}
        </button>
      </div>
      {downloadError && (
        <div className={`${styles.errorBox} noPrint`}>
          <strong>DOCX 다운로드 실패:</strong> {downloadError}
        </div>
      )}
    </div>
  );
}
