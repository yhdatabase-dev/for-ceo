'use client';

/**
 * MobileOcrConfirm — 모바일 "추출 내용 확인" 공용 화면 (의심 부분만 카드형).
 *
 * 변경: OCR 전체 텍스트를 보여주지 않고, **판독불가·확인필요 부분만 카드**로
 * 모아 그 부분만 고치게 한다. AI 판단(headerExtra)은 화면 진입 시 자동으로
 * 뜨는 바텀시트로 확인한다.
 *
 *   앱바 · 안내 · (AI 판단 시트 자동 오픈) · [추출/원본이미지] 탭 ·
 *   확인 필요 카운터 · 의심 카드 목록(인라인 수정) · 전체 직접 편집 폴백 · CTA
 *
 * 확인 페이지(근로계약서·취업규칙)가 공유한다.
 * 제출 시 onSubmit(전체 텍스트 복원본) — 부모 페이지가 분석 흐름을 이어받음.
 */

import {
  Fragment,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import styles from './MobileOcrConfirm.module.css';

export interface MobileOcrConfirmProps {
  initialText: string;
  submitting?: boolean;
  /** 수정 최종본 — 줄바꿈·공백을 보존해 복원한 전체 텍스트. */
  onSubmit: (editedText: string) => void;
  onBack: () => void;
  /** 기본값 '이 내용으로 검토 시작'. */
  submitLabel?: string;
  /** 직전 제출 실패 메시지 — CTA 위에 표시 (재시도 안내용, 선택). */
  errorMessage?: string;
  /** AI 1차 분류 확인 — 화면 진입 시 자동으로 뜨는 바텀시트에 담긴다. */
  headerExtra?: ReactNode;
  /** 원본 이미지 URL — 있을 때만 [추출 텍스트]/[원본 이미지] 탭 토글 노출. */
  imageUrl?: string;
}

/* ─────────────────────────────────────────────
 *  단어 단위 의심 휴리스틱 (순수 함수)
 *  실제 신뢰도 점수가 없어 보수적 텍스트 패턴으로만 추정한다.
 * ───────────────────────────────────────────── */

export const SUSPECT_REASON_DATE = '날짜 일부가 비어 있어요';
export const SUSPECT_REASON_JAMO = '글자가 깨져 보일 수 있어요';
export const SUSPECT_REASON_UNREADABLE = '읽지 못한 글자가 있어요';

/**
 * 줄에 "숫자가 빠진 날짜 골격"이 있는지 — '년 / 월 / 일'·'/월/일'·'2025년 월 일' 류.
 */
export function hasEmptyDateSkeleton(line: string): boolean {
  if (/\/\s*[년월일]/.test(line)) return true;
  if (/년\s*\/?\s*월(?=[\s/일]|$)/.test(line)) return true;
  if (/(^|[\s/])월\s*\/?\s*일(?=[\s/.,)]|$)/.test(line)) return true;
  return false;
}

/** 빈 날짜 골격을 이루는 토큰인지 — '2025년'·'년'·'월'·'일'·'/'·'/월/일' 등. */
function isEmptyDateToken(token: string): boolean {
  return /^(\d{0,4}년|[/년월일]+)$/.test(token);
}

/** 'ㄱ.'·'(ㄴ)' 같은 한글 자모 목록 기호 — 깨진 글자로 오인하지 않도록 제외. */
function isJamoListMarker(token: string): boolean {
  return /^[(（]?[ㄱ-ㅎ][)）.．]?$/.test(token);
}

/** 단어 하나의 의심 사유 — 없으면 null. */
export function getTokenSuspicion(token: string, line: string): string | null {
  if (!token.trim()) return null;
  if (/[□�]|\?{2,}|불분명|판독불가/.test(token)) {
    return SUSPECT_REASON_UNREADABLE;
  }
  if (/[ㄱ-ㅎㅏ-ㅣ]/.test(token) && !isJamoListMarker(token)) {
    return SUSPECT_REASON_JAMO;
  }
  if (hasEmptyDateSkeleton(line) && isEmptyDateToken(token)) {
    return SUSPECT_REASON_DATE;
  }
  return null;
}

