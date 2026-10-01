"""EC user 프롬프트 빌더 — 원본 `cgr/ec/prompts.py` 의 build_* 함수 이관.

===============================================================================
원본 이관
===============================================================================
원본 (`cgr/ec/prompts.py`) 의 아래 함수를 이관:
- `build_structure_user_prompt`   L245
- `build_analyze_user_prompt`     L287 (+ `_current_minimum_wage_block` L252)
- `build_generate_user_prompt`    L318
- `build_chat_user_prompt`        L176
- `_extract_mapping_section`      L145  (챗봇 system 조립용)
- `get_chat_system_prompt`        L162  (chat_base + STEP 2~3 매핑 자동 결합)

변경점
- `datadir` 파일 캐시·`prompt_store` 파일 override 제거
  → v2 는 `resolve_prompt(conn, key)` 로 DB override + 코드 default 자동 처리
- `topic_lookup.build_related_topics_block` 은 v2 미이관 — 챗봇에서 optional
- `db.connect().execute("SELECT * FROM v_minimum_wage_current")` (SQLite)
  → `conn.execute("SELECT * FROM cgr_master.v_minimum_wage_current")` (PG)
"""
from __future__ import annotations

import json
import re
from typing import Any

import psycopg

from app.core.logging import get_logger

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────
# structure user prompt
# ─────────────────────────────────────────────────────────────
def build_structure_user_prompt(extracted_text: str) -> str:
    """structure 호출용 user 메시지 (원본 그대로)."""
    return f"다음 OCR 텍스트를 위 양식에 맞춰 구조화해주세요:\n\n{extracted_text}"


# ─────────────────────────────────────────────────────────────
# 현행 최저임금 블록 — analyze user 프롬프트 앞에 주입
# ─────────────────────────────────────────────────────────────
def current_minimum_wage_block(conn: psycopg.Connection) -> str:
    """마스터 DB `v_minimum_wage_current` 조회 → LLM 참조용 블록.

    원본은 `db.connect().execute("SELECT * FROM v_minimum_wage_current")` (SQLite).
    v2 는 psycopg + `cgr_master.v_minimum_wage_current`.
    실패 시 빈 문자열 → LLM 이 일반지식으로 판정.
    """
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM cgr_master.v_minimum_wage_current")
            row = cur.fetchone()
    except Exception as e:  # noqa: BLE001
        log.warning("ec.min_wage 조회 실패 — 블록 생략: %s", e)
        return ""

    if not row:
        return ""
    try:
        year = int(row["year"])
        hourly = int(row["hourly_amount"])
        monthly = int(row["monthly_amount_209h"])
        source = row.get("source") or "최저임금위원회"
    except (KeyError, TypeError, ValueError) as e:  # noqa: BLE001
        log.warning("ec.min_wage 행 파싱 실패: %s", e)
        return ""

    return (
        "[현행 최저임금 — 임금 항목 검토 시 반드시 기준으로 적용]\n"
        f"- 적용 연도: {year}년\n"
        f"- 시급: **{hourly:,}원** (시간당)\n"
        f"- 월 환산: **{monthly:,}원** (주 40h × 4.345주 = 209h 기준)\n"
        f"- 출처: {source}\n"
        "\n"
        f"⚠️ 시급이 {hourly:,}원 미만이거나, 월급을 209h 로 환산한 시급이 {hourly:,}원 미만이면\n"
        "  반드시 임금 항목의 적절성을 '부적절' 로 판정하고, 발견내용에 환산 시급과 차액을 명시.\n"
        f"  (예: '시급 9,160원으로 기재 — {year}년 최저시급 {hourly:,}원 대비 1,160원 미달')\n"
    )


# ─────────────────────────────────────────────────────────────
# analyze user prompt
# ─────────────────────────────────────────────────────────────
def build_analyze_user_prompt(
    conn: psycopg.Connection,
    structured_data: dict[str, Any],
    business_size: str,
    worker_types: list[str],
    legal_guidelines: str = "",
) -> str:
    """analyze 호출용 user 메시지 (원본 로직 그대로).

    현행 최저임금 블록을 마스터 DB 에서 자동 주입 (system 프롬프트 캐시 안 흔들도록
    user 쪽에 담음).
    """
    bs = business_size or "미상"
    wt = ", ".join(worker_types) if worker_types else "미상"
    payload = json.dumps(structured_data, ensure_ascii=False, indent=2)
    mw_block = current_minimum_wage_block(conn)
    parts = [
        "[사용자 정보]\n"
        f"- 사업장 규모: {bs}\n"
        f"- 근로자 유형: {wt}",
    ]
    if mw_block:
        parts.append(mw_block)
    if legal_guidelines:
        parts.append(f"[상세 법령 가이드라인(참고자료 DB)]\n{legal_guidelines}")
    parts.append(f"[구조화된 근로계약서 데이터]\n{payload}")
    return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────
