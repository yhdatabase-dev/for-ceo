/**
 * EC(근로계약서) 결과 페이지 공용 로직·타입.
 *
 * << 개정이력(Modification Information) >>
 * 수정일          수정자      수정 내용
 * ----------      ------      ---------------------------
 * 2026.07.08      kimzion77   최초 생성
 * 2026.10.01      이시영      임금명세서·노무제공자 계약서·관리자 기능 삭제
 * 2026.10.07      이시영      화면 경로 /cgr·features 구조 이동, sync API 삭제, 업로드 원본 미저장
 *
 * Author: kimzion77
 * Since: 2026.07.08
 */
/**
 * EC(근로계약서) 결과 페이지 공용 로직·타입.
 *
 * 두 페이지에 바이트 단위로 동일하게 중복돼 있던 순수(스타일 무관) 심볼을
 * 추출한 것 — 여기 수정은 두 페이지에 동시에 반영된다.
 * (styles.* 를 참조하는 컴포넌트·상수는 페이지별 CSS 가 달라 각 페이지에 유지)
 */
import type { ReactNode } from 'react';

import type { EcAnalysisItem, EcAnalysisResult } from '@/lib/api/types';
import { lookupLawExcerpt, type LawExcerpt } from '@/data/lawExcerpts';

export const APPROPRIATENESS_ORDER: Record<string, number> = {
  부적절: 0,
  보완필요: 1,
  적절: 2,
};

export type ItemStatus = '적절' | '보완필요' | '부적절' | 'na';

export interface BoardGroupItem {
  name: string;
  status: ItemStatus;
}

export interface BoardGroup {
  key: string;
  label: string;
  description: string;
  items: BoardGroupItem[];
}

export interface RequirementBoard {
  groups: BoardGroup[];
  stats: RequirementStats;
}

export interface RequirementStats {
  ok: number;
  partial: number;
  bad: number;
  na: number;
  total: number;
}

export interface VerdictBlockProps {
  analysis: EcAnalysisResult;
  verdictStyle: { card: string; text: string };
  stats: RequirementStats;
}

export interface ContractMarker {
  no: number;
  symbol: string;
  text: string;
  tone: 'ok' | 'partial' | 'bad';
  note?: string;
}

export interface ContractPage {
  title: string;
  body: ReactNode;
}

export interface MarkerHit {
  index: number;
  length: number;
  token: string;
  finding: EcAnalysisItem;
  /** 캐러셀 인덱스(1-based) — 좌측 본문 마커와 우측 항목별 상세 카드 번호가 일치. */
  no: number;
}

export interface MetaTag {
  db: string;
  n: string;
}

export interface MetaTagInfo {
  db: string;
  n: string;
}

/**
 * findings 는 캐러셀과 동일한 정렬(부적절→보완필요→적절) 순으로 들어와야 한다.
 * 각 finding 의 배열 인덱스를 그대로 마커 번호로 사용해 캐러셀과 일대일 매칭.
 */
export function buildMarkerHits(
  text: string,
  findings: EcAnalysisItem[],
): MarkerHit[] {
  const used: Array<[number, number]> = [];
  const hits: MarkerHit[] = [];
  findings.forEach((f, idx) => {
    const tokens = extractCandidateTokens(f);
    let best: { index: number; length: number; token: string } | null = null;
    // 우선순위순 (항목명 → 발견내용) — 첫 매칭이 곧 채택. 위치는 우선 아님.
    for (const tok of tokens) {
      const i = text.indexOf(tok);
      if (i < 0) continue;
      const overlaps = used.some(
        ([s, e]) => !(i + tok.length <= s || i >= e),
      );
      if (overlaps) continue;
      best = { index: i, length: tok.length, token: tok };
      break;
    }
    if (best) {
      hits.push({ ...best, finding: f, no: idx + 1 });
      used.push([best.index, best.index + best.length]);
    }
  });
  // 본문 흐름대로 렌더하기 위해 위치순 정렬. 단 번호(no)는 변경 X — 캐러셀과 동기화.
  hits.sort((a, b) => a.index - b.index);
  return hits;
}

/**
 * finding 의 본문 매칭 후보 토큰을 우선순위순으로 추출.
 * 우선순위:
 *   1) 항목명 자체 (예: "임금", "근무 장소") — 가장 의미있는 위치
 *   2) 발견내용 split — placeholder 제외, 2자 이상
 *
 * "임금" finding 이 본문의 "임금" 단어 위치를 잡도록 — 발견내용의 흔한 단어
 * (예: "근로자") 가 앞 위치에 먼저 매칭되어 마커가 엉뚱한 곳으로 가는 것 방지.
 */
export function extractCandidateTokens(item: EcAnalysisItem): string[] {
  const tokens: string[] = [];
  const skip = /^(미기재|없음|판독불가|해당없음|—|-)$/;

  // 1) 항목명 — 공백 유지 / 공백 제거 두 변형
  if (item.항목) {
    const t = item.항목.trim();
    if (t.length >= 2 && !skip.test(t)) {
      tokens.push(t);
      const nospace = t.replace(/\s+/g, '');
      if (nospace !== t && nospace.length >= 2) tokens.push(nospace);
    }
  }

  // 2) 발견내용 split — fallback
  const found = item.발견내용 || '';
  for (const piece of found.split(/[\s,;:·\/\n\r]+/)) {
    const s = piece.trim();
    if (s.length >= 2 && !skip.test(s) && !tokens.includes(s)) {
      tokens.push(s);
    }
  }
  return tokens;
}

