"""EC 33-매핑 위반 분석 서비스 — 원본 `cgr/ec/services/analyze.py:run` 이관.

===============================================================================
원본 이관
===============================================================================
원본
- 입력: structured_data + business_size + worker_types + (legal_guidelines)
- 시스템 프롬프트: ec::ANALYSIS_PROMPT (33-매핑 테이블 + meta 태그 규칙)
- user: build_analyze_user_prompt (+ 현행 최저임금 블록 자동 주입)
- LLM (temp=0, response_format=json_object)
- 후처리:
  · `_attach_real_topic_refs` — <meta> 태그를 DB 실제 연관주제로 교체
  · `_reconcile_wage_total`   — 임금 합계 오탐 결정적 정정
  · `_postprocess` = 위 둘 조합

변경점
- `OpenAI(...)` → `get_llm_client().chat(...)`
- `prompts.get_analysis_prompt()` → `resolve_prompt(conn, "ec::ANALYSIS_PROMPT")`
- `prompts.build_analyze_user_prompt` → `prompt_builders.build_analyze_user_prompt`
  · `current_minimum_wage_block(conn)` 을 안에서 호출 (마스터 뷰 조회)
- `topic_lookup.topics_for_item` → v2 미이관 (`app/services/ec/topic_lookup.py` TODO)
  · 미존재 시 <meta> 태그만 제거하고 넘어감 (첨부 스킵)
- `_reconcile_wage_total` · `_wage_total_consistent` · `_won` 원본 100% 이관
- `_FALLBACK_RESULT` 원본 그대로 유지
- 감사 로그 `InteractionLogRepo.log(kind='근로계약서', case_uid=...)`
"""
from __future__ import annotations

import re
import time
from typing import Any

import psycopg

from app.core.exceptions import ValidationError
from app.core.logging import bind_context, get_logger
from app.core.security import mask_pii_in_payload, mask_pii_text
from app.integrations.llm.cache import make_cache_key
from app.integrations.llm.client import get_llm_client
from app.integrations.llm.prompts import resolve_prompt
from app.repositories.shared import InteractionLogRepo
from app.schemas.ec.requests import AnalyzeIn
from app.schemas.ec.responses import AnalyzeOut
from app.services.ec.prompt_builders import build_analyze_user_prompt
from app.utils.json_repair import safe_json_parse

log = get_logger(__name__)

_PROMPT_KEY = "ec::ANALYSIS_PROMPT"
_PROMPT_VERSION = "v1"

_META_RE = re.compile(r"<meta\b[^>]*?>", re.IGNORECASE)
_NUM_RE = re.compile(r"-?\d[\d,]*")
_SUM_KW = ("합계", "합산", "산식", "정합", "일치하지", "구성항목", "총액")
_VIOL_KW = ("최저임금", "미달", "미만", "누락", "위반", "서면", "명시")


_FALLBACK_RESULT: dict[str, Any] = {
    "riskLevel": "중",
    "overallStatus": "보완필요",
    "overallOpinion": "분석 중 오류가 발생했습니다.",
    "results": [],
    "finalRecommendations": "시스템 오류로 인해 분석을 완료하지 못했습니다. 다시 시도해주세요.",
}


def fallback_result() -> dict[str, Any]:
    import copy

    return copy.deepcopy(_FALLBACK_RESULT)


# ─────────────────────────────────────────────────────────────
# 후처리 1 — <meta> 태그를 실제 연관주제로 교체
# ─────────────────────────────────────────────────────────────
def _attach_real_topic_refs(
    data: dict[str, Any], conn: psycopg.Connection | None = None
) -> dict[str, Any]:
    """LLM 이 판단이유에 넣은 <meta> 태그(부정확 placeholder) 제거하고
    각 항목의 DB 실제 연관주제로 교체. idempotent.

    conn 미제공 시 <meta> 만 제거하고 refs 는 빈 리스트.
    """
    from app.services.ec.topic_lookup import topics_for_item

    try:
        results = data.get("results")
        if not isinstance(results, list):
            return data
        for item in results:
            if not isinstance(item, dict):
                continue
            field = (item.get("항목") or "").strip()
            reason = _META_RE.sub("", item.get("판단이유") or "")
            reason = re.sub(r"\s{2,}", " ", reason).strip()
            refs = topics_for_item(field, conn=conn)[:4] if field else []
            metas = "".join(
                f"<meta db='DB_{topic}' n='{sec}' />" for topic, sec in refs
            )
            item["판단이유"] = (reason + (" " + metas if metas else "")).strip()
    except Exception as e:  # noqa: BLE001
        log.warning("ec.analyze.attach_real_topic_refs 실패: %s", e)
    return data


# ─────────────────────────────────────────────────────────────
# 후처리 2 — 임금 합계 결정적 검산
# ─────────────────────────────────────────────────────────────
def _won(s: Any) -> int | None:
    m = _NUM_RE.search(str(s or ""))
    if not m:
        return None
    try:
        return int(m.group().replace(",", ""))
    except ValueError:
        return None


def _wage_total_consistent(
    structured_data: dict[str, Any],
) -> tuple[bool, int, int] | None:
    """임금 (기본급+제수당+상여금) 합계 vs 임금총액 정합 판단.

    반환: (consistent, comp_sum, total) 또는 검산 불가 시 None.
    """
    try:
        wage = structured_data.get("임금")
        if not isinstance(wage, dict):
            return None

        def _val(key: str) -> int | None:
            cell = wage.get(key)
            if isinstance(cell, dict):
                return _won(cell.get("value"))
            return _won(cell)

        total = _val("임금총액")
        if total is None or total <= 0:
            return None
        comps = [_val("기본급"), _val("제수당"), _val("상여금")]
        nums = [c for c in comps if c is not None]
        if not nums:
            return None
        comp_sum = sum(nums)
        return (abs(comp_sum - total) <= 1, comp_sum, total)
    except Exception:
        return None


