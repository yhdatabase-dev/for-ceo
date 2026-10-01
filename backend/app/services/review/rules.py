"""정합성 판정 룰 엔진.

===============================================================================
원본 이관
===============================================================================
원본: `cgr/rules.py` (258줄) → v2 로 이관.

변경점
- `cgr.models.SlotDef / Extraction / Finding / MasterValue`
  → `app.schemas.review.values.{SlotDefVO, ExtractionVO, FindingVO, MasterValueVO}`
- Finding 구조가 변경됨 (원본은 extracted/expected 를 nested 로 담음, v2 는 평면).
    · extraction.quote → FindingVO.quote
    · extraction.extracted_value → FindingVO.extracted_value
    · slot.penalty 는 status 에 따라 penalty_omission / penalty_violation 로 분리
- MasterValue 의 object_match 용 "추가 키" 비교는 원본이 model_dump extra 였으나
  v2 는 MasterValueVO.keys 로 명시적. 이 파일이 그 차이를 흡수.
- 로직·판정 규칙은 원본과 100% 동일 (LLM 무관 순수 함수).

4종 비교 연산자:
- `>=`, `<=`, `==` : 수치/단순 비교
- `object_match`  : 다중 키 dict 비교 (모든 키 일치해야 OK)
- `presence`      : 존재 여부 (임의 슬롯)
- `interpret` · `embed_match` : LLM/임베딩 verdict 신뢰
"""
from __future__ import annotations

from typing import Any

from app.schemas.review.values import (
    ExtractionVO,
    FindingVO,
    MasterValueVO,
    SlotDefVO,
)


# ─────────────────────────────────────────────────────────────
# 값 변환 헬퍼
# ─────────────────────────────────────────────────────────────
def _coerce_int(v: Any) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        digits = "".join(ch for ch in v if ch.isdigit() or ch == "-")
        if digits:
            try:
                return int(digits)
            except ValueError:
                return None
    return None


# ─────────────────────────────────────────────────────────────
# 비교 연산자별 판정 로직
# ─────────────────────────────────────────────────────────────
def _compare_numeric(extracted: Any, master_val: Any, op: str) -> tuple[bool, str]:
    e = _coerce_int(extracted)
    m = _coerce_int(master_val)
    if e is None or m is None:
        return False, f"수치 비교 불가 (추출={extracted!r}, 기준={master_val!r})"
    if op == ">=":
        ok = e >= m
        return ok, ("" if ok else f"추출값 {e} < 기준 {m} (>= 필요)")
    if op == "<=":
        ok = e <= m
        return ok, ("" if ok else f"추출값 {e} > 기준 {m} (<= 필요)")
    if op == "==":
        ok = e == m
        return ok, ("" if ok else f"추출값 {e} ≠ 기준 {m}")
    return False, f"알 수 없는 연산자: {op}"


def _compare_eq(extracted: Any, master_val: Any) -> tuple[bool, str]:
    if extracted == master_val:
        return True, ""
    return False, f"값 불일치 (추출={extracted!r}, 기준={master_val!r})"


def _compare_object(extracted: Any, master_keys: dict[str, Any]) -> tuple[bool, str]:
    """object_match — 다중 키 dict 비교.

    v2 는 MasterValueVO.keys 에 추가 키가 담김. 원본은 MasterValue 의 extra 필드였음.
    비교 기준·오차 허용은 원본과 동일.
    """
    if not isinstance(extracted, dict):
        return False, f"객체가 아님: {extracted!r}"
    diffs: list[str] = []
    for k, expect in master_keys.items():
        if k in ("note", "unit"):
            continue
        got = extracted.get(k)
        if _coerce_int(got) != _coerce_int(expect) and got != expect:
            diffs.append(f"{k}: 추출={got!r} vs 기준={expect!r}")
    if diffs:
        return False, "객체 키 불일치 — " + "; ".join(diffs)
    return True, ""


def _compare_presence(extraction: ExtractionVO) -> tuple[bool, str]:
    if extraction.found:
        return True, ""
    return False, "본문에서 미검출"


def _judge_interpret(extraction: ExtractionVO, *, prefix: str = "") -> tuple[str, str]:
    """LLM verdict 결과 → status 매핑 (interpret / embed_match 슬롯).

    Returns:
        (status, reason) — status = 'OK' | 'VIOLATION' | 'AMBIGUOUS' | 'ERROR'
    """
    v = extraction.verdict
    reason = (extraction.verdict_reason or "").strip()
    if v == "OK":
        return "OK", reason or "기준 충족"
    if v == "VIOLATION":
        return "VIOLATION", reason or "기준 미충족"
    if v == "AMBIGUOUS":
        return "AMBIGUOUS", reason or "감독관 재확인 권장"
    return "ERROR", "verdict 미설정"


# ─────────────────────────────────────────────────────────────
# severity 기본값 산출
# ─────────────────────────────────────────────────────────────
def _default_severity(slot: SlotDefVO) -> str:
    """슬롯 정의에 violation_severity 가 없을 때 fallback.

    - penalty 가 비어 있거나 '직접 적용 벌칙 없음' → LOW (임의·확인적)
    - required=False (임의 슬롯) → LOW
    - 그 외 → MEDIUM
    """
    pen = slot.penalty or []
    has_real = any(p and "직접 적용 벌칙 없음" not in str(p) for p in pen)
    if not has_real:
        return "LOW"
    if not slot.required:
        return "LOW"
    return "MEDIUM"


