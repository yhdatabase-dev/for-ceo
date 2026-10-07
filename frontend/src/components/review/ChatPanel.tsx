'use client';

import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react';

import { postEcChat } from '@/features/ec/api';
import { ApiCallError } from '@/lib/api/client';
import type { EcChatTurn } from '@/lib/api/types';

import styles from './ChatPanel.module.css';

/**
 * 공용 노동법 챗봇 패널 (SFR-001).
 *
 * 결과 페이지 우하단에 floating FAB 으로 떠 있다가 클릭 시 패널 확장.
 * 백엔드 `/ec/chat` 을 호출하나 `analysis_result` 는 `dict` 로 받아 doc-agnostic —
 * 근로계약서/취업규칙 어디서나 동일 동작.
 *
 * EC 결과 페이지에는 자체 ChatPanel 이 이미 있어 그대로 두고, 본 컴포넌트는
 * WR/WS/SC 결과 페이지의 챗봇 누락을 메우는 용도.
 *
 * 사용 예:
 * ```tsx
 * <ChatPanel
 *   analysis={someAnalysisDict}
 *   focusedItem={currentItemName}
 *   docLabel="취업규칙"
 *   quickPrompts={[...]}
 * />
 * ```
 */

interface ChatPanelProps {
  /** 분석 결과(dict). 백엔드 LLM 에 컨텍스트로 전달. 없어도 동작. */
  analysis?: Record<string, unknown> | null;
  /** 현재 사용자가 보고 있는 항목명 (캐러셀 활성 인덱스의 항목 등). */
  focusedItem?: string;
  /** "근로계약서" / "취업규칙" — 패널 헤더용. */
  docLabel?: string;
  /** 자주 묻는 질문 칩 — 빈 배열이면 기본값. */
  quickPrompts?: string[];
  /**
   * 모바일 검토앱 안에 끼워 넣을 때 true — FAB 를 하단 액션바 위로 띄운다
   * (기본은 화면 우하단). 패널 자체는 동일.
   */
  embedded?: boolean;
  /**
   * true 면 닫힌 상태의 FAB 를 숨긴다(글자 가림 방지) — 예: 항목 상세 시트가
   * 열려 있을 때. 단, 채팅 패널이 열려 있으면 유지한다.
   */
  hidden?: boolean;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

const DEFAULT_QUICK_PROMPTS = [
  '이 항목이 왜 부적절한가요?',
  '주휴수당이 뭔가요?',
  '연차유급휴가는 언제부터 발생하나요?',
  '퇴직금 계산은 어떻게 해요?',
];

/**
 * assistant 응답에서 "관련 법령: ..." 한 줄을 본문과 분리.
 */
function parseAssistantMessage(text: string): { body: string; laws: string[] } {
  if (!text) return { body: '', laws: [] };
  const m = text.match(/(?:^|\n)\s*관련\s*법령\s*[:：]\s*(.+?)\s*$/);
  if (!m) return { body: text.trim(), laws: [] };
  const body = text.replace(m[0], '').trim();
  const laws = splitLawCitations(m[1]);
  return { body, laws };
}

function stripMarkdownChars(s: string): string {
  return s.replace(/\*+|_+/g, '').replace(/\s+/g, ' ').trim();
}

function splitLawCitations(s: string): string[] {
  const cleaned = stripMarkdownChars(s);
  const parts = cleaned
    .split(/[,;／]\s*|\s+\/\s+/)
    .map((t) => stripMarkdownChars(t))
    .filter((t) => t.length > 0);
  const out: string[] = [];
  let currentLaw = '';
  const LAW_HEAD = /^(.+?(?:법률|법))/;
  for (const p of parts) {
    const lm = p.match(LAW_HEAD);
    if (lm) {
      currentLaw = lm[1];
      out.push(p);
    } else if (currentLaw && /^제\d+조/.test(p)) {
      out.push(`${currentLaw} ${p}`);
    } else if (p) {
      out.push(p);
    }
  }
  return out;
}

/** 자동 강조 패턴 — LLM 이 ** 빼먹은 핵심 키워드를 굵게. */
const CHAT_AUTO_EMPHASIZE = new RegExp(
  [
    '근로기준법\\s*제\\d+조(?:\\s*제\\d+항)?(?:\\s*제\\d+호)?',
    '기간제\\s*및\\s*단시간근로자\\s*보호\\s*등에\\s*관한\\s*법률\\s*제\\d+조',
    '최저임금법\\s*제\\d+조(?:\\s*제\\d+항)?',
    '근로자퇴직급여\\s*보장법\\s*제\\d+조',
    '산업재해보상보험법\\s*제\\d+조',
    '고용보험법\\s*제\\d+조',
    '남녀고용평등(?:과\\s*일\\s*·?\\s*가정\\s*양립\\s*지원에\\s*관한\\s*법률)?\\s*제\\d+조',
    '\\d+(?:,\\d{3})+\\s*원',
    '\\d{1,4}\\s*년\\s*\\d{1,2}\\s*월\\s*\\d{1,2}\\s*일',
    '\\d{1,2}\\s*시\\s*\\d{1,2}\\s*분',
    '\\d{1,3}\\s*시간',
    '\\d{1,3}\\s*일',
    '\\d{1,3}\\s*개월',
    '\\d{1,3}\\s*%',
    '5\\s*인\\s*이상',
    '5\\s*인\\s*미만',
    '1\\s*주\\s*\\d{1,3}\\s*시간',
    '위반\\s*가능성(?:이\\s*있어요|이\\s*있습니다|이\\s*있음)?',
    '검토가?\\s*필요(?:해요|합니다|함)?',
    '필수\\s*기재(?:사항)?',
    '서면\\s*명시(?:의무)?',
    '서면\\s*교부(?:\\s*의무)?',
    '미기재',
    '누락(?:되어|되었|된)?\\s*있?',
    '보완(?:이)?\\s*필요(?:해요|합니다)?',
  ]
    .map((p) => `(?:${p})`)
    .join('|'),
  'g',
);

function autoBoldKeywords(text: string, keyPrefix: string): ReactNode[] {
  if (!text) return [];
  const out: ReactNode[] = [];
  const re = new RegExp(CHAT_AUTO_EMPHASIZE.source, CHAT_AUTO_EMPHASIZE.flags);
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      out.push(
        <Fragment key={`${keyPrefix}-t-${last}`}>
          {text.slice(last, m.index)}
        </Fragment>,
      );
    }
    out.push(<strong key={`${keyPrefix}-a-${m.index}`}>{m[0]}</strong>);
    last = m.index + m[0].length;
  }
  if (last < text.length) {
    out.push(
      <Fragment key={`${keyPrefix}-t-${last}`}>{text.slice(last)}</Fragment>,
    );
  }
  return out;
}