/* ─────────────────────────────────────────────
 *  텍스트 모델 — 줄 × 세그먼트(단어/공백)
 * ───────────────────────────────────────────── */

interface WordSegment {
  text: string;
  ws: boolean;
  reason: string | null;
  fixed: boolean;
}

/** initialText → 모델. 공백 구분자를 세그먼트로 보존해 무손실 복원을 보장. */
function buildModel(text: string): WordSegment[][] {
  return text.split('\n').map((line) =>
    line
      .split(/(\s+)/)
      .filter((part) => part !== '')
      .map((part) => {
        const ws = /^\s+$/.test(part);
        return {
          text: part,
          ws,
          reason: ws ? null : getTokenSuspicion(part, line),
          fixed: false,
        };
      }),
  );
}

/** 모델 → 전체 텍스트 복원. */
function composeText(model: WordSegment[][]): string {
  return model.map((segs) => segs.map((s) => s.text).join('')).join('\n');
}

/** 편집 textarea 높이를 내용에 맞게 자동 조절. */
function growTextarea(el: HTMLTextAreaElement) {
  el.style.height = 'auto';
  el.style.height = `${el.scrollHeight}px`;
}

function BackIcon() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M15 18l-6-6 6-6" />
    </svg>
  );
}

function InfoIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5" />
      <path d="M12 8h.01" />
    </svg>
  );
}

