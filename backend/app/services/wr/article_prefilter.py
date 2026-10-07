#
# 임베딩 사전 필터 — 사업장 본문에 해당 영역 부재 시 LLM 호출 스킵.
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.05.28      kimzion77   최초 생성
# 2026.10.02      이시영      구조 이행 (backend/cgr → backend/app)
# 2026.10.02      이시영      구조 조정 (web/ai 파트 디렉터리 → 도메인 단일 디렉터리)
#
# Author: kimzion77
# Since: 2026.05.28
#
"""임베딩 사전 필터 — 사업장 본문에 해당 영역 부재 시 LLM 호출 스킵.

각 조의 마스터 본문(D열) vs 사업장 본문 chunks 코사인 유사도 max < threshold 면
'사업장에 관련 영역 없음' 으로 판정하여 LLM 호출 건너뛰고 모든 슬롯을 MISSING 처리.

text-embedding-3-large 1024d 1회 호출로 모든 조 + chunks 임베딩 → 빠름 (~3-5s).
"""
from __future__ import annotations

import re
import time
from typing import Any

from app.integrations.llm.embedding import Embedder, cosine
from app.repositories.wr.master import MasterDB
from app.schemas.wr.values import Extraction, SlotDef


# 임계값: 코사인 유사도 < 이면 "사업장에 부재" 로 판정. 보수적으로 낮게.
_SKIP_THRESHOLD = 0.30


def _admin_skip_threshold() -> float:
    """관리자 설정의 prefilter_threshold 우선, 없으면 모듈 기본값."""
    try:
        from app.repositories.shared.setting import get as _admin_get
        v = _admin_get("prefilter_threshold")
        if v is not None:
            return float(v)
    except Exception:
        pass
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
    by_article: dict[int, list[SlotDef]],
    db: MasterDB,
    *,
    threshold: float | None = None,
) -> tuple[dict[int, list[SlotDef]], dict[int, str]]:
    if threshold is None:
        threshold = _admin_skip_threshold()
    """임베딩 유사도로 사업장에 부재한 조를 식별.

    Returns:
        (active_articles, skipped_reasons)
        active_articles: 사업장에 관련 영역 있어 LLM 호출 필요
        skipped_reasons: 사업장에 부재한 조 — 즉시 MISSING 처리
    """
    if not by_article:
        return {}, {}

    chunks = _split_doc_chunks(document_text)
    if not chunks:
        return by_article, {}

    target_arts = sorted(by_article.keys())
    targets: list[tuple[int, str]] = []
    for n in target_arts:
        body = db.body(n) or db.title(n)
        title = db.title(n)
        # 매칭 텍스트: 제목 가중치 + 본문 일부
        match_text = f"{title}. {title}. {body[:200]}"
        targets.append((n, match_text))

    emb = Embedder()
    inputs = [m for _, m in targets] + chunks
    vecs = emb.embed(inputs)

    n_targets = len(targets)
    target_vecs = vecs[:n_targets]
    chunk_vecs = vecs[n_targets:]

    active: dict[int, list[SlotDef]] = {}
    skipped: dict[int, str] = {}
    for (n, _), tv in zip(targets, target_vecs):
        max_sim = max((cosine(tv, cv) for cv in chunk_vecs), default=0.0)
        if max_sim >= threshold:
            active[n] = by_article[n]
        else:
            skipped[n] = f"사업장 본문에 관련 영역 부재 (임베딩 유사도 max={max_sim:.2f} < {threshold})"
    return active, skipped


def make_skipped_extractions(slots: list[SlotDef]) -> list[Extraction]:
    """사전필터로 스킵된 조의 슬롯 — found=false 빈 추출."""
    return [
        Extraction(
            slot_id=s.slot_id,
            extracted_value=None,
            quote="",
            found=False,
            confidence=None,
        )
        for s in slots
    ]
