#
# 슬롯 카탈로그 YAML 저장 + 자동 백업 + 캐시 무효화.
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
"""슬롯 카탈로그 YAML 저장 + 자동 백업 + 캐시 무효화.

핵심 흐름:
  1. 백업: backups/<ts>_slot_edit_<slot_id>/atomic_slots_v0.yaml 로 원본 복사
  2. 원자적 저장: tmp 파일에 yaml.safe_dump → os.replace
  3. 캐시 무효화: cgr.catalog._load_cached.cache_clear()

YAML 보존 규칙:
  - allow_unicode=True (한국어 그대로)
  - sort_keys=False (필드 순서 보존)
  - default_flow_style=False (블록 스타일)
  - width=4096 (긴 한국어 줄 wrap 방지)
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]  # app/repositories/wr/x.py -> backend 루트


def slots_yaml_path() -> Path:
    return _project_root() / "data" / "slots" / "atomic_slots_v0.yaml"


def backups_root() -> Path:
    p = _project_root() / "backups"
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_raw() -> dict:
    """원본 YAML 을 dict 로 그대로 로드 (편집·재저장용)."""
    return yaml.safe_load(slots_yaml_path().read_text(encoding="utf-8"))


def find_slot_index(parsed: dict, slot_id: str) -> int:
    """parsed['slots'] 에서 slot_id 의 인덱스. 없으면 -1."""
    for i, s in enumerate(parsed.get("slots", [])):
        if s.get("slot_id") == slot_id:
            return i
    return -1


def make_backup(slot_id: str, reason: str = "edit") -> Path:
    """원본 YAML 을 backups/<ts>_slot_<reason>_<slot_id>/atomic_slots_v0.yaml 로 복사.

    Returns: 백업 디렉토리 경로
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_slot = slot_id.replace("/", "_").replace("\\", "_") if slot_id else "all"
    backup_dir = backups_root() / f"{ts}_slot_{reason}_{safe_slot}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    src = slots_yaml_path()
    dst = backup_dir / src.name
    shutil.copy2(src, dst)
    return backup_dir


def save_atomic(parsed: dict) -> None:
    """parsed dict 를 원자적 쓰기 패턴으로 YAML 저장.

    tmp 파일에 dump 후 os.replace (POSIX·NTFS 모두 원자성 보장).
    """
    target = slots_yaml_path()
    tmp = target.with_suffix(".yaml.tmp")
    tmp.write_text(
        yaml.safe_dump(
            parsed,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=4096,
        ),
        encoding="utf-8",
    )
    os.replace(tmp, target)


def invalidate_catalog_cache() -> None:
    """cgr.catalog 의 lru_cache 무효화 — 다음 검토에서 재로드."""
    try:
        from app.repositories.wr.catalog import _load_cached
        _load_cached.cache_clear()
    except Exception:
        pass


def save_slot_edit(slot_id: str, new_slot: dict) -> Path:
    """단일 슬롯 편집 — 백업 + 슬롯 교체 + 저장 + 캐시 무효화.

    Args:
        slot_id: 편집 대상 slot_id
        new_slot: 새 슬롯 dict (전체 필드)

    Returns:
        backup_dir 경로

    Raises:
        ValueError: slot_id 가 카탈로그에 없으면
    """
    backup_dir = make_backup(slot_id, "edit")
    parsed = load_raw()
    idx = find_slot_index(parsed, slot_id)
    if idx < 0:
        raise ValueError(f"슬롯 {slot_id} 가 카탈로그에 없습니다.")
    parsed["slots"][idx] = new_slot
    save_atomic(parsed)
    invalidate_catalog_cache()
    return backup_dir


def save_bulk_edit(updates: dict[str, dict], reason: str = "bulk") -> Path:
    """다수 슬롯 일괄 편집 — 백업 1회 + 모든 슬롯 교체 + 저장.

    Args:
        updates: {slot_id: new_slot_dict, ...}
        reason: 백업 디렉토리 라벨 (bulk_severity, bulk_threshold 등)

    Returns:
        backup_dir 경로
    """
    backup_dir = make_backup(f"{len(updates)}slots", reason)
    parsed = load_raw()
    missing = []
    for sid, new_slot in updates.items():
        idx = find_slot_index(parsed, sid)
        if idx < 0:
            missing.append(sid)
            continue
        parsed["slots"][idx] = new_slot
    if missing:
        raise ValueError(f"카탈로그에 없는 slot_id: {missing}")
    save_atomic(parsed)
    invalidate_catalog_cache()
    return backup_dir


def slot_to_yaml_block(slot_dict: dict) -> str:
    """단일 슬롯 dict 를 YAML 텍스트로 직렬화 (diff 미리보기용)."""
    return yaml.safe_dump(
        [slot_dict],
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=4096,
    )