export default function MobileOcrConfirm({
  initialText,
  submitting = false,
  onSubmit,
  onBack,
  submitLabel = '이 내용으로 검토 시작',
  errorMessage,
  headerExtra,
  imageUrl,
}: MobileOcrConfirmProps) {
  const [model, setModel] = useState<WordSegment[][]>(() =>
    buildModel(initialText),
  );
  // [추출 텍스트] / [원본 이미지] 탭
  const [view, setView] = useState<'text' | 'image'>('text');
  // AI 판단(headerExtra) 바텀시트 — 화면 진입 시 자동으로 열린다.
  const [clsSheetOpen, setClsSheetOpen] = useState(Boolean(headerExtra));
  // 전체 텍스트 직접 편집 폴백
  const [rawMode, setRawMode] = useState(false);
  const [rawDraft, setRawDraft] = useState('');
  const rawDraftRef = useRef('');
  const rawTaRef = useRef<HTMLTextAreaElement | null>(null);

  // initialText 가 마운트 후 바뀌는 경우(스토어 비동기 복원) 동기화.
  const lastInitialRef = useRef(initialText);
  useEffect(() => {
    if (lastInitialRef.current === initialText) return;
    lastInitialRef.current = initialText;
    setModel(buildModel(initialText));
    setRawMode(false);
  }, [initialText]);

  useEffect(() => {
    if (!rawMode) return;
    const el = rawTaRef.current;
    if (el) growTextarea(el);
  }, [rawMode]);

  // 아직 안 고친 의심 단어 수 — 상태줄 카운터
  const suspectCount = useMemo(
    () =>
      model.reduce(
        (n, segs) =>
          n + segs.reduce((m, s) => m + (s.reason && !s.fixed ? 1 : 0), 0),
        0,
      ),
    [model],
  );

  // 의심(판독불가·확인필요) 세그먼트만 카드로 — OCR 전체는 안 보여준다.
  const suspects = useMemo(() => {
    const out: { li: number; si: number }[] = [];
    model.forEach((segs, li) =>
      segs.forEach((seg, si) => {
        if (seg.reason) out.push({ li, si });
      }),
    );
    return out;
  }, [model]);

  // 카드형 인라인 수정 — 세그먼트 텍스트 갱신 / '확인'(수정됨) 마킹
  const setSegText = (li: number, si: number, value: string) =>
    setModel((prev) =>
      prev.map((segs, i) =>
        i === li
          ? segs.map((seg, j) => (j === si ? { ...seg, text: value } : seg))
          : segs,
      ),
    );
  const markSegFixed = (li: number, si: number) =>
    setModel((prev) =>
      prev.map((segs, i) =>
        i === li
          ? segs.map((seg, j) => (j === si ? { ...seg, fixed: true } : seg))
          : segs,
      ),
    );

  // 전체 텍스트 직접 편집 토글 — 닫을 때 의심 휴리스틱을 다시 돌린다
  const toggleRawMode = () => {
    if (submitting) return;
    if (rawMode) {
      setModel(buildModel(rawDraftRef.current));
      setRawMode(false);
    } else {
      const full = composeText(model);
      setRawDraft(full);
      rawDraftRef.current = full;
      setRawMode(true);
    }
  };

  const handleSubmit = () => {
    if (submitting) return;
    onSubmit(rawMode ? rawDraftRef.current : composeText(model));
  };

  const showTabs = Boolean(imageUrl);
  const showImage = showTabs && view === 'image';

  return (
    <div className={styles.root}>
      {/* 앱바 */}
      <header className={styles.appBar}>
        <button
          type="button"
          className={styles.backBtn}
          onClick={onBack}
          aria-label="뒤로 가기"
        >
          <BackIcon />
        </button>
        <h1 className={styles.appBarTitle}>추출된 내용 확인</h1>
      </header>

      {/* 안내 배너 */}
      <div className={styles.banner}>
        <span className={styles.bannerIcon} aria-hidden>
          <InfoIcon />
        </span>
        <p className={styles.bannerText}>
          <strong>확인이 필요한 곳</strong>을 모았어요 — 내용을 확인하고 고쳐
          주세요.
        </p>
      </div>

      {/* AI 판단을 다시 보고 싶을 때 (시트 재오픈) */}
      {headerExtra && !clsSheetOpen && (
        <button
          type="button"
          className={styles.reopenCls}
          onClick={() => setClsSheetOpen(true)}
        >
          ✨ AI 판단 다시 보기
        </button>
      )}

      {/* 탭 토글 — 원본 이미지가 있을 때만 */}
      {showTabs && (
        <div className={styles.tabs} role="tablist" aria-label="보기 전환">
          <button
            type="button"
            role="tab"
            aria-selected={!showImage}
            className={!showImage ? styles.tabActive : styles.tab}
            onClick={() => setView('text')}
          >
            확인할 곳
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={showImage}
            className={showImage ? styles.tabActive : styles.tab}
            onClick={() => setView('image')}
          >
            원본 이미지
          </button>
        </div>
      )}

      {/* 상태줄 — 남은 확인 필요 수 */}
      {!rawMode && !showImage && (
        <p className={styles.statusLine} role="status">
          {suspectCount > 0 ? (
            <>
              <span className={styles.statusWarn} aria-hidden>
                △
              </span>{' '}
              확인이 필요한 곳 <strong>{suspectCount}</strong> 군데
            </>
          ) : (
            <>
              <span className={styles.statusOk} aria-hidden>
                ✓
              </span>{' '}
              확인이 필요한 곳이 없어요
            </>
          )}
        </p>
      )}

      {/* 본문 */}
      <div className={styles.body}>
        {showImage ? (
          /* ── 원본 이미지 모드 ── */
          <div className={styles.imagePane}>
            <p className={styles.imageCaption}>
              원본과 비교하며 ‘확인할 곳’ 탭에서 고쳐 주세요.
            </p>
            <div className={styles.imageScroll}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={imageUrl}
                alt="업로드한 원본 문서"
                className={styles.image}
              />
            </div>
          </div>
        ) : rawMode ? (
          /* ── 전체 텍스트 직접 편집 폴백 ── */
          <div className={styles.rawPane}>
            <textarea
              ref={rawTaRef}
              className={styles.rawEditor}
              value={rawDraft}
              spellCheck={false}
              onChange={(e) => {
                setRawDraft(e.target.value);
                rawDraftRef.current = e.target.value;
                growTextarea(e.target);
              }}
              aria-label="전체 텍스트 직접 편집"
            />
            <button
              type="button"
              className={styles.rawToggle}
              onClick={toggleRawMode}
            >
              ✓ 직접 편집 완료 — 확인 필요한 곳 다시 찾기
            </button>
          </div>
        ) : suspects.length === 0 ? (
          /* ── 확인할 곳 없음 ── */
          <>
            <div className={styles.emptyCard}>
              <span className={styles.emptyCheck} aria-hidden>
                ✓
              </span>
              <p className={styles.emptyText}>
                읽기 어렵거나 비어 있는 곳이 없어요. 바로 검토를 시작하셔도
                됩니다.
              </p>
            </div>
            <button
              type="button"
              className={styles.rawToggle}
              onClick={toggleRawMode}
            >
              ✎ 전체 텍스트 보기·직접 편집
            </button>
          </>
        ) : (
          /* ── 의심(판독불가·확인필요) 부분만 카드로 ── */
          <>
            <div className={styles.cardList}>
              {suspects.map(({ li, si }) => {
                const seg = model[li]?.[si];
                if (!seg) return null;
                return (
                  <div
                    key={`${li}-${si}`}
                    className={seg.fixed ? styles.fixCardDone : styles.fixCard}
                  >
                    <div className={styles.fixCardHead}>
                      <span
                        className={
                          seg.fixed ? styles.fixBadgeDone : styles.fixBadge
                        }
                      >
                        {seg.fixed ? '✓ 수정됨' : '확인 필요'}
                      </span>
                      <span className={styles.fixReason}>{seg.reason}</span>
                    </div>
                    <p className={styles.fixContext}>
                      {model[li].map((s, j) =>
                        j === si ? (
                          <mark key={j} className={styles.fixCtxMark}>
                            {s.text.trim() || '⬚'}
                          </mark>
                        ) : (
                          <Fragment key={j}>{s.text}</Fragment>
                        ),
                      )}
                    </p>
                    <div className={styles.fixRow}>
                      <input
                        className={styles.fixInput}
                        type="text"
                        value={seg.text}
                        spellCheck={false}
                        placeholder="고친 내용 입력"
                        onChange={(e) => setSegText(li, si, e.target.value)}
                        aria-label="고친 내용"
                      />
                      <button
                        type="button"
                        className={styles.fixBtn}
                        onClick={() => markSegFixed(li, si)}
                      >
                        확인
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
            <button
              type="button"
              className={styles.rawToggle}
              onClick={toggleRawMode}
            >
              ✎ 전체 텍스트 보기·직접 편집
            </button>
          </>
        )}
      </div>

      {/* 하단 고정 CTA */}
      <div className={styles.ctaBar}>
        {errorMessage && (
          <p className={styles.error} role="alert">
            {errorMessage}
          </p>
        )}
        <button
          type="button"
          className={styles.cta}
          onClick={handleSubmit}
          disabled={submitting}
        >
          {submitting ? '준비 중…' : submitLabel}
        </button>
        <p className={styles.ctaCaption}>
          수정한 내용을 기준으로 노동법 위반 여부를 검토합니다
        </p>
      </div>

      {/* AI 판단 바텀시트 — 진입 시 자동 오픈 */}
      {headerExtra && clsSheetOpen && (
        <>
          <div
            className={styles.clsScrim}
            onClick={() => setClsSheetOpen(false)}
            aria-hidden
          />
          <div
            className={styles.clsSheet}
            role="dialog"
            aria-modal="true"
            aria-label="AI 판단 확인"
          >
            <div className={styles.clsGrab} />
            <div className={styles.clsBody}>{headerExtra}</div>
            <button
              type="button"
              className={styles.clsDone}
              onClick={() => setClsSheetOpen(false)}
            >
              확인했어요
            </button>
          </div>
        </>
      )}
    </div>
  );
}