def _reconcile_wage_total(
    data: dict[str, Any], structured_data: dict[str, Any]
) -> dict[str, Any]:
    """구성항목 합계가 지급총액과 일치하면 '합계 불일치' 오탐을 정정. idempotent."""
    try:
        check = _wage_total_consistent(structured_data)
        if check is None:
            return data
        consistent, comp_sum, total = check
        if not consistent:
            return data

        results = data.get("results")
        if not isinstance(results, list):
            return data

        changed = False
        for item in results:
            if not isinstance(item, dict):
                continue
            field = item.get("항목") or ""
            text = (item.get("판단이유") or "") + " " + (item.get("발견내용") or "")
            is_total_item = ("총액" in field) or ("합계" in field)
            mentions_sum = any(k in text for k in _SUM_KW)
            if not (is_total_item or ("임금" in field and mentions_sum)):
                continue
            if (item.get("적절성") or "") == "적절":
                continue
            has_violation = any(k in text for k in _VIOL_KW)
            fact = (
                f"구성항목 합계({comp_sum:,}원)가 지급합계액({total:,}원)과 "
                "정확히 일치합니다."
            )
            if mentions_sum and not has_violation:
                # 오탐 — 산술 트집뿐 → 적절로 정정
                item["적절성"] = "적절"
                item["판단이유"] = fact
                item["발견내용"] = fact
                item["개선권고"] = ""
                changed = True
            else:
                # 실제 위반과 섞임 → 등급 유지, 산술 정합 사실만 덧붙임
                reason = (item.get("판단이유") or "").strip()
                if "일치합니다" not in reason:
                    item["판단이유"] = (reason + " " + fact).strip()
                    changed = True

        if changed:
            grades = [
                (it.get("적절성") or "")
                for it in results
                if isinstance(it, dict)
            ]
            n_bad = sum(1 for g in grades if g == "부적절")
            n_warn = sum(1 for g in grades if g == "보완필요")
            data["overallStatus"] = (
                "위험" if n_bad else ("보완필요" if n_warn else "적정")
            )
            data["riskLevel"] = "상" if n_bad else ("중" if n_warn else "하")
    except Exception as e:  # noqa: BLE001
        log.warning("ec.analyze.reconcile_wage_total 실패: %s", e)
    return data


def _postprocess(
    data: dict[str, Any],
    structured_data: dict[str, Any],
    conn: psycopg.Connection | None = None,
) -> dict[str, Any]:
    """참고자료 칩 교정 + 임금합계 오탐 정정. idempotent."""
    data = _attach_real_topic_refs(data, conn=conn)
    data = _reconcile_wage_total(data, structured_data)
    return data


# ─────────────────────────────────────────────────────────────
# 서비스
# ─────────────────────────────────────────────────────────────
class AnalyzeService:
    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db
        self.log_repo = InteractionLogRepo(db)

    def run(self, payload: AnalyzeIn, *, visitor: str | None = None) -> AnalyzeOut:
        if not isinstance(payload.structured_data, dict):
            raise ValidationError("structured_data 가 dict 가 아닙니다.")

        # 원본 cgr/api/routes/ec.py:analyze L373 대응 — case_id 시점 로그 상관 강화
        if payload.case_id:
            bind_context(case_uid=payload.case_id)

        # PII 게이트 — 8섹션 중첩 dict 재귀 마스킹
        structured = mask_pii_in_payload(payload.structured_data)

        client = get_llm_client()
        system = resolve_prompt(self.db, _PROMPT_KEY)
        user = build_analyze_user_prompt(
            self.db,
            structured_data=structured,
            business_size=payload.business_size or "",
            worker_types=payload.worker_types or [],
            legal_guidelines=payload.legal_guidelines or "",
        )

        cache_key = make_cache_key(
            _PROMPT_KEY, _PROMPT_VERSION, system, user
        )

        t0 = time.perf_counter()
        try:
            resp = client.chat(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
                cache_key=cache_key,
            )
        except Exception as e:  # noqa: BLE001
            log.warning(
                "ec.analyze.llm_failed — fallback 반환 (case=%s): %s",
                payload.case_id, e,
            )
            return AnalyzeOut(
                analysis_result=fallback_result(),
                elapsed_sec=0.0,
                model="",
            )
        elapsed = time.perf_counter() - t0

        data = safe_json_parse(resp.get("content") or "", default=None)
        if not isinstance(data, dict) or "results" not in data:
            log.warning("ec.analyze 응답 형식 오류 — fallback 반환")
            data = fallback_result()
        else:
            # 결정적 후처리 — self.db 를 topic_lookup 에 전달
            data = _postprocess(data, structured, conn=self.db)

        try:
            self.log_repo.log(
                kind="근로계약서",
                model=resp.get("model", ""),
                input_text=mask_pii_text(str(payload.structured_data)[:2000]),
                output_text=str(data)[:2000],
                visitor=visitor,
                case_uid=payload.case_id or None,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("ec.analyze.audit_log 실패: %s", e)

        return AnalyzeOut(
            analysis_result=data,
            elapsed_sec=round(elapsed, 3),
            model=resp.get("model", ""),
        )
