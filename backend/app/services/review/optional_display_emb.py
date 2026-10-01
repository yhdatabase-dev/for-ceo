"""임베딩 기반 선택 조 디스플레이 (기본 채택).

===============================================================================
원본 이관
===============================================================================
원본: `cgr/optional_display_emb.py` → v2 로 이관.

변경점
- `cgr.master_db.MasterDB` → **시그니처를 `articles: list[OptionalArticleSpec]`**
  (`optional_display.py` 와 동일 인터페이스)
- `cgr.embedding` → `app.integrations.llm.embedding`
- `cgr.models.OptionalDisplay` → `OptionalDisplayVO`
- 임계값·chunk 정책·필터 규칙은 원본과 100% 동일

성능
- 기존 LLM 호출 (~25s, 52건) 을 임베딩 1회 호출 + 코사인 유사도로 대체 (~3s).
- 사업장 본문 paragraph 단위 split → 마스터 (title+body 앞 300자) 와 코사인 max.
"""
from __future__ import annotations

import re

from app.integrations.llm.embedding import Embedder, cosine
from app.schemas.review.values import OptionalDisplayVO
from app.services.review.optional_display import OptionalArticleSpec

_SIMILARITY_THRESHOLD = 0.5   # 코사인 ≥ 0.5 면 "관련 있음" 판정
_MAX_CHUNK_LEN = 400
_MIN_CHUNK_LEN = 20


def _split_doc_chunks(text: str) -> list[str]:
    paragraphs = re.split(r"\n\s*\n|\n(?=【)|\n(?=제\s*\d+\s*조)", text)
    chunks: list[str] = []
    for p in paragraphs:
        p = p.strip()
        if len(p) < _MIN_CHUNK_LEN:
            continue
        if len(p) <= _MAX_CHUNK_LEN:
            chunks.append(p)
        else:
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
    articles: list[OptionalArticleSpec],
    *,
    excluded_articles: set[int] | None = None,
) -> list[OptionalDisplayVO]:
    """임베딩 1회 호출로 모든 선택 조의 사업장 인용 + 존재여부 판정."""
    excluded = excluded_articles or set()
    targets: list[tuple[int, str, str]] = []  # (article, title, master_text)
    meta_by_no: dict[int, OptionalArticleSpec] = {}
    for a in articles:
        n = a["article"]
        if n in excluded:
            continue
        if a.get("required"):
            continue
        title = a.get("title", "")
        body = a.get("body") or title
        master_text = f"{title}. {body[:300]}"
        targets.append((n, title, master_text))
        meta_by_no[n] = a

    if not targets:
        return []

    chunks = _split_doc_chunks(document_text)
    if not chunks:
        # 사업장 본문 너무 짧음 — 전부 미존재로 처리
        return [
            _make_display(n, title, meta_by_no[n], quote=None, present=False)
            for n, title, _ in targets
        ]

    emb = Embedder()
    inputs = [m for _, _, m in targets] + chunks
    vecs = emb.embed(inputs)
    n_targets = len(targets)
    master_vecs = vecs[:n_targets]
    chunk_vecs = vecs[n_targets:]

    out: list[OptionalDisplayVO] = []
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
        out.append(_make_display(n, title, meta_by_no[n], quote=quote, present=present))
    return out


def _make_display(
    article: int,
    title: str,
    meta: OptionalArticleSpec,
    *,
    quote: str | None,
    present: bool,
) -> OptionalDisplayVO:
    return OptionalDisplayVO(
        article=article,
        title=title,
        scope=str(meta.get("scope") or "선택"),
        master_body=meta.get("body") or "",
        master_guide=meta.get("guide") or "",
        master_note=meta.get("note") or "",
        user_quote=quote,
        user_present=present,
    )
