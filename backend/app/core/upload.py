#
# 업로드 추적 — 메타만 기록한다. 원본 파일은 저장하지 않는다(처리용 임시 파일은 처리 후 삭제).
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.06.22      kimzion77   최초 생성
# 2026.10.02      이시영      구조 이행 (backend/cgr → backend/app)
# 2026.10.07      이시영      환경설정 통합 (루트 .env·config.py), mock LLM 추가
# 2026.10.07      이시영      화면 경로 /cgr·features 구조 이동, sync API 삭제, 업로드 원본 미저장
# 2026.10.07      이시영      검토번호 서버 발급, 변경 사유 주석 추가
#
# Author: kimzion77
# Since: 2026.06.22
#
"""업로드 추적 — 메타만 기록한다. 원본 파일은 저장하지 않는다(처리용 임시 파일은 처리 후 삭제).

프로그램명세서 WEB-P02-001: "올린 사진은 검토가 끝나면 바로 삭제" (기존: 원본 파일을 data/uploads 에 보관).

- 메타는 app.tb_file_uld_rcd (analytics.add_upload).
- 업로더는 **익명화**: 원시 IP 를 저장하지 않고 IP+UA+날짜 단방향 해시(visitor)만 남긴다.
- 보관기간(retention) 초과분은 analytics.cleanup_old_uploads 로 자동 삭제.
- 실패해도 silent — 업로드/추출 본 흐름을 절대 막지 않는다.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core import config
from app.core.logging import get_logger
from app.repositories.shared import analytics

log = get_logger(__name__)


# 허용 업로드 확장자 — 지원 문서·이미지만 (시큐어코딩: 입력 데이터 검증)
ALLOWED_UPLOAD_EXTS = {
    "png", "jpg", "jpeg", "gif", "bmp", "tif", "tiff", "webp", "heic", "heif",
    "pdf", "docx", "doc", "hwp", "hwpx", "txt",
}
# 개발표준정의서 Directory 구조: 환경설정 값은 환경변수로 주입하고 /app/core/config.py 한 곳에서만 읽는다 (기존: 20MB 코드 고정)
MAX_UPLOAD_BYTES = config.get_max_upload_mb() * 1024 * 1024  # CGR_MAX_UPLOAD_MB (운영 리버스프록시의 client_max_body_size 와 함께)

# 확장자별 매직바이트 서명 — 확장자만 바꿔치기한 위장 파일 차단 (내용 기반 2차 검증).
# 서명이 하나라도 일치하면 통과. txt/heic 계열은 별도 처리(아래).
_MAGIC_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "png": (b"\x89PNG",),
    "jpg": (b"\xff\xd8",),
    "jpeg": (b"\xff\xd8",),
    "gif": (b"GIF8",),
    "bmp": (b"BM",),
    "webp": (b"RIFF",),
    "tif": (b"II*\x00", b"MM\x00*"),
    "tiff": (b"II*\x00", b"MM\x00*"),
    "pdf": (b"%PDF",),
    "docx": (b"PK\x03\x04",),   # OOXML zip
    "hwpx": (b"PK\x03\x04",),   # HWPX zip
    "doc": (b"\xd0\xcf\x11\xe0",),  # OLE2
    "hwp": (b"\xd0\xcf\x11\xe0",),  # HWP 5.x OLE2
}


def _magic_ok(ext: str, content: bytes) -> bool:
    """선언된 확장자와 파일 내용(매직바이트)이 부합하는지. 모르는 확장자는 통과."""
    if ext in ("heic", "heif"):
        # ISO-BMFF: 4바이트 크기 + 'ftyp'
        return len(content) >= 12 and content[4:8] == b"ftyp"
    sigs = _MAGIC_SIGNATURES.get(ext)
    if not sigs:  # txt 등 — 서명 없는 형식은 내용 검사 생략
        return True
    return any(content.startswith(s) for s in sigs)


def validate_upload(filename: str, content: bytes) -> None:
    """업로드 파일 검증 — 빈/과대/허용외 형식/내용 불일치 거부. 위반 시 HTTPException."""
    from fastapi import HTTPException

    size = len(content or b"")
    if size == 0:
        raise HTTPException(status_code=400, detail="빈 파일은 업로드할 수 없어요.")
    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"파일이 너무 큽니다 (최대 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB).",
        )
    ext = Path(filename or "").suffix.lower().lstrip(".")
    if ext and ext not in ALLOWED_UPLOAD_EXTS:
        raise HTTPException(
            status_code=400, detail=f"허용되지 않은 파일 형식이에요 (.{ext})."
        )
    if ext and not _magic_ok(ext, content):
        raise HTTPException(
            status_code=400,
            detail=f"파일 내용이 .{ext} 형식과 일치하지 않아요. 원본 파일 그대로 올려주세요.",
        )


def anon_visitor(request: Any | None) -> str:
    """익명 방문자 해시 — 원시 IP 저장 안 함(IP+UA+날짜 salt 단방향 해시 16자)."""
    ip = ua = ""
    try:
        if request is not None:
            client = getattr(request, "client", None)
            ip = getattr(client, "host", "") or ""
            ua = request.headers.get("user-agent", "") or ""
    except Exception:
        pass
    day = datetime.now().strftime("%Y%m%d")
    raw = f"{ip}|{ua}|{day}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def record_upload(
    *,
    content: bytes,
    filename: str,
    mime: str,
    service: str,
    request: Any | None = None,
    case_id: str | None = None,
) -> int | None:
    """업로드 1건 메타 기록. 원본 파일은 저장하지 않는다. 절대 예외를 밖으로 던지지 않는다.

    저장된 업로드 레코드 id 를 반환(실패 시 None) — 상호작용 로그와 연결하는 데 쓴다.
    """
    try:
        ext = (Path(filename or "").suffix.lower().lstrip(".")) or "bin"
        return analytics.add_upload(
            service=service,
            filename=filename or "",
            size=len(content or b""),
            mime=mime or "",
            ext=ext,
            visitor=anon_visitor(request),
            case_id=case_id,
            stored_path="",
        )
    except Exception as e:
        log.warning("업로드 기록 실패 (본 흐름 계속): %s: %s", type(e).__name__, e)
        return None
