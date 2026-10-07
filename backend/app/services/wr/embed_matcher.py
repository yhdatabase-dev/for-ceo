#
# 슬롯 단위 임베딩 매칭 — interpret 슬롯의 결정성·속도 대안.
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
"""슬롯 단위 임베딩 매칭 — interpret 슬롯의 결정성·속도 대안.

LLM 비결정성 영향을 받는 'interpret' 슬롯의 키워드/구문 검출형은
임베딩 코사인 유사도로 대체. 100% 결정적 + 빠름.

각 슬롯에 search_phrases (1~5개 한국어 표현) 정의:
  - 본문 chunks 와 코사인 유사도 max
  - threshold ≥ 0.65 → found=true + verdict=OK + quote=가장 유사한 chunk
  - 0.50 ≤ ... < 0.65 → found=true + verdict=AMBIGUOUS (모호)
  - < 0.50 → found=false + verdict=VIOLATION (관련 표현 부재)

YAML 슬롯 형식 (embed_match comparator):
  - slot_id: SLOT_xxx
    comparator: "embed_match"
    search_phrases:
      - "감봉 1/10 임금총액"
      - "1임금지급기 임금총액의 10분의 1"
    threshold_ok: 0.65        # 이상이면 OK
    threshold_violation: 0.50 # 미만이면 VIOLATION (그 사이 AMBIGUOUS)
"""
from __future__ import annotations

import re
from typing import Any

from app.integrations.llm.embedding import Embedder, cosine
from app.schemas.wr.values import Extraction, SlotDef


# 모듈 기본 임계값 (관리자 설정으로 override 가능)
_DEFAULT_OK_THRESHOLD = 0.50
_DEFAULT_VIOLATION_THRESHOLD = 0.48
_MAX_CHUNK = 400
_MIN_CHUNK = 20


def _admin_threshold(key: str, fallback: float) -> float:
    """data/admin_settings.json 에서 임계값 조회. 실패 시 fallback.

    호출 시점에 매번 조회하므로 관리자 페이지에서 변경 즉시 반영.
    """
    try:
        from app.repositories.shared.setting import get as _admin_get
        v = _admin_get(key)
        if v is not None:
            return float(v)
    except Exception:
        pass
    return fallback


def _ok_threshold() -> float:
    return _admin_threshold("embed_threshold_ok", _DEFAULT_OK_THRESHOLD)


def _violation_threshold() -> float:
    return _admin_threshold("embed_threshold_violation", _DEFAULT_VIOLATION_THRESHOLD)


def _normalize_for_substring(s: str) -> str:
    """substring 매칭용 정규화: 공백·구두점·따옴표 제거 + 소문자.

    예) '「직원」이라 함은' → '직원이라함은'
        '업무상 적정범위를 넘어' → '업무상적정범위를넘어'
    """
    if not s:
        return ""
    # 한국어 따옴표·구두점·괄호 제거 (의미 보존하되 표기 차이 흡수)
    s = re.sub(r"[「」『』『』\"'`·,.\(\)\[\]【】〈〉《》①②③④⑤⑥⑦⑧⑨⑩]", "", s)
    return re.sub(r"\s+", "", s).lower()


def _split_doc_chunks(text: str) -> list[str]:
    paragraphs = re.split(r"\n\s*\n|\n(?=【)|\n(?=제\s*\d+\s*조)", text)
    chunks: list[str] = []
    for p in paragraphs:
        p = p.strip()
        if len(p) < _MIN_CHUNK:
            continue
        if len(p) <= _MAX_CHUNK:
            chunks.append(p)
        else:
            sents = re.split(r"(?<=[.。])\s+|\n", p)
            buf = ""
            for s in sents:
                if len(buf) + len(s) > _MAX_CHUNK and buf:
                    chunks.append(buf.strip())
                    buf = s
                else:
                    buf = buf + " " + s if buf else s
            if buf.strip():
                chunks.append(buf.strip())
    return chunks


