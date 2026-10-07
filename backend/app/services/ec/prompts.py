"""근로계약서 풀 이식 — 프롬프트 로더.

기존 `1. 근로계약서/기존/server/prompts.json` 을 그대로 옮겨와
`mvp/data/prompts/ec_prompts.json` 에 둠. 한 자도 다르지 않게 보존.

`STRUCTURE_PROMPT` — OCR 텍스트 → 8섹션 구조화 JSON
`ANALYSIS_PROMPT`  — 구조화 JSON + 사용자 컨텍스트 → 33-매핑 위반 분석 (meta 태그)
`GENERATION_PROMPT` — 분석 결과 → 표준 근로계약서 텍스트
`OCR_PROMPT`        — 이미지 → 텍스트 (참고용. 실제로는 `cgr/parsers/image.py` 가 사용)

사용자 메시지 템플릿은 본 모듈의 `build_*_user_prompt` 헬퍼로 통일.
JSON 파일 위치는 추후 관리자 대시보드에서 편집 가능하도록 외부에 둔다.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core import datadir


# baked(이미지 번들) 기본본 — 최초 1회 볼륨으로 시드되는 원본
_BAKED_PROMPTS_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "prompts" / "ec_prompts.json"
)
# 하위호환 별칭
_PROMPTS_PATH = _BAKED_PROMPTS_PATH


def _active_path() -> Path:
    """편집·영구화용 활성 경로(볼륨). 없으면 baked 본을 한 번 복사해 시드."""
    p = datadir.prompts_dir() / "ec_prompts.json"
    if not p.exists() and _BAKED_PROMPTS_PATH.exists():
        try:
            p.write_text(
                _BAKED_PROMPTS_PATH.read_text(encoding="utf-8"), encoding="utf-8"
            )
        except Exception:
            pass
    return p


@lru_cache(maxsize=1)
def _load() -> dict[str, str]:
    """활성 JSON(볼륨, 없으면 baked)에서 프롬프트 로드. 누락 시 빠르게 실패."""
    path = _active_path()
    if not path.exists():
        path = _BAKED_PROMPTS_PATH
    if not path.exists():
        raise FileNotFoundError(f"EC 프롬프트 파일 없음: {path}")
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    required = ("STRUCTURE_PROMPT", "ANALYSIS_PROMPT", "GENERATION_PROMPT")
    missing = [k for k in required if k not in data]
    if missing:
        raise KeyError(f"EC 프롬프트 누락 키: {missing} (파일: {path})")
    return data


def get_prompt_raw(key: str) -> str:
    """관리자 편집용 — 특정 프롬프트 원문 반환(없으면 빈 문자열)."""
    return _load().get(key, "")


def save_prompt(key: str, content: str) -> None:
    """관리자 편집 저장 — 활성 JSON 갱신 후 캐시 무효화(즉시 적용)."""
    import os

    path = _active_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        data = dict(_load())
    data[key] = content
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    _load.cache_clear()


def get_structure_prompt() -> str:
    return _load()["STRUCTURE_PROMPT"]


def get_analysis_prompt() -> str:
    return _load()["ANALYSIS_PROMPT"]


def get_generation_prompt() -> str:
    return _load()["GENERATION_PROMPT"]


def get_ocr_prompt() -> str:
    """OCR 시스템 프롬프트 — 참고용. `cgr/parsers/image.py` 는 자체 한국어 프롬프트 사용."""
    return _load().get("OCR_PROMPT", "")


# ────────────────────────────────────────────────────────────────
# user 메시지 템플릿 — 기존 `server/services/openaiService.js` 와 동일하게 유지
# ────────────────────────────────────────────────────────────────


def build_structure_user_prompt(extracted_text: str) -> str:
    """`structure` 호출용 user 메시지."""
    return (
        f"다음 OCR 텍스트를 위 양식에 맞춰 구조화해주세요:\n\n{extracted_text}"
    )


def _current_minimum_wage_block() -> str:
    """DB(tb_yr_lwprc_wage) 에서 오늘 시행 중인 최저임금을 읽어 LLM 이 임금 항목
    검토 시 즉시 참조 가능한 블록 생성. DB 조회 실패 시 빈 문자열.
    테이블정의서 ai.tb_yr_lwprc_wage 조회 (기존: SQLite 뷰 v_minimum_wage_current).

    이 블록을 analyze user prompt 머리에 박아 system prompt 의 캐시 키를 흔들지 않으면서도
    "현행 최저임금 미달" 판정을 가능하게 한다. (generate 단계엔 이미 하드코딩 돼 있어
    분석 결과의 시급이 현행 최저임금 미만이면 LLM 이 보정함 — 그러나 analyze 가 먼저
    "부적절" 로 잡지 않으면 generate 가 보정 트리거를 안 받는다.)
    """
    try:
        from app.repositories import base as db

        with db.connect() as conn:
            row = conn.execute(
                """
                SELECT crtr_yr AS year, hrwg_amt AS hourly_amount,
                       monthly_cnvs_amt AS monthly_amount_209h, data_src_cn AS source
                FROM ai.tb_yr_lwprc_wage
                WHERE enfc_ymd <= to_char(current_date, 'YYYYMMDD')
                  AND (enfc_end_ymd IS NULL OR enfc_end_ymd >= to_char(current_date, 'YYYYMMDD'))
                ORDER BY crtr_yr DESC
                LIMIT 1
                """
            ).fetchone()
        if not row:
            return ""
        year = int(row["year"])
        hourly = int(row["hourly_amount"])
        monthly = int(row["monthly_amount_209h"])
        return (
            f"[현행 최저임금 — 임금 항목 검토 시 반드시 기준으로 적용]\n"
            f"- 적용 연도: {year}년\n"
            f"- 시급: **{hourly:,}원** (시간당)\n"
            f"- 월 환산: **{monthly:,}원** (주 40h × 4.345주 = 209h 기준)\n"
            f"- 출처: {row['source'] or '최저임금위원회'}\n"
            f"\n"
            f"⚠️ 시급이 {hourly:,}원 미만이거나, 월급을 209h 로 환산한 시급이 {hourly:,}원 미만이면\n"
            f"  반드시 임금 항목의 적절성을 '부적절' 로 판정하고, 발견내용에 환산 시급과 차액을 명시.\n"
            f"  (예: '시급 9,160원으로 기재 — {year}년 최저시급 {hourly:,}원 대비 1,160원 미달')\n"
        )
    except Exception:
        # DB 조회 실패해도 분석 자체는 계속 진행 — 단 최저임금 비교는 LLM 일반지식에 의존
        return ""


def build_analyze_user_prompt(
    structured_data: dict[str, Any],
    business_size: str,
    worker_types: list[str],
    legal_guidelines: str = "",
) -> str:
    """`analysis` 호출용 user 메시지.

    `legal_guidelines` 는 기존에서 RAG 검색으로 채우던 자리.
    풀 이식 1단계에서는 빈 문자열로 두고, 후속 단계에서 임베딩 매칭 채움.

    **현행 최저임금** 은 마스터 DB 에서 자동 주입 — 사용자가 폼에 따로 입력하지 않아도
    LLM 이 비교 기준을 얻는다.
    """
    bs = business_size or "미상"
    wt = ", ".join(worker_types) if worker_types else "미상"
    payload = json.dumps(structured_data, ensure_ascii=False, indent=2)
    mw_block = _current_minimum_wage_block()
    parts = [
        f"[사용자 정보]\n"
        f"- 사업장 규모: {bs}\n"
        f"- 근로자 유형: {wt}",
    ]
    if mw_block:
        parts.append(mw_block)
    if legal_guidelines:
        parts.append(f"[상세 법령 가이드라인(참고자료 DB)]\n{legal_guidelines}")
    parts.append(f"[구조화된 근로계약서 데이터]\n{payload}")
    return "\n\n".join(parts)


def build_generate_user_prompt(
    analysis_result: dict[str, Any],
    user_overrides: dict[str, str] | None = None,
) -> str:
    """`generation` 호출용 user 메시지.

    `user_overrides` 가 있으면(사용자가 결과 페이지에서 SuggestBlock 으로 직접 손본
    보완 표현) 별도 섹션으로 강조해 LLM 이 그 문구를 그대로 표준 계약서 본문에
    쓰도록 지시한다.
    """
    payload = json.dumps(analysis_result, ensure_ascii=False, indent=2)
    base = (
        f"다음 분석 결과를 바탕으로 완벽한 표준근로계약서를 작성해주세요:\n\n{payload}"
    )
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
        f"=== 사용자 직접 작성 보완 표현 (반드시 그대로 사용) ===\n"
        f"아래는 사용자가 결과 페이지에서 직접 손본 보완 표현입니다.\n"
        f"표준 계약서 본문 작성 시 해당 항목은 **사용자가 적은 표현을 그대로** 반영하고,\n"
        f"LLM 이 임의로 다시 쓰거나 줄이지 마세요.\n"
        f"\n"
        f"⚠️ **이 섹션의 표현은 위 시스템 작성 지침의 어떤 일반 규칙보다 우선합니다.**\n"
        f"  - 시스템 규칙 #6 (계약 시작일/종료일/계약서 작성일을 빈칸으로 두라) 도\n"
        f"    아래 항목에 사용자가 구체적 값을 직접 적었으면 그 값을 그대로 본문에 씁니다.\n"
        f"  - 임금·서명 등 다른 항목도 동일.\n"
        f"\n"
        f"{overrides_block}\n"
    )


# ────────────────────────────────────────────────────────────────
# 응답 정제 — 기존 `server/utils/jsonParser.js` 의 cleanJsonResponse 동등
# ────────────────────────────────────────────────────────────────


def clean_json_response(text: str) -> str:
    """LLM 응답에서 ```json fence·앞뒤 잡문 제거 후 JSON 본문만 반환."""
    if not text:
        return ""
    s = text.strip()
    # markdown fence 제거
    if s.startswith("```"):
        # 첫 줄 (```json 등) 과 마지막 ``` 잘라냄
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    # 첫 { 또는 [ 부터 마지막 } 또는 ] 까지 보존 (앞뒤 잡문 제거)
    first_obj = s.find("{")
    first_arr = s.find("[")
    starts = [x for x in (first_obj, first_arr) if x >= 0]
    if not starts:
        return s
    start = min(starts)
    end_obj = s.rfind("}")
    end_arr = s.rfind("]")
    end = max(end_obj, end_arr)
    if end < start:
        return s
    return s[start : end + 1]


