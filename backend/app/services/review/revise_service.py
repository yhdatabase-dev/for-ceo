"""취업규칙 수정본 생성 — 원본 `cgr/revise.py:run("취업규칙", ...)` 이관.

===============================================================================
원본 이관
===============================================================================
원본: `cgr/revise.py` (WR + SC 공용) → v2 는 WR 전용으로 이관.

변경점
- SC 경로 제거 (v2 는 WR·EC·guide 만 유지). doc_label 은 고정 "취업규칙".
- `OpenAI(...)` 직접 → `get_llm_client().chat(...)`
  · 재시도·PII·캐시는 어댑터가 흡수 (원본 3회 재시도 + backoff 는 어댑터에서 관리)
- `llm_cache.make_key/get/put` → `make_cache_key` + client cache_key 인자
- `cgr.pii_mask.mask_pii_text/mask_pii_in_payload` → `app.core.security.mask_pii_text`
  · corrections dict 마스킹은 각 필드(now/fix)에 mask_pii_text 적용으로 재현
- `_build_system_prompt` · `_build_user_prompt` 원본 로직 100% 이관
- mark_changes=True 는 WR 기본 (원본 라우터 호출 지점에서도 True) → 프롬프트 규칙 6 부착
- 표준 양식 80k 자 컷 유지
"""
from __future__ import annotations

import time

import psycopg

from app.core.exceptions import LLMError, ValidationError
from app.core.security import mask_pii_text
from app.integrations.llm.cache import make_cache_key
from app.integrations.llm.client import get_llm_client
from app.schemas.review.requests import CorrectionIn, GenerateIn
from app.schemas.review.responses import GenerateOut

_DOC_LABEL = "취업규칙"
_STANDARD_MAX_CHARS = 80_000


class WrReviseService:
    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db

    def run(
        self,
        payload: GenerateIn,
        *,
        standard_text: str | None = None,
        mark_changes: bool = True,
    ) -> GenerateOut:
        """수정본 생성.

        Args:
            standard_text: 표준 취업규칙 원문. 원본은 `data/standards/표준취업규칙_2026.txt`
                           를 읽음. v2 는 라우터가 파일/DB 에서 조회해 넘김.
            mark_changes:  True (WR 기본) → 변경 부분을 【수정】…【/수정】 마커로 감쌈.
        """
        original = (payload.original_text or "").strip()
        if not original:
            raise ValidationError("원문 텍스트가 비어 있습니다.")
        if not payload.corrections:
            raise ValidationError(
                "수정 목록이 비어 있습니다. 반영할 항목을 먼저 담아 주세요."
            )

        # PII 게이트 — 원문·수정 목록 모두 마스킹 후 외부 전송
        # (표준 양식은 공개 배포 자료라 마스킹 불요)
        original_masked = mask_pii_text(original)
        corrections_masked = [
            CorrectionIn(
                name=c.name,
                now=mask_pii_text(c.now),
                fix=mask_pii_text(c.fix),
            )
            for c in payload.corrections
        ]

        std = standard_text or ""
        if std and len(std) > _STANDARD_MAX_CHARS:
            std = std[:_STANDARD_MAX_CHARS]

        system = _build_system_prompt(
            _DOC_LABEL, has_standard=bool(std), mark_changes=mark_changes
        )
        user = _build_user_prompt(original_masked, corrections_masked, std)

        # 캐시 키 — 원본 schema {"kind": "revise", "doc": doc_label[, "marked"]}
        cache_schema: dict = {"kind": "revise", "doc": _DOC_LABEL}
        if mark_changes:
            cache_schema["marked"] = True
        cache_key = make_cache_key("wr_revise", system, user, cache_schema)

        client = get_llm_client()
        t0 = time.perf_counter()
        try:
            resp = client.chat(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.0,
                cache_key=cache_key,
            )
        except LLMError:
            raise
        elapsed = time.perf_counter() - t0

        text = (resp.get("content") or "").strip()
        if not text:
            raise LLMError("수정본 응답이 비어 있습니다.")

        return GenerateOut(
            revised_text=text,
            elapsed_sec=round(elapsed, 3),
            model=resp.get("model", ""),
        )


