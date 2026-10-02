"""임베딩 기반 선택 조 디스플레이.

기존 LLM 호출 (~25s, 52건) 을 임베딩 1회 호출 + 코사인 유사도로 대체 (~3s).
사업장 본문을 paragraph 단위로 split 하여 임베딩 → 마스터 D열 임베딩과 매칭.
"""
from __future__ import annotations

import re
import time

from app.integrations.llm.embedding import Embedder, cosine
from app.repositories.wr.master import MasterDB
from app.schemas.wr.values import OptionalDisplay


_SIMILARITY_THRESHOLD = 0.5  # 코사인 ≥ 0.5 면 "관련 있음" 으로 판정
_MAX_CHUNK_LEN = 400         # paragraph 너무 길면 잘라서 임베딩 입력
_MIN_CHUNK_LEN = 20          # 너무 짧은 chunk 는 제외


def _split_doc_chunks(text: str) -> list[str]:
    """사업장 본문을 paragraph 단위로 분할.

    제N조/【제목】/빈 줄 으로 분리 후, _MAX_CHUNK_LEN 초과 시 다시 자름.
    """
    # 빈 줄 + 제목 라인으로 1차 분리
    paragraphs = re.split(r"\n\s*\n|\n(?=【)|\n(?=제\s*\d+\s*조)", text)
    chunks: list[str] = []
    for p in paragraphs:
        p = p.strip()
        if len(p) < _MIN_CHUNK_LEN:
            continue
        if len(p) <= _MAX_CHUNK_LEN:
            chunks.append(p)
        else:
            # 너무 길면 문장 단위로 자르기
            sents = re.split(r"(?<=[.。])\s+|\n", p)
            buf = ""
            for s in sents:
                if len(buf) + len(s) > _MAX_CHUNK_LEN and buf:
                    chunks.append(buf.strip())
                    buf = s
                else:
                    buf = buf + " " + s if buf else s
            if buf.strip():
                chunks.append(buf.strip())
    return chunks


def build_optional_displays_emb(
    document_text: str,
    db: MasterDB,
    *,
    excluded_articles: set[int] | None = None,
) -> list[OptionalDisplay]:
    """임베딩 1회 호출로 모든 선택 조의 사업장 인용 + 존재여부 판정."""
    excluded = excluded_articles or set()
    targets: list[tuple[int, str, str]] = []  # (article, title, master_text)
    for n in db.all_articles():
        if n in excluded:
            continue
        if db.is_required(n):
            continue
        title = db.title(n)
        body = db.body(n) or title
        # 마스터 비교 텍스트: 제목 + 본문 일부 (조 제목이 신호로 가장 강함)
        master_text = f"{title}. {body[:300]}"
        targets.append((n, title, master_text))

    if not targets:
        return []

    # 사업장 chunk 분할
    chunks = _split_doc_chunks(document_text)
    if not chunks:
        # 사업장 본문 너무 짧음 — 전부 미존재로 처리
        return [
            OptionalDisplay(
                article=n,
                title=title,
                scope=str(db.article(n).get("scope") or "선택"),
                master_body=db.body(n),
                master_guide=db._cell(n, "guide"),
                master_note=db.note(n),
                user_quote=None,
                user_present=False,
            )
            for n, title, _ in targets
        ]

    # 임베딩 일괄 호출 (마스터 N + 사업장 M)
    emb = Embedder()
    inputs = [m for _, _, m in targets] + chunks
    t0 = time.time()
    vecs = emb.embed(inputs)
    n_targets = len(targets)
    master_vecs = vecs[:n_targets]
    chunk_vecs = vecs[n_targets:]

    # 각 마스터 → 가장 유사한 사업장 chunk
    out: list[OptionalDisplay] = []
    for (n, title, _), mv in zip(targets, master_vecs):
        best_idx = -1
        best_sim = -1.0
        for i, cv in enumerate(chunk_vecs):
            s = cosine(mv, cv)
            if s > best_sim:
                best_sim = s
                best_idx = i
        present = best_sim >= _SIMILARITY_THRESHOLD
        quote = chunks[best_idx][:400] if present and best_idx >= 0 else None
        out.append(
            OptionalDisplay(
                article=n,
                title=title,
                scope=str(db.article(n).get("scope") or "선택"),
                master_body=db.body(n),
                master_guide=db._cell(n, "guide"),
                master_note=db.note(n),
                user_quote=quote,
                user_present=present,
            )
        )
    return out
