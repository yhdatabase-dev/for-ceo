"""임베딩 사전 필터 — 사업장 본문에 부재한 조는 LLM 호출 스킵.

===============================================================================
원본 이관
===============================================================================
원본: `cgr/article_prefilter.py` → v2 로 이관.

변경점
- `cgr.models.SlotDef / Extraction` → `SlotDefVO / ExtractionVO`
- `cgr.embedding` → `app.integrations.llm.embedding`
- `MasterDB.body(n) / title(n)` 직접 의존 → 시그니처를 `article_texts: dict[int, str]`
  로 바꿔 repository 결합 제거 (호출자가 미리 조회해 전달). 원본과 임계값·로직 동일.
- 관리자 settings store 는 v2 에 아직 없음 → 상수 fallback (TODO: settings repo 도입 시 연결).

동작
- 각 조의 마스터 본문 vs 사업장 본문 chunks 코사인 유사도 max < threshold 면
  '사업장에 부재' 로 판정하여 LLM 호출 건너뛰고 모든 슬롯을 MISSING 처리.
- text-embedding-3-large 1024d 1회 batch 호출 → 빠름 (~3-5s).
"""
from __future__ import annotations

import re

from app.integrations.llm.embedding import Embedder, cosine
from app.schemas.review.values import ExtractionVO, SlotDefVO

# 임계값: 코사인 유사도 < 이면 "사업장에 부재" 로 판정. 보수적으로 낮게.
_SKIP_THRESHOLD = 0.30


def _admin_skip_threshold() -> float:
    """관리자 설정의 prefilter_threshold 우선 — v2 에는 아직 store 없음.

    TODO: `app/repositories/admin/settings_repo` 도입 시 이 함수에서 호출.
    """
    return _SKIP_THRESHOLD


def _split_doc_chunks(text: str, max_chunk: int = 400, min_chunk: int = 20) -> list[str]:
    paragraphs = re.split(r"\n\s*\n|\n(?=【)|\n(?=제\s*\d+\s*조)", text)
    chunks: list[str] = []
    for p in paragraphs:
        p = p.strip()
        if len(p) < min_chunk:
            continue
        if len(p) <= max_chunk:
            chunks.append(p)
        else:
            sents = re.split(r"(?<=[.。])\s+|\n", p)
            buf = ""
            for s in sents:
                if len(buf) + len(s) > max_chunk and buf:
                    chunks.append(buf.strip())
                    buf = s
                else:
                    buf = buf + " " + s if buf else s
            if buf.strip():
                chunks.append(buf.strip())
    return chunks


def filter_articles_by_embedding(
    document_text: str,
    by_article: dict[int, list[SlotDefVO]],
    article_texts: dict[int, str],
    *,
    threshold: float | None = None,
) -> tuple[dict[int, list[SlotDefVO]], dict[int, str]]:
    """임베딩 유사도로 사업장에 부재한 조를 식별.

    Args:
        document_text: 사업장 본문 전체
        by_article:    {조번호: [슬롯정의]}
        article_texts: {조번호: 마스터 본문 텍스트} — 원본은 MasterDB.body(n) 로 조회.
        threshold:     None 이면 관리자 설정 → 기본값 사용

    Returns:
        (active_articles, skipped_reasons)
        - active_articles: 사업장에 관련 영역 있어 LLM 호출 필요
        - skipped_reasons: 사업장에 부재한 조 — 즉시 MISSING 처리
    """
    if threshold is None:
        threshold = _admin_skip_threshold()
    if not by_article:
        return {}, {}

    chunks = _split_doc_chunks(document_text)
    if not chunks:
        return by_article, {}

    target_arts = sorted(by_article.keys())
    targets: list[tuple[int, str]] = []
    for n in target_arts:
        body = article_texts.get(n, "") or ""
        # 원본은 title 을 두 번 넣어 가중치 부여. v2 는 article_texts 에 이미 합쳐 넘어온다고 가정.
        # (호출자가 title. title. body[:200] 형태로 조립하는 것이 원본과 동치)
        match_text = body if body else f"제{n}조"
        targets.append((n, match_text))

    emb = Embedder()
    inputs = [m for _, m in targets] + chunks
    vecs = emb.embed(inputs)

    n_targets = len(targets)
    target_vecs = vecs[:n_targets]
    chunk_vecs = vecs[n_targets:]

    active: dict[int, list[SlotDefVO]] = {}
    skipped: dict[int, str] = {}
    for (n, _), tv in zip(targets, target_vecs):
        max_sim = max((cosine(tv, cv) for cv in chunk_vecs), default=0.0)
        if max_sim >= threshold:
            active[n] = by_article[n]
        else:
            skipped[n] = (
                f"사업장 본문에 관련 영역 부재 (임베딩 유사도 max={max_sim:.2f} < {threshold})"
            )
    return active, skipped


def make_skipped_extractions(slots: list[SlotDefVO]) -> list[ExtractionVO]:
    """사전필터로 스킵된 조의 슬롯 — found=false 빈 추출."""
    return [
        ExtractionVO(
            slot_id=s.slot_id,
            extracted_value=None,
            quote="",
            found=False,
            confidence=None,
        )
        for s in slots
    ]
