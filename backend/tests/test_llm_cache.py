"""LLM 캐시 테스트 — '같은 입력 → 같은 출력' 재현성의 물리적 토대."""
from __future__ import annotations

from app.integrations.llm import cache as llm_cache


SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}}


def test_make_key_deterministic():
    k1 = llm_cache.make_key("sys", "user", SCHEMA, "gpt-x")
    k2 = llm_cache.make_key("sys", "user", SCHEMA, "gpt-x")
    assert k1 == k2
    assert len(k1) == 24


def test_make_key_sensitive_to_each_component():
    base = llm_cache.make_key("sys", "user", SCHEMA, "gpt-x")
    assert llm_cache.make_key("sys2", "user", SCHEMA, "gpt-x") != base   # system
    assert llm_cache.make_key("sys", "user2", SCHEMA, "gpt-x") != base   # user
    assert llm_cache.make_key("sys", "user", {"b": 1}, "gpt-x") != base  # schema
    assert llm_cache.make_key("sys", "user", SCHEMA, "gpt-y") != base    # model
    # 프롬프트를 바꾸면 캐시가 자동 무효화되는 근거


def test_schema_key_order_irrelevant():
    """dict 키 순서는 결과에 영향 없어야 함 (sort_keys 직렬화)."""
    a = {"x": 1, "y": 2}
    b = {"y": 2, "x": 1}
    assert llm_cache.make_key("s", "u", a, "m") == llm_cache.make_key("s", "u", b, "m")


def test_put_get_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_cache, "CACHE_DIR", tmp_path)
    monkeypatch.delenv("CGR_DISABLE_CACHE", raising=False)  # conftest 격리 해제(임시 디렉터리라 안전)
    key = llm_cache.make_key("s", "u", SCHEMA, "m")
    payload = {"결과": "판정", "점수": 1}
    llm_cache.put(key, payload)
    assert llm_cache.get(key) == payload


def test_disabled_env_blocks_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_cache, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("CGR_DISABLE_CACHE", "1")
    key = llm_cache.make_key("s", "u", SCHEMA, "m")
    llm_cache.put(key, {"a": 1})
    assert llm_cache.get(key) is None
    assert not list(tmp_path.glob("*.json"))
