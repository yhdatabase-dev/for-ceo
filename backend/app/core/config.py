"""키·모델 resolver.

우선순위:
  1. 명시 파라미터
  2. 환경변수 (OPENAI_API_KEY, OPENAI_MODEL, OPENAI_EMBEDDING_MODEL)
  3. backend/.streamlit/secrets.toml 의 openai_api_key
  4. 관리자 대시보드 설정 (data/admin_settings.json)
  5. 모듈 기본값
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

DEFAULT_LLM_MODEL = "gpt-5.4-mini"
DEFAULT_EMBED_MODEL = "text-embedding-3-large"
DEFAULT_EMBED_DIM = 1024  # text-embedding-3-large 는 truncate 지원 (default 3072)


def _load_admin_setting(key: str) -> str:
    """admin_settings.json 에서 설정값 조회. 실패해도 silent."""
    try:
        from app.repositories.shared.setting import get as _admin_get
        v = _admin_get(key)
        return str(v) if v else ""
    except Exception:
        return ""


def _load_secrets_attr(key: str) -> str:
    """`backend/.streamlit/secrets.toml` 에서 키 조회 (있으면).

    OpenAI API 키를 secrets.toml 에 보관해 dev 환경에서 한 곳에서 관리하기 위함.
    Streamlit 의 secrets 와 같은 파일을 공유하는 게 운영 단순화에 유리.
    """
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        return ""
    p = Path(__file__).resolve().parents[2] / ".streamlit" / "secrets.toml"
    if not p.exists():
        return ""
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
        v = data.get(key)
        return str(v) if v else ""
    except Exception:
        return ""


def get_api_key(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    env = os.environ.get("OPENAI_API_KEY")
    if env:
        return env
    # secrets.toml 의 openai_api_key (dev 편의)
    return _load_secrets_attr("openai_api_key")


def get_llm_model(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    env = os.environ.get("OPENAI_MODEL")
    if env:
        return env
    admin = _load_admin_setting("llm_model")
    if admin:
        return admin
    return DEFAULT_LLM_MODEL


def get_embed_model(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    env = os.environ.get("OPENAI_EMBEDDING_MODEL")
    if env:
        return env
    admin = _load_admin_setting("embed_model")
    if admin:
        return admin
    return DEFAULT_EMBED_MODEL


def get_embed_dim(explicit: int | None = None) -> int:
    if explicit:
        return explicit
    env = os.environ.get("OPENAI_EMBEDDING_DIM")
    if env:
        try:
            return int(env)
        except ValueError:
            pass
    return DEFAULT_EMBED_DIM


def assert_ready() -> None:
    """키 누락 시 친절히 안내."""
    if not get_api_key():
        from app.core.logging import get_logger

        get_logger(__name__).error(
            "[설정 오류] OpenAI API 키 없음 — OPENAI_API_KEY 환경변수 또는 "
            "backend/.streamlit/secrets.toml 의 openai_api_key 로 설정"
        )
        raise SystemExit(2)