export function findingLabel(item: EcAnalysisItem): string {
  const cur = (item.발견내용 || '').trim();
  if (item.적절성 === '부적절' && (!cur || cur === '없음')) return '미기재';
  return item.적절성;
}

export function firstLaw(legal: string): string {
  if (!legal) return '';
  return legal.split(/[,;]+/)[0]?.trim() ?? '';
}

/** db 가 실제 법령(법/법률) 이름인지. */
export function isLawDb(db: string): boolean {
  const cleanDb = db.replace(/^DB_/, '');
  return /(법|법률)$/.test(cleanDb);
}

export function isLawName(cleanDb: string): boolean {
  return /(법|법률)$/.test(cleanDb);
}

/**
 * 법령+제N조 패턴이면 국가법령정보센터의 해당 조문 URL.
 * 매핑 안 되면 null — LawHover 가 anchor 대신 plain span 으로 폴백.
 */
export function lawArticleUrl(m: { db: string; n: string }): string | null {
  const cleanDb = m.db.replace(/^DB_/, '');
  if (!isLawName(cleanDb)) return null;
  const article = normalizeArticleLabel(m.n);
  if (!/^제\d+조/.test(article)) return null;
  const head = article.match(/^제\d+조/)?.[0] ?? article;
  return `https://www.law.go.kr/법령/${encodeURIComponent(cleanDb)}/${encodeURIComponent(head)}`;
}

/**
 * "근로기준법 제17조 제1항 제1호" 또는 "근로기준법제17조제1항" (붙어있는 경우)
 * → lookupLawExcerpt('DB_근로기준법', '제17조 제1항 제1호')
 *
 * 정규식 — lazy `.+?` 로 첫 "법률" 또는 "법" 위치를 잡고, 그 뒤를 조항으로.
 * "법률" 을 alternation 1순위로 둬서 "기간제…법률" 같이 긴 법령명도 잘 잡힘.
 */
export function lookupForLawName(name: string): LawExcerpt {
  const trimmed = name.trim();
  if (!trimmed) {
    return { title: '법령 정보', body: '근거 법령 정보를 찾을 수 없습니다.' };
  }
  // 띄어쓰기 유무 모두 수용 — `\s*` 가 0 또는 N개 공백
  const m = trimmed.match(/^(.+?(?:법률|법))\s*(.*)$/);
  if (m) {
    const lawNm = m[1];
    const article = m[2].trim();
    const db = `DB_${lawNm}`;
    return lookupLawExcerpt(db, article);
  }
  return lookupLawExcerpt(`DB_${trimmed}`, '');
}

/**
 * 조항 번호 정규화.
 *   "17"      → "제17조"
 *   "17조"    → "제17조"
 *   "제17조"   → 그대로
 *   "제17조제1항" → 그대로 (lawArticleUrl 이 첫 "제N조" 만 사용)
 */
export function normalizeArticleLabel(n: string): string {
  const t = n.trim();
  if (!t) return t;
  if (/^\d+$/.test(t)) return `제${t}조`;
  if (/^\d+조(\s|$)/.test(t)) return `제${t}`;
  return t;
}

export function parseMetaTags(input: string): { text: string; metas: MetaTag[] } {
  if (!input) return { text: '', metas: [] };
  const metas: MetaTag[] = [];
  const seen = new Set<string>();
  const re = /<meta\s+db=["']([^"']+)["']\s+n=["']([^"']+)["']\s*\/?\s*>/gi;
  const cleaned = input.replace(re, (_full, db: string, n: string) => {
    const key = `${db}|${n}`;
    if (!seen.has(key)) {
      seen.add(key);
      metas.push({ db, n });
    }
    return '';
  });
  return { text: cleaned.replace(/\s{2,}/g, ' ').trim(), metas };
}

/** finding 의 짧은 한 줄 라벨 (Note 용).
 *  '부적절' 을 무조건 '미기재' 로 표기하던 버그 수정 — 발견내용이 실제로
 *  비었을 때만 '미기재', 값이 있으면(예: 최저임금 미달) '부적절' 로 표기. */
export function shortNoteForFinding(f: EcAnalysisItem): string {
  const found = (f.발견내용 || '').trim();
  const isMissing =
    !found || /^(미기재|없음|누락|미작성|판독불가|해당없음|미상|—|-)$/.test(found);
  if (f.적절성 === '부적절') return isMissing ? `${f.항목} 미기재` : `${f.항목} 부적절`;
  if (f.적절성 === '보완필요') return `${f.항목} 보완 필요`;
  return f.항목;
}

export function statusForItem(
  itemLabel: string,
  results: EcAnalysisItem[],
): ItemStatus {
  const stripped = itemLabel.replace(/\s*\([^)]*\)\s*/g, '').trim();
  const direct = results.find((r) => r.항목 === stripped);
  if (direct) return direct.적절성;
  const head = stripped.split(/[\s·\/]+/)[0];
  if (head) {
    const partial = results.filter((r) => r.항목.startsWith(head));
    if (partial.length > 0) {
      if (partial.some((r) => r.적절성 === '부적절')) return '부적절';
      if (partial.some((r) => r.적절성 === '보완필요')) return '보완필요';
      if (partial.every((r) => r.적절성 === '적절')) return '적절';
    }
  }
  return 'na';
}

export function toneOf(s: EcAnalysisItem['적절성']): 'bad' | 'partial' | 'ok' {
  if (s === '부적절') return 'bad';
  if (s === '보완필요') return 'partial';
  return 'ok';
}
