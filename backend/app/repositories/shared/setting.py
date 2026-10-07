#
# 관리자 설정 저장소 — admin_settings.json.
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.05.28      kimzion77   최초 생성
# 2026.10.02      이시영      구조 이행 (backend/cgr → backend/app)
#
# Author: kimzion77
# Since: 2026.05.28
#
"""관리자 설정 저장소 — admin_settings.json.

저장 형식:
{
  "embed_threshold_ok": 0.50,
  "embed_threshold_violation": 0.48,
  "prefilter_threshold": 0.30,
  "llm_model": "gpt-5.4-mini",
  "embed_model": "text-embedding-3-large",
  "master_db_version": "2026",         // "2025" | "2026"
  "default_workplace": {
    "shift_work_used": null,
    "osha_applicable": true,
    "chemical_handling": null,
    "workenv_measurement": null
  }
}

cgr.config / cgr.embed_matcher / cgr.master_db 가 호출 시점에 이 파일을 조회.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]  # app/repositories/shared/x.py -> backend 루트


def settings_path() -> Path:
    p = _project_root() / "data" / "admin_settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# 기본값 (저장된 설정이 없을 때)
DEFAULTS: dict[str, Any] = {
    "embed_threshold_ok": 0.50,
    "embed_threshold_violation": 0.48,
    "prefilter_threshold": 0.30,
    "llm_model": "gpt-5.4-mini",
    "embed_model": "text-embedding-3-large",
    "master_db_version": "2026",
    "default_workplace": {
        "shift_work_used": None,
        "osha_applicable": True,
        "chemical_handling": None,
        "workenv_measurement": None,
    },
}


def load() -> dict[str, Any]:
    """현재 설정 로드. 파일 없거나 손상 시 DEFAULTS 반환 (병합)."""
    p = settings_path()
    if not p.exists():
        return dict(DEFAULTS)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        # DEFAULTS 와 병합 (누락 키 보충)
        merged = dict(DEFAULTS)
        merged.update(data)
        # 중첩 dict 도 보강
        if "default_workplace" in DEFAULTS and isinstance(merged.get("default_workplace"), dict):
            wp = dict(DEFAULTS["default_workplace"])
            wp.update(merged["default_workplace"])
            merged["default_workplace"] = wp
        return merged
    except Exception:
        return dict(DEFAULTS)


def save(settings: dict[str, Any], backup: bool = True) -> Path | None:
    """설정 저장 (원자적 쓰기). backup=True 시 backups/<ts>_settings/ 보존.

    Returns:
        backup_dir 경로 또는 None (백업 미실행)
    """
    p = settings_path()
    backup_dir = None
    if backup and p.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = _project_root() / "backups" / f"{ts}_settings"
        backup_dir.mkdir(parents=True, exist_ok=True)
        try:
            (backup_dir / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass

    # 원자적 쓰기
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)
    return backup_dir


def get(key: str, default: Any = None) -> Any:
    """단일 키 조회 헬퍼 (cgr.config 등에서 사용)."""
    s = load()
    return s.get(key, default)


def update(patch: dict[str, Any], backup: bool = True) -> Path | None:
    """부분 업데이트 (load → patch → save)."""
    s = load()
    s.update(patch)
    return save(s, backup=backup)