# ─────────────────────────────────────────────────────────────
# 프롬프트 빌더 (원본 `cgr/revise.py:_build_system_prompt/_build_user_prompt` 이관)
# ─────────────────────────────────────────────────────────────
def _build_system_prompt(
    doc_label: str, has_standard: bool, mark_changes: bool = False
) -> str:
    base = (
        "당신은 노동법 문서 수정 전문가입니다.\n"
        f"입력된 원문을 **그대로 유지**하되, 아래 수정 목록의 항목만 반영한 "
        f"'{doc_label} 수정본' 전체를 출력하세요.\n\n"
        "규칙:\n"
        "1. 수정 목록에 없는 문장·조항·서식은 한 글자도 바꾸지 않는다.\n"
        "2. 각 수정 항목은 원문에서 해당 위치를 찾아 '수정 문구'로 교체한다.\n"
        "3. 원문에 아예 없는(누락) 항목은 문맥상 적절한 조항 위치에 새로 추가한다.\n"
        "4. 순수 텍스트만 출력한다 — 머리말·해설·마크다운 코드블록 금지.\n"
        "5. **계약서 문체(조문체)로 변환** — '수정 문구'가 설명·권고문\n"
        "   (예: '퇴직금을 제공해야 해요', '~하는 것이 좋습니다', '~를 명시하세요')\n"
        "   이면 절대 그대로 넣지 말고, 실제 계약 조항 문장으로 바꿔 쓴다.\n"
        "   (예: '퇴직금을 제공해야 해요' → '제O조(퇴직급여) 위탁자는 근로자퇴직급여\n"
        "   보장법에 따라 퇴직급여를 지급한다.')\n"
        "   '~해요/~하세요/~좋습니다/권장/필요합니다' 같은 표현은 최종 문서에\n"
        "   등장해서는 안 된다."
    )
    if has_standard:
        base += (
            "\n5. **표준 양식 준용** — 문구를 교체·추가할 때는 [표준 양식] 의 해당 조항"
            " 표현·체계를 기준으로 삼는다. 수정 문구가 표준 양식과 충돌하면 표준 양식의"
            " 법정 기준을 우선하되, 사업장 고유 정보(상호·일자·금액·인명 등)는 반드시"
            " 원문의 값을 유지한다. 표준 양식은 참조 기준일 뿐 — 원문에 없는 조항을"
            " 표준 양식에서 통째로 가져와 덧붙이지 않는다(수정 목록에 있는 항목만 반영)."
        )
    if mark_changes:
        base += (
            "\n6. **수정 위치 마커** — 교체·추가한 모든 문구는 정확히 그 범위만"
            " 【수정】…【/수정】 마커로 감싼다. 수정하지 않은 원문에는 절대 마커를"
            " 붙이지 않는다. 마커는 이 두 토큰 외 다른 형태(괄호 변형·대체 기호·"
            "중첩) 금지."
        )
    return base


def _build_user_prompt(
    original_text: str,
    corrections: list[CorrectionIn],
    standard_text: str,
) -> str:
    lines: list[str] = []
    for i, c in enumerate(corrections, start=1):
        name = (c.name or "").strip()
        now = (c.now or "").strip() or "(기재 없음)"
        fix = (c.fix or "").strip()
        lines.append(f"{i}. [{name}] 현재: {now} → 수정: {fix}")
    corrections_block = "\n".join(lines)
    parts = [f"[원문]\n{original_text}", f"[수정 목록]\n{corrections_block}"]
    if standard_text:
        parts.append(f"[표준 양식 — 수정 문구의 준용 기준]\n{standard_text}")
    return "\n\n".join(parts)
