"""정합성 판정 룰 엔진.

4종 비교 연산자:
  - >=, <=, == : 수치/단순 비교
  - object_match : 다중 키 dict 비교 (모든 키 일치해야 OK)
  - presence : 존재 여부 (임의 슬롯)
"""
from __future__ import annotations

from typing import Any

from app.schemas.wr.values import Extraction, Finding, MasterValue, SlotDef


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


def _compare_object(extracted: Any, master_val: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(extracted, dict):
        return False, f"객체가 아님: {extracted!r}"
    diffs = []
    for k, expect in master_val.items():
        if k in ("note", "unit"):
            continue
        got = extracted.get(k)
        if _coerce_int(got) != _coerce_int(expect) and got != expect:
            diffs.append(f"{k}: 추출={got!r} vs 기준={expect!r}")
    if diffs:
        return False, "객체 키 불일치 — " + "; ".join(diffs)
    return True, ""


def _compare_presence(extracted: Extraction) -> tuple[bool, str]:
    if extracted.found:
        return True, ""
    return False, "본문에서 미검출"


def _judge_interpret(extracted: Extraction, *, prefix: str = "") -> tuple[str, str]:
    """verdict 결과 → status 매핑.

    Returns:
        (status, reason) — status 는 'OK' | 'VIOLATION' | 'AMBIGUOUS' | 'ERROR'
    """
    v = extracted.verdict
    reason = (extracted.verdict_reason or "").strip()
    if v == "OK":
        # 적정인 경우 reason 은 단순화 — 사용자에게 부정적 표현 노출 회피
        return "OK", reason or "기준 충족"
    if v == "VIOLATION":
        return "VIOLATION", reason or "기준 미충족"
    if v == "AMBIGUOUS":
        return "AMBIGUOUS", reason or "감독관 재확인 권장"
    return "ERROR", "verdict 미설정"


def _default_severity(slot: SlotDef) -> str:
    """슬롯 정의에 violation_severity 가 없을 때 추정 fallback.

    - penalty 가 비어 있거나 '직접 적용 벌칙 없음' 표기 → LOW (임의·확인적 규정)
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


def evaluate(slot: SlotDef, extraction: Extraction) -> Finding:
    """슬롯 + 추출결과 → Finding."""
    expected = slot.master_value
    op = slot.comparator

    # interpret / embed_match 슬롯은 extraction.verdict 를 그대로 신뢰 (코사인+substring 결과 우선)
    if op in ("interpret", "embed_match"):
        status, reason = _judge_interpret(extraction)
        # ERROR (LLM 이 verdict 미설정) 인 경우 — found · required · master_value 로 추론
        if status == "ERROR":
            master_v = expected.value if expected else None
            is_negative_check = (master_v is False)  # 부정 검출 슬롯 (있으면 안 됨)
            if not extraction.found:
                # 본문에 관련 표현 부재
                if not slot.required or is_negative_check:
                    # 임의 슬롯이거나 부정 검출 슬롯 → 본문 부재는 적정
                    status = "OK"
                    reason = "임의 규정 — 본문 미기재 가능 (해당사항 없음)." if not slot.required else "부정 검출 항목 — 본문에 부적정 표현 부재로 적정."
                else:
                    status = "MISSING"
                    reason = extraction.verdict_reason or "본문에서 관련 규정을 찾지 못하였습니다."
            else:
                # found=True 인데 verdict 미설정 — VIOLATION 으로 보수적 처리
                status = "VIOLATION"
                reason = extraction.verdict_reason or "verdict 미설정 — 감독관 재확인 권장"
        # 본문에 부재(found=false) + VIOLATION 으로 잡힌 경우는 사실 "누락"이므로 MISSING 으로 변환
        # 단, 부정 검출 슬롯 (master_value=false) 은 본문 부재가 정상 → OK 로 처리
        if status == "VIOLATION" and not extraction.found:
            master_v = expected.value if expected else None
            if master_v is False:
                # 부정 검출 슬롯 — 본문에 부적정 표현 부재 → 적정
                status = "OK"
                reason = "부정 검출 항목 — 본문에 부적정 표현이 없어 적정합니다."
            else:
                status = "MISSING"
        default_sev = _default_severity(slot)
        sev_map = {
            "OK": "INFO",
            "VIOLATION": slot.violation_severity or default_sev,
            "MISSING": slot.missing_severity or slot.violation_severity or default_sev,
            "AMBIGUOUS": default_sev if default_sev == "LOW" else "MEDIUM",
            "ERROR": "INFO",
        }
        return Finding(
            slot_id=slot.slot_id,
            article=slot.article,
            item_name=slot.slot_id,
            extracted=extraction,
            expected=expected,
            comparator=op,
            status=status,  # type: ignore[arg-type]
            severity=sev_map.get(status, "INFO"),  # type: ignore[arg-type]
            reason=reason,
            penalty=slot.penalty if status == "VIOLATION" else [],
        )

    # 미검출(found=False) 처리
    if not extraction.found:
        if slot.required:
            sev = slot.missing_severity or slot.violation_severity or _default_severity(slot)
            return Finding(
                slot_id=slot.slot_id,
                article=slot.article,
                item_name=slot.slot_id,
                extracted=extraction,
                expected=expected,
                comparator=op,
                status="MISSING",
                severity=sev,
                reason="필수기재사항 누락 — 본문에서 관련 규정을 찾지 못함",
                penalty=slot.penalty,
            )
        # 임의 슬롯이고 미검출이면 OK (해당사항 없음)
        return Finding(
            slot_id=slot.slot_id,
            article=slot.article,
            item_name=slot.slot_id,
            extracted=extraction,
            expected=expected,
            comparator=op,
            status="OK",
            severity="INFO",
            reason="임의 규정 — 본문 미기재 가능 (해당사항 없음).",
            penalty=[],
        )

    # found=True → 비교 수행
    val = extraction.extracted_value
    master_raw = expected.value
    extra: dict[str, Any] = expected.model_dump(exclude_none=True)
    extra.pop("value", None)
    extra.pop("unit", None)
    extra.pop("note", None)

    try:
        if op in (">=", "<=", "=="):
            # master_value 가 boolean 인 경우 == 로 처리
            if isinstance(master_raw, bool) or (op == "==" and not isinstance(master_raw, (int, float))):
                ok, reason = _compare_eq(val, master_raw)
            else:
                ok, reason = _compare_numeric(val, master_raw, op)
        elif op == "object_match":
            # MasterValue 의 추가 키들이 비교 대상
            ok, reason = _compare_object(val, extra)
        elif op == "presence":
            ok, reason = _compare_presence(extraction)
        else:
            ok, reason = False, f"알 수 없는 연산자: {op}"
    except Exception as e:
        return Finding(
            slot_id=slot.slot_id,
            article=slot.article,
            item_name=slot.slot_id,
            extracted=extraction,
            expected=expected,
            comparator=op,
            status="ERROR",
            severity="INFO",
            reason=f"룰 평가 오류: {type(e).__name__}: {e}",
            penalty=[],
        )

    if ok:
        return Finding(
            slot_id=slot.slot_id,
            article=slot.article,
            item_name=slot.slot_id,
            extracted=extraction,
            expected=expected,
            comparator=op,
            status="OK",
            severity="INFO",
            reason="기준 충족",
            penalty=[],
        )

    sev = slot.violation_severity or _default_severity(slot)
    return Finding(
        slot_id=slot.slot_id,
        article=slot.article,
        item_name=slot.slot_id,
        extracted=extraction,
        expected=expected,
        comparator=op,
        status="VIOLATION",
        severity=sev,
        reason=reason,
        penalty=slot.penalty,
    )
