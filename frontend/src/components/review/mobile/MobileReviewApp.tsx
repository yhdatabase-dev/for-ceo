/**
 * MobileReviewApp — 모바일 검토 결과 공용 컴포넌트.
 *
 * << 개정이력(Modification Information) >>
 * 수정일          수정자      수정 내용
 * ----------      ------      ---------------------------
 * 2026.06.11      kimzion77   최초 생성
 * 2026.10.01      이시영      임금명세서·노무제공자 계약서·관리자 기능 삭제
 * 2026.10.07      이시영      챗봇 기능 삭제
 *
 * Author: kimzion77
 * Since: 2026.06.11
 */
'use client';

/**
 * MobileReviewApp — 모바일 검토 결과 공용 컴포넌트.
 *
 * 디자이너 시안 `근로계약서 검토 앱.html` 의 결과 단계(결과 ↔ 원문 ↔ 내 수정본 +
 * 항목 상세 시트 + 토스트)를 React 상태 기반으로 이식한 것.
 * 결과 페이지(근로계약서·취업규칙)가 공유한다.
 *
 * 원칙:
 *  - 원문 = 읽기전용 증거 / 수정본 = 편집 가능한 별도 산출물 (2레이어 분리)
 *  - 번호 = findings 인덱스+1 — 목록·본문·시트·수정본 어디서나 동일
 *  - drafts/added 변경 시마다 onPersist 콜백 → 부모가 store 에 저장
 */

import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';


import { matchMarkers } from './markers';
import styles from './MobileReviewApp.module.css';

/* ════════════════════════════════════════════════════════
 * 타입
 * ════════════════════════════════════════════════════════ */

export interface MobileFinding {
  /** 안정적 고유 id (항목 or 슬롯ID or finding id). */
  key: string;
  /** 부적절(bad) / 보완필요(warn) — 색·정렬용. */
  tone: 'bad' | 'warn';
  /** 상태 표기 라벨 — 미지정 시 부적절/보완필요. 취업규칙은 누락·위반·주의·
   *  검토필요 등 기존 5-bucket 표현을 그대로 전달. */
  statusLabel?: string;
  /** 항목명. */
  name: string;
  /** 목록 한줄 사유 (예: "최저임금 미달 · 부적절"). */
  reason: string;
  /** 왜 고쳐야 하나요 본문. */
  why?: string;
  /** 근거 법령. */
  law?: string;
  /** 위반 시 벌칙. */
  pen?: string;
  /** 현재 표현 (원문). */
  now: string;
  /** 제안 표현 (기본값). */
  fix: string;
}

export interface MobileReviewAppProps {
  docLabel: string;
  filename: string;
  verdict: { word: string; tone: 'bad' | 'warn' | 'ok'; summary: string };
  /** 위반·보완 항목만 (적절 제외). 번호 = 인덱스+1. */
  findings: MobileFinding[];
  okCount: number;
  /** 있으면 원문(doc) 화면 활성화. */
  extractedText?: string;
  /** 원본 이미지 (선택). */
  imageUrl?: string;
  initialDrafts?: Record<string, string>;
  initialAdded?: Record<string, boolean>;
  /** drafts/added 변경 시마다 호출 — 부모가 store 에 영속화. */
  onPersist?: (
    drafts: Record<string, string>,
    added: Record<string, boolean>,
  ) => void;
  /** 결과 화면에서 ← 시. */
  onBack?: () => void;
  /** 내 수정본에서 "표준 문서 만들기" — 담은 항목을 반영한 표준 문서 생성 흐름
   *  (EC: 표준 근로계약서 생성→다운로드). 없으면 복사 내보내기만 노출. */
  onGenerate?: () => void;
  /** onGenerate 버튼 라벨 (기본 '표준 문서 만들기'). */
  generateLabel?: string;
}

type Screen = 'result' | 'doc' | 'revision';
type Filter = 'all' | 'bad' | 'warn';

/* ════════════════════════════════════════════════════════
 * 모바일 뷰포트 훅 — 결과 페이지들이 isMobile 분기에 사용
 * ════════════════════════════════════════════════════════ */

