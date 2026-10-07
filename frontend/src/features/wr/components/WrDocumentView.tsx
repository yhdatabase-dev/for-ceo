'use client';

/**
 * 취업규칙 수정본 — 종이 문서 뷰.
 *
 * generatedText 의 【수정】…【/수정】 마커를 파싱해 A4 종이 카드 위에
 * 조·항 단락(줄) 단위로 렌더한다.
 *
 *   - 마커 구간: 형광펜(초록) 하이라이트 + 줄 끝 '수정됨' 칩
 *   - 줄 클릭: 인라인 textarea 로 직접 편집 → 저장 시 '✎ 편집됨' 배지 + 줄 되돌리기
 *   - 마커가 전혀 없는 텍스트(구 캐시 등)도 일반 문서로 깨지지 않고 렌더
 *
 * 파서 엣지케이스 (tokenizeWrMarkers):
 *   - 중첩 【수정】   → 토큰만 제거하고 열린 구간 유지
 *   - 고아 【/수정】  → 토큰만 제거하고 일반 텍스트 취급
 *   - 미닫힘 【수정】 → 다음 닫힘 또는 텍스트 끝까지 수정 구간
 *   - 줄에 걸친 구간  → 줄마다 마커 균형을 맞춰 정규화 (라운드트립 보존)
 */

import { useEffect, useRef, useState } from 'react';

import styles from './WrDocumentView.module.css';

const OPEN = '【수정】';
const CLOSE = '【/수정】';

export interface WrSegment {
  text: string;
  changed: boolean;
}

/** 마커 제거 — 복사·다운로드(.txt/.docx)·인쇄용 순수 본문. 마커 없으면 no-op. */
export function stripWrMarkers(text: string): string {
  return text.split(OPEN).join('').split(CLOSE).join('');
}

/** 전역 토크나이즈 — 마커 엣지케이스를 모두 흡수한 세그먼트 배열. */
export function tokenizeWrMarkers(text: string): WrSegment[] {
  const segs: WrSegment[] = [];
  let changed = false;
  for (const part of text.split(/(【\/?수정】)/)) {
    if (part === OPEN) {
      changed = true; // 이미 열려 있으면(중첩) 그대로 유지
      continue;
    }
    if (part === CLOSE) {
      changed = false; // 고아 닫힘이면 no-op
      continue;
    }
    if (!part) continue;
    const last = segs[segs.length - 1];
    if (last && last.changed === changed) {
      last.text += part;
    } else {
      segs.push({ text: part, changed });
    }
  }
  return segs;
}

/** 수정 구간 개수 — 공백·줄바꿈만으로 이어진 인접 구간은 1곳으로 합산. */
export function countWrChanges(text: string): number {
  const segs = tokenizeWrMarkers(text);
  let count = 0;
  let prevIdx = -1;
  for (let i = 0; i < segs.length; i += 1) {
    if (!segs[i].changed) continue;
    if (prevIdx >= 0) {
      const between = segs
        .slice(prevIdx + 1, i)
        .map((s) => s.text)
        .join('');
      if (between.trim() === '') {
        // 줄바꿈·공백만 사이에 둔 구간 — 같은 1곳으로 본다
        prevIdx = i;
        continue;
      }
    }
    count += 1;
    prevIdx = i;
  }
  return count;
}

/** 줄 단위 원시 텍스트 배열 — 줄에 걸친 구간은 줄마다 마커 균형을 맞춰 정규화. */
function splitIntoLineRaws(text: string): string[] {
  const segs = tokenizeWrMarkers(text);
  const lines: WrSegment[][] = [[]];
  for (const seg of segs) {
    const parts = seg.text.split('\n');
    parts.forEach((p, idx) => {
      if (idx > 0) lines.push([]);
      if (p) lines[lines.length - 1].push({ text: p, changed: seg.changed });
    });
  }
  return lines.map((spans) =>
    spans.map((s) => (s.changed ? OPEN + s.text + CLOSE : s.text)).join(''),
  );
}

interface LineState {
  id: number;
  /** 현재 줄의 원시 텍스트 (마커 포함, 줄 안에서 균형). */
  raw: string;
  /** 외부 갱신 시점의 원시 텍스트 — 줄 단위 되돌리기용. */
  originalRaw: string;
  /** 사용자가 이 줄을 직접 편집했는지. */
  edited: boolean;
}

interface WrDocumentViewProps {
  /** 마커 포함 수정본 전문 (canonical). */
  text: string;
  /** 줄 편집·되돌리기 반영 후 마커 포함 전문 — 부모 draft 와 동기화. */
  onTextChange: (next: string) => void;
}