def _repair_truncated_json(s: str) -> str:
    """잘린 JSON 의 끝을 닫아 파싱 가능하게 복구 시도.

    LLM 응답이 max_tokens 한도에서 잘리면 문자열·배열·객체가 닫히지 않은 상태로
    끝남. 보수적으로 다음을 시도:
      1) 닫히지 않은 string 안에 있으면 마지막 따옴표 안 문자를 잘라내고 " 닫기
      2) 그 다음 ], } 를 역순으로 적절한 개수만큼 추가
    실패해도 원본 그대로 반환 — 호출자가 default 로 떨어지게.
    """
    if not s or s[-1] in '}]':
        return s
    # 스택 추적 — string 안인지, 어떤 컨테이너 안인지
    in_string = False
    escape = False
    stack: list[str] = []
    last_unclosed_quote_idx = -1
    for i, ch in enumerate(s):
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
                last_unclosed_quote_idx = i
            elif ch in '{[':
                stack.append(ch)
            elif ch in '}]':
                if stack:
                    stack.pop()
    # 미완 string 이면 마지막 깨진 문자(혹은 trailing whitespace) 까지 잘라내고 " 추가
    if in_string and last_unclosed_quote_idx >= 0:
        # string 시작 위치 이후 부분에서 끝쪽 트림 — escape 가 잘리는 것 방지
        tail = s[last_unclosed_quote_idx + 1:]
        # 마지막 backslash 가 escape 미완성이면 잘라냄
        while tail.endswith('\\'):
            tail = tail[:-1]
        s = s[: last_unclosed_quote_idx + 1] + tail + '"'
    # 컨테이너 역순으로 닫기
    closers = {'{': '}', '[': ']'}
    while stack:
        opener = stack.pop()
        # trailing comma 가 있으면 제거 (불필요한 , 가 끝에 남아 있으면 파싱 실패)
        s = s.rstrip()
        if s.endswith(','):
            s = s[:-1]
        s += closers[opener]
    return s


def safe_json_parse(text: str, default: Any) -> Any:
    """JSON 파싱 실패 시 default 반환. truncated 응답은 자동 복구 시도."""
    cleaned = clean_json_response(text)
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        # 잘림 복구 한 번 더 시도
        try:
            repaired = _repair_truncated_json(cleaned)
            return json.loads(repaired)
        except (json.JSONDecodeError, ValueError):
            return default