export function useIsMobileViewport(maxWidthPx = 720): boolean {
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${maxWidthPx}px)`);
    const sync = () => setIsMobile(mq.matches);
    sync();
    mq.addEventListener('change', sync);
    return () => mq.removeEventListener('change', sync);
  }, [maxWidthPx]);
  return isMobile;
}

/* ════════════════════════════════════════════════════════
 * 작은 헬퍼
 * ════════════════════════════════════════════════════════ */

const toneLabel = (t: 'bad' | 'warn') => (t === 'bad' ? '부적절' : '보완필요');

/** 항목 상태 라벨 — statusLabel(취업규칙 누락·위반 등) 우선, 없으면 tone 기본. */
const labelOf = (f: MobileFinding) => f.statusLabel ?? toneLabel(f.tone);

/** 핵심 키워드 자동 강조 — LLM 이 ** 를 빼먹어도 중요 부분을 굵게.
 *  금액·법령 제n조·기간/시각·누락/위반/필수기재 등 결정적 표현. */
const AUTO_BOLD = new RegExp(
  [
    '[가-힣]+법(?:률)?\\s*제\\d+조(?:\\s*제\\d+항)?(?:\\s*제\\d+호)?',
    '시행령\\s*제\\d+조(?:의\\d+)?',
    '\\d{1,3}(?:,\\d{3})+\\s*원',
    '\\d{1,4}\\s*년\\s*\\d{1,2}\\s*월(?:\\s*\\d{1,2}\\s*일)?',
    '\\d{1,2}\\s*시(?:\\s*\\d{1,2}\\s*분)?',
    '\\d{1,3}\\s*시간',
    '\\d{1,3}\\s*일(?:분)?',
    '\\d{1,3}\\s*개월',
    '\\d{1,3}\\s*%',
    '5\\s*인\\s*(?:이상|미만)',
    '필수\\s*기재(?:사항|항목)?',
    '서면\\s*(?:명시|교부)(?:의무)?',
    '지급(?:총액|일)|공제(?:총액|내역)?|실지급액|실수령액',
    '미기재',
    '누락',
    '위반',
    '부적절',
    '보완(?:이)?\\s*필요',
  ]
    .map((p) => `(?:${p})`)
    .join('|'),
  'g',
);

function autoBold(text: string, keyPrefix: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = new RegExp(AUTO_BOLD.source, 'g');
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      out.push(<Fragment key={`${keyPrefix}-t${last}`}>{text.slice(last, m.index)}</Fragment>);
    }
    out.push(<strong key={`${keyPrefix}-b${m.index}`}>{m[0]}</strong>);
    last = m.index + m[0].length;
  }
  if (last < text.length) {
    out.push(<Fragment key={`${keyPrefix}-t${last}`}>{text.slice(last)}</Fragment>);
  }
  return out;
}

/** 마크다운 볼드(**…**) → <strong>, 그 외 구간은 핵심 키워드 자동 강조. */
function renderBold(text: string): ReactNode {
  if (!text) return text;
  const out: ReactNode[] = [];
  const re = /\*\*([^*]+)\*\*/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let seg = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      out.push(<Fragment key={`s${seg++}`}>{autoBold(text.slice(last, m.index), `s${seg}`)}</Fragment>);
    }
    out.push(<strong key={`e${m.index}`}>{m[1]}</strong>);
    last = m.index + m[0].length;
  }
  if (last < text.length) {
    out.push(<Fragment key={`s${seg++}`}>{autoBold(text.slice(last), `s${seg}`)}</Fragment>);
  }
  return out;
}

function BackIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M15 18l-6-6 6-6" />
    </svg>
  );
}

function CheckIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden>
      <path d="M5 12l4 4 10-10" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function VerdictBadgeIcon({ tone }: { tone: 'bad' | 'warn' | 'ok' }) {
  if (tone === 'ok') {
    return (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" aria-hidden>
        <circle cx="12" cy="12" r="9" />
        <path d="M8 12l3 3 5-6" />
      </svg>
    );
  }
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" aria-hidden>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v6M12 17v.01" />
    </svg>
  );
}

/* ════════════════════════════════════════════════════════
 * 본체
 * ════════════════════════════════════════════════════════ */

export default function MobileReviewApp({
  docLabel,
  filename,
  verdict,
  findings,
  okCount,
  extractedText,
  imageUrl,
  initialDrafts,
  initialAdded,
  onPersist,
  onBack,
  onGenerate,
  generateLabel,
}: MobileReviewAppProps) {
  const [screen, setScreen] = useState<Screen>('result');
  const [sheetOpen, setSheetOpen] = useState(false);
  const [curIndex, setCurIndex] = useState(0);
  const [filter, setFilter] = useState<Filter>('all');
  const [docClean, setDocClean] = useState(false);
  const [imgOpen, setImgOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>(() => ({
    ...(initialDrafts ?? {}),
  }));
  const [added, setAdded] = useState<Record<string, boolean>>(() => ({
    ...(initialAdded ?? {}),
  }));

  // ─── 토스트 ───
  const [toastMsg, setToastMsg] = useState('');
  const [toastOn, setToastOn] = useState(false);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const toast = useCallback((m: string) => {
    setToastMsg(m);
    setToastOn(true);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToastOn(false), 1600);
  }, []);
  useEffect(
    () => () => {
      if (toastTimer.current) clearTimeout(toastTimer.current);
    },
    [],
  );

  // ─── 파생 값 ───
  const total = findings.length;
  const badCount = useMemo(
    () => findings.filter((f) => f.tone === 'bad').length,
    [findings],
  );
  const warnCount = total - badCount;
  const addedCount = useMemo(
    () => findings.reduce((n, f) => n + (added[f.key] ? 1 : 0), 0),
    [findings, added],
  );
  const allAdded = total > 0 && addedCount === total;
  const hasDoc = !!(extractedText && extractedText.trim());
  const cur = findings[curIndex] as MobileFinding | undefined;
  const isCurAdded = !!(cur && added[cur.key]);

  const markerHits = useMemo(
    () => (hasDoc ? matchMarkers(extractedText as string, findings) : []),
    [hasDoc, extractedText, findings],
  );

  // ─── 상태 변이 (drafts/added) — 매 변경마다 onPersist ───
  const commit = (
    nextDrafts: Record<string, string>,
    nextAdded: Record<string, boolean>,
  ) => {
    setDrafts(nextDrafts);
    setAdded(nextAdded);
    onPersist?.(nextDrafts, nextAdded);
  };

  const setDraftValue = (key: string, value: string) => {
    commit({ ...drafts, [key]: value }, added);
  };

  const toggleCurAdded = () => {
    if (!cur) return;
    const wasAdded = !!added[cur.key];
    const nextAdded = { ...added, [cur.key]: !wasAdded };
    const nextDrafts =
      !wasAdded && drafts[cur.key] == null
        ? { ...drafts, [cur.key]: cur.fix }
        : drafts;
    commit(nextDrafts, nextAdded);
    toast(wasAdded ? '수정본에서 뺐어요' : '수정본에 담았어요');
  };

  const onBulkFix = () => {
    if (total === 0) return;
    const nextAdded: Record<string, boolean> = { ...added };
    const nextDrafts: Record<string, string> = { ...drafts };
    if (allAdded) {
      for (const f of findings) nextAdded[f.key] = false;
    } else {
      for (const f of findings) {
        nextAdded[f.key] = true;
        if (nextDrafts[f.key] == null) nextDrafts[f.key] = f.fix;
      }
    }
    commit(nextDrafts, nextAdded);
    toast(allAdded ? '전체 담기를 해제했어요' : `${total}건을 모두 수정본에 담았어요`);
  };

  // ─── 시트 열기/닫기/이동 ───
  const openSheet = (idx: number) => {
    setCurIndex(Math.max(0, Math.min(idx, total - 1)));
    setEditing(false);
    setSheetOpen(true);
  };
  const closeSheet = () => {
    setSheetOpen(false);
    setEditing(false);
  };
  const goPrev = () => {
    if (total === 0) return;
    setCurIndex((i) => (i - 1 + total) % total);
    setEditing(false);
  };
  const goNext = () => {
    if (total === 0) return;
    setCurIndex((i) => (i + 1) % total);
    setEditing(false);
  };

  // 수정 모드 진입 시 textarea 포커스
  const fixTaRef = useRef<HTMLTextAreaElement | null>(null);
  useEffect(() => {
    if (editing) fixTaRef.current?.focus();
  }, [editing]);

  // ─── 앱바 ← ───
  const onAppBack = () => {
    if (sheetOpen) {
      closeSheet();
      return;
    }
    if (screen !== 'result') {
      setScreen('result');
      return;
    }
    onBack?.();
  };

  const appTitle =
    screen === 'result' ? '검토 결과' : screen === 'doc' ? '원문 보기' : '내 수정본';

  // ─── 수정본 내보내기 (복사) ───
  const onExport = async () => {
    const items = findings.filter((f) => added[f.key]);
    if (items.length === 0) return;
    const text = items
      .map((f) => `■ ${f.name}\n현재: ${f.now}\n수정: ${drafts[f.key] ?? f.fix}\n`)
      .join('\n');
    let ok = false;
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch {
      // 구형/비보안 컨텍스트 fallback
      try {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        ok = document.execCommand('copy');
        document.body.removeChild(ta);
      } catch {
        ok = false;
      }
    }
    toast(ok ? '수정본을 복사했어요' : '복사에 실패했어요');
  };

  /* ════════════════════════════════════════════
   * 렌더 조각
   * ════════════════════════════════════════════ */

  const numClass = (f: MobileFinding, isAdded: boolean) =>
    `${styles.num} ${
      isAdded ? styles.numOk : f.tone === 'bad' ? styles.numBad : styles.numWarn
    }`;

  // 결과 목록 (필터 적용)
  const listRows = findings
    .map((f, i) => ({ f, i }))
    .filter(({ f }) => filter === 'all' || f.tone === filter);

  // 원문 본문 — 마커 사이사이 일반 텍스트
  const renderDocBody = (): ReactNode => {
    const text = extractedText ?? '';
    if (markerHits.length === 0) return text;
    const out: ReactNode[] = [];
    let pos = 0;
    markerHits.forEach((h) => {
      const f = findings[h.no - 1];
      if (!f) return;
      if (h.index > pos) {
        out.push(<Fragment key={`t${pos}`}>{text.slice(pos, h.index)}</Fragment>);
      }
      const isAdded = !!added[f.key];
      const isFocus = h.no - 1 === curIndex;
      if (!docClean) {
        out.push(
          <button
            key={`vn${h.no}`}
            type="button"
            className={`${numClass(f, isAdded)} ${styles.vnum}`}
            onClick={() => openSheet(h.no - 1)}
            aria-label={`${h.no}번 ${f.name} 상세 보기`}
          >
            {isAdded ? '✓' : h.no}
          </button>,
        );
      }
      out.push(
        <mark
          key={`mk${h.no}`}
          className={[
            styles.vio,
            f.tone === 'bad' ? styles.vioBad : styles.vioWarn,
            isAdded ? styles.vioFixed : '',
            !docClean && isFocus ? styles.vioFocus : '',
            docClean ? styles.vioClean : '',
          ]
            .filter(Boolean)
            .join(' ')}
          onClick={() => {
            if (!docClean) openSheet(h.no - 1);
          }}
        >
          {text.slice(h.index, h.index + h.length)}
        </mark>,
      );
      pos = h.index + h.length;
    });
    if (pos < text.length) {
      out.push(<Fragment key={`t${pos}`}>{text.slice(pos)}</Fragment>);
    }
    return out;
  };

  const verdictCardCls =
    verdict.tone === 'bad'
      ? styles.verdictBad
      : verdict.tone === 'warn'
        ? styles.verdictWarn
        : styles.verdictOk;

  /* ════════════════════════════════════════════
   * JSX
   * ════════════════════════════════════════════ */

  return (
    <div className={styles.root}>
      {/* ─── 앱바 ─── 항목 상세 시트가 열리면 숨겨 화면을 넓게 쓴다 */}
      <div className={`${styles.appbar} ${sheetOpen ? styles.appbarHidden : ''}`}>
        <button
          type="button"
          className={styles.appbarBtn}
          onClick={onAppBack}
          aria-label="뒤로"
        >
          <BackIcon />
        </button>
        <div className={styles.appbarTitle}>{appTitle}</div>
        <div className={styles.appbarSub} title={filename}>
          {filename}
        </div>
      </div>

      {/* ════════ 결과 화면 ════════ */}
      {screen === 'result' && (
        <>
          <div className={styles.body}>
            {/* 종합 판정 카드 */}
            <div className={`${styles.verdict} ${verdictCardCls}`}>
              <div className={styles.vtop}>
                <div className={`${styles.vbadge} ${styles[`vbadge_${verdict.tone}`]}`}>
                  <VerdictBadgeIcon tone={verdict.tone} />
                </div>
                <div>
                  <div className={styles.vlabel}>종합 판정 · {docLabel}</div>
                  <h2 className={`${styles.vword} ${styles[`vword_${verdict.tone}`]}`}>
                    {verdict.word}
                  </h2>
                  <div className={styles.vsub}>
                    {total > 0
                      ? `${total + okCount}개 항목 중 ${total}건 손봐야 해요`
                      : '손봐야 할 항목이 없어요'}
                  </div>
                </div>
              </div>
              {verdict.summary && (
                <div className={styles.vdesc}>{renderBold(verdict.summary)}</div>
              )}
              <div className={styles.vstats}>
                <div className={styles.vstat}>
                  <div className={`${styles.vstatV} ${styles.vstatVBad}`}>{badCount}</div>
                  <div className={styles.vstatL}>부적절</div>
                </div>
                <div className={styles.vstat}>
                  <div className={`${styles.vstatV} ${styles.vstatVWarn}`}>{warnCount}</div>
                  <div className={styles.vstatL}>보완필요</div>
                </div>
                <div className={styles.vstat}>
                  <div className={`${styles.vstatV} ${styles.vstatVOk}`}>{okCount}</div>
                  <div className={styles.vstatL}>적절</div>
                </div>
              </div>
            </div>

            {total > 0 && (
              <>
                {/* 먼저 고쳐야 할 항목 + 일괄 담기 */}
                <div className={styles.seccap}>
                  먼저 고쳐야 할 항목
                  <button
                    type="button"
                    className={`${styles.bulkfix} ${allAdded ? styles.bulkfixDone : ''}`}
                    onClick={onBulkFix}
                  >
                    {allAdded ? (
                      '전체 담음 · 해제'
                    ) : (
                      <>
                        <CheckIcon size={13} /> 제안 일괄 담기
                      </>
                    )}
                  </button>
                </div>

                {/* 필터 */}
                <div className={styles.filt}>
                  <button
                    type="button"
                    className={`${styles.filtBtn} ${filter === 'all' ? styles.filtOn : ''}`}
                    onClick={() => setFilter('all')}
                  >
                    전체 {total}
                  </button>
                  <button
                    type="button"
                    className={`${styles.filtBtn} ${filter === 'bad' ? styles.filtOn : ''}`}
                    onClick={() => setFilter('bad')}
                  >
                    부적절 {badCount}
                  </button>
                  <button
                    type="button"
                    className={`${styles.filtBtn} ${filter === 'warn' ? styles.filtOn : ''}`}
                    onClick={() => setFilter('warn')}
                  >
                    보완 {warnCount}
                  </button>
                </div>

                {/* 위반 목록 */}
                <div className={styles.vlist}>
                  {listRows.map(({ f, i }) => {
                    const isAdded = !!added[f.key];
                    return (
                      <button
                        key={f.key}
                        type="button"
                        className={`${styles.vitem} ${isAdded ? styles.vitemFixed : ''}`}
                        onClick={() => openSheet(i)}
                      >
                        <span className={`${numClass(f, isAdded)} ${styles.vitemNum}`}>
                          {isAdded ? '✓' : i + 1}
                        </span>
                        <span className={styles.vitemTx}>
                          <span className={`${styles.vitemNm} ${isAdded ? styles.vitemNmFixed : ''}`}>
                            {f.name}
                          </span>
                          <span
                            className={`${styles.vitemKd} ${
                              isAdded
                                ? styles.vitemKdOk
                                : f.tone === 'bad'
                                  ? styles.vitemKdBad
                                  : styles.vitemKdWarn
                            }`}
                          >
                            {isAdded ? '수정본에 담음' : f.reason}
                          </span>
                        </span>
                        <span
                          className={`${styles.vitemSt} ${
                            isAdded
                              ? styles.vitemStOk
                              : f.tone === 'bad'
                                ? styles.vitemStBad
                                : styles.vitemStWarn
                          }`}
                        >
                          {isAdded ? '완료' : labelOf(f)}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </>
            )}
            <div className={styles.fabSpacer} />
          </div>

          {/* 하단 FAB */}
          <div className={styles.fab}>
            {hasDoc && (
              <button
                type="button"
                className={`${styles.btn} ${styles.btnGhost}`}
                onClick={() => setScreen('doc')}
              >
                원문에서 보기
              </button>
            )}
            <button
              type="button"
              className={`${styles.btn} ${styles.btnPrimary}`}
              onClick={() => setScreen('revision')}
            >
              수정본 만들기 <span className={styles.badgeCount}>{addedCount}</span>
            </button>
          </div>
        </>
      )}

      {/* ════════ 원문 화면 ════════ */}
      {screen === 'doc' && (
        <>
          <div className={styles.docbar}>
            <button
              type="button"
              className={`${styles.docbarBtn} ${!docClean ? styles.docbarOn : ''}`}
              onClick={() => setDocClean(false)}
            >
              위반 표시
            </button>
            <button
              type="button"
              className={`${styles.docbarBtn} ${docClean ? styles.docbarOn : ''}`}
              onClick={() => setDocClean(true)}
            >
              원문만
            </button>
          </div>
          <div className={styles.body}>
            {imageUrl && (
              <div className={styles.imgBlock}>
                <button
                  type="button"
                  className={styles.imgToggle}
                  onClick={() => setImgOpen((v) => !v)}
                >
                  {imgOpen ? '원본 이미지 접기 ▴' : '원본 이미지 보기 ▾'}
                </button>
                {imgOpen && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={imageUrl} alt={filename} className={styles.docImg} />
                )}
              </div>
            )}
            <div className={styles.doc}>{renderDocBody()}</div>
            <div className={styles.fabSpacer} />
          </div>
          {cur && (
            <button
              type="button"
              className={styles.minibar}
              onClick={() => openSheet(curIndex)}
            >
              <span className={`${numClass(cur, isCurAdded)} ${styles.minibarNum}`}>
                {isCurAdded ? '✓' : curIndex + 1}
              </span>
              <span className={styles.minibarT}>
                {cur.name} {isCurAdded ? '완료' : labelOf(cur)}
              </span>
              <span className={styles.minibarNav}>탭하여 상세 ›</span>
            </button>
          )}
        </>
      )}

      {/* ════════ 내 수정본 화면 ════════ */}
      {screen === 'revision' && (
        <>
          <div className={styles.body}>
            {addedCount === 0 ? (
              <div className={styles.empty}>
                <div className={styles.emptyIcon}>
                  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
                    <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
                    <path d="M14 3v6h6" />
                  </svg>
                </div>
                <p>
                  아직 담은 항목이 없어요.
                  <br />
                  검토 결과에서 고칠 항목의
                  <br />
                  &ldquo;수정본에 담기&rdquo;를 눌러보세요.
                </p>
              </div>
            ) : (
              <>
                <div className={styles.revIntro}>
                  <h3>✓ {addedCount}개 항목을 다듬었어요</h3>
                  <p>
                    원문은 그대로 두고, 아래 내용으로 보완한 <b>새 문서</b>를 만들 수
                    있어요. 사업장 상황에 맞게 한 번 더 확인해 주세요.
                  </p>
                </div>
                <div className={styles.revList}>
                  {findings.map((f, i) => {
                    if (!added[f.key]) return null;
                    return (
                      <button
                        key={f.key}
                        type="button"
                        className={styles.revCard}
                        onClick={() => {
                          setScreen('result');
                          openSheet(i);
                        }}
                      >
                        <span className={styles.revHead}>
                          <span className={`${numClass(f, false)} ${styles.revNum}`}>
                            {i + 1}
                          </span>
                          <span className={styles.revNm}>{f.name}</span>
                          <span
                            className={`${styles.chip} ${
                              f.tone === 'bad' ? styles.chipBad : styles.chipWarn
                            } ${styles.revChip}`}
                          >
                            {labelOf(f)}
                          </span>
                        </span>
                        <span className={styles.revFrom}>{f.now}</span>
                        <span className={styles.revTo}>{drafts[f.key] ?? f.fix}</span>
                      </button>
                    );
                  })}
                </div>
              </>
            )}
            <div className={styles.fabSpacer} />
          </div>
          {addedCount > 0 && (
            <div className={styles.fab}>
              {onGenerate ? (
                <>
                  <button
                    type="button"
                    className={`${styles.btn} ${styles.btnGhost}`}
                    onClick={onExport}
                  >
                    복사
                  </button>
                  <button
                    type="button"
                    className={`${styles.btn} ${styles.btnPrimary}`}
                    onClick={onGenerate}
                  >
                    {generateLabel ?? '표준 문서 만들기'}
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className={`${styles.btn} ${styles.btnPrimary}`}
                  onClick={onExport}
                >
                  수정본 내보내기
                </button>
              )}
            </div>
          )}
        </>
      )}

      {/* ════════ 항목 상세 시트 (모든 화면 공통 오버레이) ════════ */}
      <div
        className={`${styles.scrim} ${sheetOpen ? styles.scrimOn : ''}`}
        onClick={closeSheet}
        aria-hidden
      />
      <div
        className={`${styles.sheet} ${sheetOpen ? styles.sheetOn : ''}`}
        role="dialog"
        aria-modal={sheetOpen}
        aria-label="항목 상세"
      >
        {cur && (
          <>
            <div className={styles.grab} />
            <div className={styles.shead}>
              <span className={`${numClass(cur, false)} ${styles.sheadNum}`}>
                {curIndex + 1}
              </span>
              <span className={styles.sheadNm}>{cur.name}</span>
              <span
                className={`${styles.chip} ${
                  cur.tone === 'bad' ? styles.chipBad : styles.chipWarn
                }`}
              >
                {labelOf(cur)}
              </span>
              <span className={styles.sheadPg}>
                {String(curIndex + 1).padStart(2, '0')}/{total}
              </span>
            </div>
            <div className={styles.sbody}>
              {cur.why && (
                <>
                  <div className={styles.secT}>왜 고쳐야 하나요?</div>
                  <div className={styles.why}>{renderBold(cur.why)}</div>
                </>
              )}
              {cur.law && (
                <div className={styles.lawrow}>
                  <span className={styles.lawrowT}>⚖ {cur.law}</span>
                  {cur.pen && <span className={styles.lawrowPen}>위반 시 {cur.pen}</span>}
                </div>
              )}
              <div className={styles.cmp}>
                <div className={`${styles.secT} ${styles.secTGap}`}>현재 {docLabel}</div>
                <div className={styles.nowBox}>
                  <div className={styles.nowVal}>{cur.now}</div>
                </div>
                <div className={styles.arrow}>↓</div>
                <div className={styles.secT}>
                  이렇게 고쳐보세요 · <span className={styles.secTOk}>직접 수정 가능</span>
                </div>
                <div className={styles.fixbox}>
                  <div className={styles.fixboxHead}>
                    ✓ 제안 문구
                    <button
                      type="button"
                      className={`${styles.fixboxEd} ${editing ? styles.fixboxEdDone : ''}`}
                      onClick={() => {
                        if (editing) {
                          // 완료 — onChange 로 이미 draft 저장됨, 읽기전용 복귀만
                          setEditing(false);
                        } else {
                          setEditing(true);
                        }
                      }}
                    >
                      {editing ? '완료' : '수정'}
                    </button>
                  </div>
                  <textarea
                    ref={fixTaRef}
                    className={styles.fixboxTa}
                    value={drafts[cur.key] ?? cur.fix}
                    readOnly={!editing}
                    onChange={(e) => setDraftValue(cur.key, e.target.value)}
                    rows={3}
                  />
                </div>
                <div className={styles.editnote}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                    <circle cx="12" cy="12" r="9" />
                    <path d="M12 11v5M12 8v.01" />
                  </svg>
                  <span>
                    원문은 그대로 보관돼요. 다듬은 문구는 <b>내 수정본</b>에만 담깁니다.
                  </span>
                </div>
              </div>
            </div>
            <div className={styles.sfoot}>
              <button
                type="button"
                className={styles.arrowBtn}
                onClick={goPrev}
                aria-label="이전 항목"
              >
                ‹
              </button>
              <button
                type="button"
                className={`${styles.sfootPrim} ${isCurAdded ? styles.sfootPrimAdded : ''}`}
                onClick={toggleCurAdded}
              >
                {isCurAdded ? (
                  '✓ 담음 · 빼기'
                ) : (
                  <>
                    <PlusIcon /> 수정본에 담기
                  </>
                )}
              </button>
              <button
                type="button"
                className={styles.arrowBtn}
                onClick={goNext}
                aria-label="다음 항목"
              >
                ›
              </button>
            </div>
          </>
        )}
      </div>

      {/* ════════ 토스트 ════════ */}
      <div className={`${styles.toast} ${toastOn ? styles.toastOn : ''}`} role="status">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#7CE0AC" strokeWidth="2.4" aria-hidden>
          <path d="M5 12l4 4 10-10" />
        </svg>
        {toastMsg}
      </div>

    </div>
  );
}