export default function WrDocumentView({
  text,
  onTextChange,
}: WrDocumentViewProps) {
  // 주의: 모든 훅은 조기 return 보다 위 (hook-order 사고 방지).
  const [lines, setLines] = useState<LineState[]>([]);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editValue, setEditValue] = useState('');
  const lastEmittedRef = useRef<string | null>(null);
  const idSeqRef = useRef(0);
  const editAreaRef = useRef<HTMLTextAreaElement | null>(null);

  // 외부에서 text 가 바뀌면(전체 되돌리기·텍스트 보기 편집) 줄 상태 재구성.
  // 자신이 emit 한 변경은 건너뜀 — 줄별 편집 플래그 유지.
  useEffect(() => {
    if (text === lastEmittedRef.current) return;
    lastEmittedRef.current = text;
    const raws = splitIntoLineRaws(text);
    setLines(
      raws.map((raw) => ({
        id: (idSeqRef.current += 1),
        raw,
        originalRaw: raw,
        edited: false,
      })),
    );
    setEditingId(null);
  }, [text]);

  // 편집 textarea 오토포커스 + 내용 높이에 맞춤
  useEffect(() => {
    const el = editAreaRef.current;
    if (!el) return;
    el.focus();
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [editingId]);

  const emit = (next: LineState[]) => {
    setLines(next);
    const joined = next.map((l) => l.raw).join('\n');
    lastEmittedRef.current = joined;
    onTextChange(joined);
  };

  const startEdit = (line: LineState) => {
    if (editingId === line.id) return;
    setEditingId(line.id);
    setEditValue(stripWrMarkers(line.raw));
  };

  const cancelEdit = () => setEditingId(null);

  const saveEdit = (line: LineState) => {
    // 원문과 같게 고치면 마커·상태 원복, 다르면 편집본(마커 없음) 채택
    const restored = editValue === stripWrMarkers(line.originalRaw);
    const next = lines.map((l) =>
      l.id === line.id
        ? { ...l, raw: restored ? line.originalRaw : editValue, edited: !restored }
        : l,
    );
    setEditingId(null);
    emit(next);
  };

  const revertLine = (line: LineState) => {
    const next = lines.map((l) =>
      l.id === line.id ? { ...l, raw: l.originalRaw, edited: false } : l,
    );
    if (editingId === line.id) setEditingId(null);
    emit(next);
  };

  return (
    <div className={styles.paper}>
      {lines.map((line) => {
        // ── 편집 중인 줄 — 인라인 textarea
        if (editingId === line.id) {
          return (
            <div key={line.id} className={styles.editWrap}>
              <textarea
                ref={editAreaRef}
                className={styles.editArea}
                value={editValue}
                spellCheck={false}
                onChange={(e) => {
                  setEditValue(e.target.value);
                  e.target.style.height = 'auto';
                  e.target.style.height = `${e.target.scrollHeight}px`;
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') cancelEdit();
                  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                    saveEdit(line);
                  }
                }}
              />
              <div className={styles.editActions}>
                <span className={styles.editHint}>
                  Esc 취소 · Ctrl+Enter 저장
                </span>
                <button
                  type="button"
                  className={styles.btnCancel}
                  onClick={cancelEdit}
                >
                  취소
                </button>
                <button
                  type="button"
                  className={styles.btnSave}
                  onClick={() => saveEdit(line)}
                >
                  저장
                </button>
              </div>
            </div>
          );
        }

        // ── 빈 줄 — 단락 간격 (편집 대상 아님)
        if (line.raw === '') {
          return <div key={line.id} className={styles.blank} aria-hidden />;
        }

        const spans = tokenizeWrMarkers(line.raw);
        const lineChanged = spans.some((s) => s.changed);
        const cls = [
          styles.line,
          lineChanged ? styles.lineChanged : '',
          line.edited ? styles.lineEdited : '',
        ]
          .filter(Boolean)
          .join(' ');

        return (
          <div
            key={line.id}
            className={cls}
            role="button"
            tabIndex={0}
            title="클릭해서 직접 편집"
            onClick={() => startEdit(line)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                startEdit(line);
              }
            }}
          >
            {spans.map((s, i) =>
              s.changed ? (
                <mark key={i} className={styles.hl}>
                  {s.text}
                </mark>
              ) : (
                <span key={i}>{s.text}</span>
              ),
            )}
            {lineChanged && !line.edited && (
              <span className={`${styles.chip} ${styles.chipFix}`}>수정됨</span>
            )}
            {line.edited && (
              <>
                <span className={`${styles.chip} ${styles.chipEdited}`}>
                  ✎ 편집됨
                </span>
                <button
                  type="button"
                  className={styles.revertBtn}
                  title="이 줄을 생성된 수정본으로 되돌리기"
                  onClick={(e) => {
                    e.stopPropagation();
                    revertLine(line);
                  }}
                >
                  ↺ 되돌리기
                </button>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}