class EmbedMatcher:
    """문서 1회 청크 + 임베딩, 슬롯별 매칭 처리.

    prepare_slots() 로 모든 슬롯 phrases 를 한 번에 batch 임베딩 (slot당 호출 X).
    이후 match() 는 캐시된 vector 만 재사용 → 매우 빠름.
    """

    def __init__(self, document_text: str, embedder: Embedder | None = None) -> None:
        self.embedder = embedder or Embedder()
        self.chunks = _split_doc_chunks(document_text)
        if self.chunks:
            self.chunk_vecs = self.embedder.embed(self.chunks)
        else:
            self.chunk_vecs = []
        self._phrase_vecs_by_slot: dict[str, list[list[float]]] = {}

    def prepare_slots(self, slots: list[SlotDef]) -> None:
        """모든 embed_match 슬롯의 phrases 를 1번 batch 호출로 임베딩."""
        slot_phrase_pairs: list[tuple[str, str]] = []
        for s in slots:
            if s.comparator != "embed_match":
                continue
            for p in s.search_phrases or []:
                slot_phrase_pairs.append((s.slot_id, p))
        if not slot_phrase_pairs:
            return
        all_phrases = [p for _, p in slot_phrase_pairs]
        all_vecs = self.embedder.embed(all_phrases)
        for (sid, _), vec in zip(slot_phrase_pairs, all_vecs):
            self._phrase_vecs_by_slot.setdefault(sid, []).append(vec)

    def match(self, slot: SlotDef) -> Extraction:
        """슬롯의 search_phrases 와 doc chunks 매칭.

        2단계:
          1) Substring 매칭 (정규화 후) — 가장 정확. 공백·구두점 차이 인정.
          2) 임베딩 코사인 유사도 fallback — substring 미발견 시.
        """
        phrases = slot.search_phrases or []
        if not phrases or not self.chunks:
            return Extraction(
                slot_id=slot.slot_id,
                extracted_value=None,
                quote="",
                found=False,
                confidence=0.0,
                verdict="VIOLATION" if slot.required else None,
                verdict_reason="검색 표현 또는 본문이 비어있음",
            )

        # ─── 1단계: Substring 매칭 (가장 정확) ─────────
        norm_chunks = [(i, _normalize_for_substring(c), c) for i, c in enumerate(self.chunks)]
        for ph in phrases:
            np = _normalize_for_substring(ph)
            if not np:
                continue
            for i, nc, original in norm_chunks:
                if np in nc:
                    return Extraction(
                        slot_id=slot.slot_id,
                        extracted_value=True,
                        quote=original[:300],
                        found=True,
                        confidence=1.0,
                        verdict="OK",
                        verdict_reason="본문에 관련 규정이 명시되어 있습니다.",
                    )

        # ─── 2단계: 임베딩 코사인 유사도 fallback ──────
        phrase_vecs = self._phrase_vecs_by_slot.get(slot.slot_id)
        if not phrase_vecs:
            phrase_vecs = self.embedder.embed(phrases)

        # 가장 높은 (phrase, chunk) 쌍의 유사도
        best_sim = -1.0
        best_chunk_idx = -1
        best_phrase = ""
        for pv, ph in zip(phrase_vecs, phrases):
            for ci, cv in enumerate(self.chunk_vecs):
                s = cosine(pv, cv)
                if s > best_sim:
                    best_sim = s
                    best_chunk_idx = ci
                    best_phrase = ph

        ok_th = float(slot.threshold_ok or _ok_threshold())
        vio_th = float(slot.threshold_violation or _violation_threshold())

        quote = self.chunks[best_chunk_idx][:300] if best_chunk_idx >= 0 else ""
        if best_sim >= ok_th:
            return Extraction(
                slot_id=slot.slot_id,
                extracted_value=True,
                quote=quote,
                found=True,
                confidence=best_sim,
                verdict="OK",
                verdict_reason="본문에 관련 규정이 명시되어 있습니다.",
            )
        elif best_sim >= vio_th:
            return Extraction(
                slot_id=slot.slot_id,
                extracted_value=None,
                quote=quote,
                found=True,
                confidence=best_sim,
                verdict="AMBIGUOUS",
                verdict_reason="본문에 유사 표현이 일부 보이나 명확하지 않아 감독관 재확인이 필요합니다.",
            )
        else:
            return Extraction(
                slot_id=slot.slot_id,
                extracted_value=False,
                quote="",
                found=False,
                confidence=best_sim,
                verdict="VIOLATION",
                verdict_reason="본문에서 해당 규정을 찾지 못하였습니다.",
            )

    def match_many(self, slots: list[SlotDef]) -> list[Extraction]:
        return [self.match(s) for s in slots]