function renderMarkdownBold(text: string): ReactNode[] {
  if (!text) return [];
  const out: ReactNode[] = [];
  const re = /\*\*([^*]+)\*\*/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let segIdx = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      const seg = text.slice(last, m.index);
      out.push(
        <Fragment key={`s-${segIdx++}`}>
          {autoBoldKeywords(seg, `s${segIdx}`)}
        </Fragment>,
      );
    }
    out.push(<strong key={`b-${m.index}`}>{m[1]}</strong>);
    last = m.index + m[0].length;
  }
  if (last < text.length) {
    const seg = text.slice(last);
    out.push(
      <Fragment key={`s-${segIdx++}`}>
        {autoBoldKeywords(seg, `s${segIdx}`)}
      </Fragment>,
    );
  }
  return out;
}

/** 법령 칩 — 클릭 시 국가법령정보센터 새 탭. */
function LawChip({ lawName }: { lawName: string }) {
  const cleaned = stripMarkdownChars(lawName);
  if (!cleaned) return null;
  // 검색 URL — 법령명+조항을 그대로 query 로 전달
  const url = `https://www.law.go.kr/LSW/lsSc.do?menuId=1&subMenuId=15&tabMenuId=81&query=${encodeURIComponent(cleaned)}`;
  return (
    <a
      className={styles.lawChip}
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      title="국가법령정보센터에서 보기 — 새 탭"
    >
      {cleaned}
      <span className={styles.lawChipIcon} aria-hidden>↗</span>
    </a>
  );
}

export function ChatAssistantBubble({ content }: { content: string }) {
  const { body, laws } = parseAssistantMessage(content);
  return (
    <div className={styles.chatBubble}>
      <div className={styles.chatBubbleBody}>{renderMarkdownBold(body)}</div>
      {laws.length > 0 && (
        <div className={styles.chatBubbleLaws}>
          <span className={styles.chatBubbleLawsLabel}>관련 법령</span>
          {laws.map((l, i) => (
            <LawChip key={`${l}-${i}`} lawName={l} />
          ))}
        </div>
      )}
    </div>
  );
}