# generate user prompt
# ─────────────────────────────────────────────────────────────
def build_generate_user_prompt(
    analysis_result: dict[str, Any],
    user_overrides: dict[str, str] | None = None,
) -> str:
    """generate 호출용 user 메시지 (원본 그대로).

    user_overrides — 사용자가 결과 화면에서 손본 보완 표현. 별도 섹션으로 강조.
    """
    payload = json.dumps(analysis_result, ensure_ascii=False, indent=2)
    base = f"다음 분석 결과를 바탕으로 완벽한 표준근로계약서를 작성해주세요:\n\n{payload}"
    if not user_overrides:
        return base

    overrides_block = "\n".join(
        f"- 항목 「{name}」: {text}".strip()
        for name, text in user_overrides.items()
        if text and text.strip()
    )
    if not overrides_block:
        return base

    return (
        f"{base}\n\n"
        "=== 사용자 직접 작성 보완 표현 (반드시 그대로 사용) ===\n"
        "아래는 사용자가 결과 페이지에서 직접 손본 보완 표현입니다.\n"
        "표준 계약서 본문 작성 시 해당 항목은 **사용자가 적은 표현을 그대로** 반영하고,\n"
        "LLM 이 임의로 다시 쓰거나 줄이지 마세요.\n"
        "\n"
        "⚠️ **이 섹션의 표현은 위 시스템 작성 지침의 어떤 일반 규칙보다 우선합니다.**\n"
        "  - 시스템 규칙 #6 (계약 시작일/종료일/계약서 작성일을 빈칸으로 두라) 도\n"
        "    아래 항목에 사용자가 구체적 값을 직접 적었으면 그 값을 그대로 본문에 씁니다.\n"
        "  - 임금·서명 등 다른 항목도 동일.\n"
        "\n"
        f"{overrides_block}\n"
    )


# ─────────────────────────────────────────────────────────────
# chat system 조립 (base + ANALYSIS_PROMPT STEP 2~3 매핑)
# ─────────────────────────────────────────────────────────────
_MAPPING_RE = re.compile(r"## STEP 2:.*?(?=## STEP 4:)", flags=re.DOTALL)


def extract_mapping_section(analysis_prompt: str) -> str:
    """ANALYSIS_PROMPT 에서 STEP 2 (서면명시의무 기준) ~ STEP 4 직전까지 추출.

    매핑 테이블 33행이 STEP 3 안에 들어있음. chat system 프롬프트에 결합.
    """
    m = _MAPPING_RE.search(analysis_prompt or "")
    return m.group(0).strip() if m else ""


def compose_chat_system_prompt(chat_base: str, analysis_prompt: str) -> str:
    """chat_base + STEP 2~3 매핑 → 최종 chat system 프롬프트."""
    mapping = extract_mapping_section(analysis_prompt)
    return chat_base + (mapping or "(매핑 테이블 로드 실패)")


# ─────────────────────────────────────────────────────────────
# chat user prompt
# ─────────────────────────────────────────────────────────────
def build_chat_user_prompt(
    user_message: str,
    *,
    analysis_result: dict[str, Any] | None = None,
    focused_item: str | None = None,
    history: list[dict[str, str]] | None = None,
    conn: psycopg.Connection | None = None,
) -> str:
    """chat user 메시지 — 컨텍스트(분석 결과·현재 항목·이전 대화) 묶음.

    분석 결과는 항목별 요약(적절성/항목/발견내용/법적근거) 만 추출해 토큰 절약.
    `conn` 이 있으면 focused_item 관련 노무사회 자료(topic_lookup) 를 첨부.
    """
    blocks: list[str] = []

    if analysis_result and isinstance(analysis_result, dict):
        overall_status = analysis_result.get("overallStatus", "")
        risk_level = analysis_result.get("riskLevel", "")
        results = analysis_result.get("results") or []
        compact: list[dict[str, str]] = []
        for r in results:
            if not isinstance(r, dict):
                continue
            compact.append(
                {
                    "항목": r.get("항목", ""),
                    "적절성": r.get("적절성", ""),
                    "발견내용": (r.get("발견내용") or "")[:120],
                    "법적근거": r.get("법적근거", ""),
                }
            )
        blocks.append(
            "[분석 결과 컨텍스트]\n"
            f"- 종합 판정: {overall_status} (위험도 {risk_level})\n"
            f"- 항목별 요약: {json.dumps(compact, ensure_ascii=False)}"
        )

    if focused_item:
        blocks.append(f"[사용자가 지금 보고 있는 항목] {focused_item}")
        try:
            from app.services.ec.topic_lookup import build_related_topics_block

            related = build_related_topics_block(focused_item, conn=conn)
            if related:
                blocks.append(related)
        except Exception as e:  # noqa: BLE001
            log.warning("ec.chat.topic_lookup 실패 (%s): %s", focused_item, e)

    if history:
        recent = history[-6:]
        hist_lines: list[str] = []
        for h in recent:
            role = h.get("role", "user")
            content = (h.get("content") or "")[:600]
            hist_lines.append(f"- {role}: {content}")
        blocks.append("[이전 대화]\n" + "\n".join(hist_lines))

    blocks.append(f"[사용자 질문] {user_message}")
    return "\n\n".join(blocks)