# ─────────────────────────────────────────────────────────────
# FindingVO 구성 헬퍼 — 원본 Finding 을 v2 평면 구조로 변환
# ─────────────────────────────────────────────────────────────
def _build_finding(
    *,
    slot: SlotDefVO,
    extraction: ExtractionVO,
    status: str,
    severity: str,
    reason: str,
) -> FindingVO:
    """공통 FindingVO 구성.

    v2 는 status 에 따라 penalty 를 penalty_omission / penalty_violation 으로 분리.
    """
    penalty_om: list[str] = []
    penalty_vi: list[str] = []
    if status == "MISSING":
        penalty_om = list(slot.penalty)
    elif status == "VIOLATION":
        penalty_vi = list(slot.penalty)

    return FindingVO(
        slot_id=slot.slot_id,
        article=slot.article,
        status=status,
        severity=severity,
        comparator=slot.comparator,
        reason=reason,
        quote=extraction.quote or "",
        extracted_value=extraction.extracted_value,
        penalty_omission=penalty_om,
        penalty_violation=penalty_vi,
        fix_example=slot.fix_example,
    )


# ─────────────────────────────────────────────────────────────
# 진입점 — 슬롯 1개 평가
# ─────────────────────────────────────────────────────────────
def evaluate(slot: SlotDefVO, extraction: ExtractionVO) -> FindingVO:
    """슬롯 + 추출결과 → Finding.

    원본 `cgr/rules.py:evaluate()` 완전 이관 (v2 스키마 적응 외 로직 동일).
    """
    expected = slot.master_value
    op = slot.comparator

    # ─── interpret / embed_match: LLM verdict 우선 ───
    if op in ("interpret", "embed_match"):
        status, reason = _judge_interpret(extraction)

        # ERROR (LLM verdict 미설정) → found · required · master_value 로 추론
        if status == "ERROR":
            master_v = expected.value if expected else None
            is_negative_check = master_v is False   # 부정 검출 슬롯

            if not extraction.found:
                if not slot.required or is_negative_check:
                    status = "OK"
                    reason = (
                        "임의 규정 — 본문 미기재 가능 (해당사항 없음)."
                        if not slot.required
                        else "부정 검출 항목 — 본문에 부적정 표현 부재로 적정."
                    )
                else:
                    status = "MISSING"
                    reason = extraction.verdict_reason or "본문에서 관련 규정을 찾지 못하였습니다."
            else:
                # found=True 인데 verdict 미설정 — 보수적으로 VIOLATION
                status = "VIOLATION"
                reason = extraction.verdict_reason or "verdict 미설정 — 감독관 재확인 권장"

        # 본문 부재(found=false) + VIOLATION → MISSING 으로 변환
        # 단, 부정 검출 슬롯(master_value=false) 은 부재가 정상 → OK
        if status == "VIOLATION" and not extraction.found:
            master_v = expected.value if expected else None
            if master_v is False:
                status = "OK"
                reason = "부정 검출 항목 — 본문에 부적정 표현이 없어 적정합니다."
            else:
                status = "MISSING"

        default_sev = _default_severity(slot)
        sev_map = {
            "OK":         "INFO",
            "VIOLATION":  slot.violation_severity or default_sev,
            "MISSING":    slot.missing_severity or slot.violation_severity or default_sev,
            "AMBIGUOUS":  default_sev if default_sev == "LOW" else "MEDIUM",
            "ERROR":      "INFO",
        }
        return _build_finding(
            slot=slot,
            extraction=extraction,
            status=status,
            severity=sev_map.get(status, "INFO"),
            reason=reason,
        )

    # ─── 미검출(found=False) 처리 ───
    if not extraction.found:
        if slot.required:
            sev = (
                slot.missing_severity
                or slot.violation_severity
                or _default_severity(slot)
            )
            return _build_finding(
                slot=slot,
                extraction=extraction,
                status="MISSING",
                severity=sev,
                reason="필수기재사항 누락 — 본문에서 관련 규정을 찾지 못함",
            )
        # 임의 슬롯 + 미검출 = OK
        return _build_finding(
            slot=slot,
            extraction=extraction,
            status="OK",
            severity="INFO",
            reason="임의 규정 — 본문 미기재 가능 (해당사항 없음).",
        )

    # ─── found=True → 실제 비교 수행 ───
    val = extraction.extracted_value
    master_raw = expected.value if expected else None
    master_keys = _get_master_keys(expected)

    try:
        if op in (">=", "<=", "=="):
            # master_value 가 boolean 이거나 op == 인데 수치가 아니면 == 로 처리
            if isinstance(master_raw, bool) or (
                op == "==" and not isinstance(master_raw, (int, float))
            ):
                ok, reason = _compare_eq(val, master_raw)
            else:
                ok, reason = _compare_numeric(val, master_raw, op)
        elif op == "object_match":
            ok, reason = _compare_object(val, master_keys)
        elif op == "presence":
            ok, reason = _compare_presence(extraction)
        else:
            ok, reason = False, f"알 수 없는 연산자: {op}"
    except Exception as e:  # noqa: BLE001
        return _build_finding(
            slot=slot,
            extraction=extraction,
            status="ERROR",
            severity="INFO",
            reason=f"룰 평가 오류: {type(e).__name__}: {e}",
        )

    if ok:
        return _build_finding(
            slot=slot,
            extraction=extraction,
            status="OK",
            severity="INFO",
            reason="기준 충족",
        )

    sev = slot.violation_severity or _default_severity(slot)
    return _build_finding(
        slot=slot,
        extraction=extraction,
        status="VIOLATION",
        severity=sev,
        reason=reason,
    )


# ─────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────
def _get_master_keys(expected: MasterValueVO | None) -> dict[str, Any]:
    """MasterValueVO 에서 object_match 용 추가 키 dict 추출.

    v2 는 keys 필드에 명시적으로 담김. 원본은 extra 로 담겼음.
    """
    if expected is None:
        return {}
    return dict(expected.keys) if expected.keys else {}