export function ChatPanel({
  analysis,
  focusedItem,
  docLabel = '검토 결과',
  quickPrompts,
  embedded = false,
  hidden = false,
}: ChatPanelProps) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages, pending]);

  const QUICK = quickPrompts && quickPrompts.length > 0 ? quickPrompts : DEFAULT_QUICK_PROMPTS;

  const sendMessage = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || pending) return;
    setError(null);
    const userTurn: ChatMessage = { role: 'user', content: trimmed };
    const nextMessages = [...messages, userTurn];
    setMessages(nextMessages);
    setInput('');
    setPending(true);
    try {
      const history: EcChatTurn[] = nextMessages.slice(0, -1).map((m) => ({
        role: m.role,
        content: m.content,
      }));
      // 백엔드 EcAnalysisResult 시그니처지만 실제로는 dict any → doc-agnostic 동작.
      // TS 통과를 위해 cast.
      const out = await postEcChat(trimmed, {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        analysisResult: (analysis as any) ?? undefined,
        focusedItem,
        history,
      });
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: out.answer },
      ]);
    } catch (e) {
      const msg =
        e instanceof ApiCallError
          ? e.detail
          : e instanceof Error
            ? e.message
            : String(e);
      setError(msg);
    } finally {
      setPending(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void sendMessage(input);
  };

  if (!open) {
    if (hidden) return null;
    return (
      <button
        type="button"
        className={`${styles.chatFab} ${embedded ? styles.chatFabEmbedded : ''}`}
        onClick={() => setOpen(true)}
        aria-label="노무 가이드 챗봇 열기"
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
        >
          <path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 9 9 0 0 1-4-1L3 20l1.5-4.5a8.38 8.38 0 0 1-1-4A8.5 8.5 0 0 1 12 3a8.38 8.38 0 0 1 9 8.5z" />
        </svg>
        <span className={styles.chatFabLabel}>노무 가이드</span>
      </button>
    );
  }

  return (
    <aside className={styles.chatPanel} aria-label="노동법 챗봇">
      <header className={styles.chatHead}>
        <span className={styles.chatHeadTitle}>노동법 도우미</span>
        <span className={styles.chatHeadDoc}>{docLabel}</span>
        {focusedItem && (
          <span className={styles.chatHeadContext} title="현재 본 항목">
            「{focusedItem}」
          </span>
        )}
        <button
          type="button"
          className={styles.chatClose}
          onClick={() => setOpen(false)}
          aria-label="닫기"
        >
          ✕
        </button>
      </header>

      <div className={styles.chatBody} ref={listRef}>
        {messages.length === 0 && (
          <div className={styles.chatEmpty}>
            <p className={styles.chatEmptyTitle}>
              {docLabel} 검토 결과에 대해 무엇이든 물어보세요.
            </p>
            <p className={styles.chatEmptyHint}>
              {focusedItem
                ? `현재 본 항목 「${focusedItem}」 의 분석 결과를 함께 보고 답해 드려요.`
                : '항목별 분석을 보면서 자유롭게 질문해 주세요.'}
            </p>
            <div className={styles.chatQuickRow}>
              {QUICK.map((q) => (
                <button
                  key={q}
                  type="button"
                  className={styles.chatQuickChip}
                  onClick={() => void sendMessage(q)}
                  disabled={pending}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div
            key={i}
            className={`${styles.chatMsg} ${styles[`chatMsg_${m.role}`]}`}
          >
            {m.role === 'assistant' ? (
              <ChatAssistantBubble content={m.content} />
            ) : (
              <div className={styles.chatBubble}>{m.content}</div>
            )}
          </div>
        ))}

        {pending && (
          <div className={`${styles.chatMsg} ${styles.chatMsg_assistant}`}>
            <div className={`${styles.chatBubble} ${styles.chatBubbleTyping}`}>
              <span className={styles.chatTypingDot} />
              <span className={styles.chatTypingDot} />
              <span className={styles.chatTypingDot} />
            </div>
          </div>
        )}

        {error && (
          <div className={styles.chatError}>
            <strong>오류:</strong> {error}
          </div>
        )}
      </div>

      <form className={styles.chatInputRow} onSubmit={handleSubmit}>
        <input
          type="text"
          className={styles.chatInput}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="질문을 입력하세요 (예: 주휴수당이 뭔가요?)"
          disabled={pending}
          autoFocus
        />
        <button
          type="submit"
          className={styles.chatSend}
          disabled={pending || !input.trim()}
        >
          {pending ? '…' : '전송'}
        </button>
      </form>
    </aside>
  );
}

export default ChatPanel;
