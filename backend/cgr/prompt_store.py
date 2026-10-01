"""편집형 프롬프트 레지스트리 — 관리자 대시보드에서 보고/수정하고 즉시 적용.

설계
- **override-or-default**: 각 프롬프트는 datadir.prompts_dir()/<key>.txt 에 override 가
  있으면 그 내용을, 없으면 코드의 기본 상수를 쓴다. override 가 비어 있으면 동작은
  기존과 동일 — 안전한 폴백.
- 저장 시 메모리 캐시 갱신 + 관련 lru_cache 무효화 → **재배포 없이 즉시 적용**.
- EC 4단계(ec_prompts.json)·extractor.md·explainer.md 는 이미 외부 파일이라 각 모듈이
  관리하고, 본 레지스트리는 통합 목록/저장 진입점만 제공한다.

prompts_dir() 은 Fly 볼륨 위라 편집 내용이 배포 후에도 유지된다.
"""
from __future__ import annotations

from typing import Any, Callable

from cgr import datadir

# 인라인 프롬프트 텍스트 override 캐시 (key -> 내용)
_text_cache: dict[str, str] = {}


def _override_path(key: str):
    return datadir.prompts_dir() / f"{key}.txt"


def get_or_default(key: str, default: str) -> str:
    """인라인 프롬프트용 — override 파일 있으면 그 내용, 없으면 코드 기본값."""
    if key in _text_cache:
        return _text_cache[key]
    p = _override_path(key)
    if p.exists():
        try:
            txt = p.read_text(encoding="utf-8")
            _text_cache[key] = txt
            return txt
        except Exception:
            pass
    return default


def set_text(key: str, content: str) -> None:
    p = _override_path(key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    _text_cache[key] = content


def has_override(key: str) -> bool:
    return _override_path(key).exists()


# ─── 통합 레지스트리 (관리자 목록/조회/저장) ──────────────────
# 각 항목: key, label, group, read()->str, write(str)->None
# read/write 는 순환 import 방지를 위해 호출 시점에 모듈을 lazy import 한다.


def _text_entry(key: str, label: str, group: str, default_getter: Callable[[], str]):
    """인라인 텍스트 override 항목."""

    def read() -> str:
        return get_or_default(key, default_getter())

    def write(content: str) -> None:
        set_text(key, content)
        _invalidate_caches()

    return {"key": key, "label": label, "group": group, "read": read, "write": write}


def _invalidate_caches() -> None:
    """프롬프트 저장 후 관련 lru_cache 무효화 — 즉시 적용."""
    try:
        from cgr.ec import prompts as ecp

        ecp._load.cache_clear()
        ecp.get_chat_system_prompt.cache_clear()
    except Exception:
        pass


def _build_registry() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    # 1) 가이드 챗봇 (인라인)
    def _guide_default() -> str:
        from cgr.api.routes import guide

        return guide._GUIDE_CHAT_SYSTEM

    entries.append(_text_entry("guide_chat", "가이드 챗봇", "챗봇", _guide_default))

    # 2) 근로계약서 챗봇 base (인라인)
    def _ec_chat_default() -> str:
        from cgr.ec import prompts as ecp

        return ecp._CHAT_SYSTEM_BASE

    entries.append(_text_entry("ec_chat_base", "근로계약서 챗봇", "근로계약서", _ec_chat_default))

    # 7) 선택 노출 판정 (인라인)
    def _optional_default() -> str:
        from cgr import optional_display as od

        return getattr(od, "_SYSTEM_PROMPT", "")

    entries.append(_text_entry("optional_display", "선택 노출 판정", "기타", _optional_default))

    # 7b) 취업규칙 — 추출/설명 (인라인 + .md override)
    def _wr_extractor_default() -> str:
        from cgr import extractor

        return extractor._SYSTEM_PROMPT

    entries.append(_text_entry("wr_extractor", "취업규칙 조항 추출", "취업규칙", _wr_extractor_default))

    def _wr_explainer_default() -> str:
        from cgr import explainer

        return explainer._SYSTEM_PROMPT

    entries.append(_text_entry("wr_explainer", "취업규칙 시정문구 설명", "취업규칙", _wr_explainer_default))

    # 8~10) EC 4단계 (ec_prompts.json — 외부 파일, 모듈이 직접 관리)
    try:
        from cgr.ec import prompts as ecp

        for jkey, label in (
            ("STRUCTURE_PROMPT", "근로계약서 구조화"),
            ("ANALYSIS_PROMPT", "근로계약서 분석(33매핑)"),
            ("GENERATION_PROMPT", "근로계약서 표준 생성"),
        ):

            def _mk(jk: str):
                def read() -> str:
                    return ecp.get_prompt_raw(jk)

                def write(content: str) -> None:
                    ecp.save_prompt(jk, content)
                    _invalidate_caches()

                return read, write

            r, w = _mk(jkey)
            entries.append(
                {"key": f"ec::{jkey}", "label": label, "group": "근로계약서", "read": r, "write": w}
            )
    except Exception:
        pass

    return entries


def list_prompts(include_content: bool = True) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in _build_registry():
        item: dict[str, Any] = {"key": e["key"], "label": e["label"], "group": e["group"]}
        if include_content:
            try:
                item["content"] = e["read"]()
            except Exception as ex:
                item["content"] = ""
                item["error"] = str(ex)
        out.append(item)
    return out


def get_prompt(key: str) -> str | None:
    for e in _build_registry():
        if e["key"] == key:
            return e["read"]()
    return None


def save_prompt(key: str, content: str) -> bool:
    for e in _build_registry():
        if e["key"] == key:
            e["write"](content)
            return True
    return False
