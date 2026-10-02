"""고용노동부 등 정부 사이트에서 표준 양식 파일을 받아 `backend/data/forms/` 에 저장.

Phase 18 — 사용자가 우리 서비스에서 직접 양식을 다운받을 수 있도록.

전략:
  1) **알려진 직링크** 가 있는 양식은 그 URL 에서 직접 다운로드 (가장 빠르고 안정).
  2) 직링크 없는 양식은 검색 URL 만 DB 에 남고, 본 스크립트는 skip.
  3) 받은 파일은 `<code>.<ext>` 로 저장 + DB 의 `local_filename` 갱신.
  4) **best-effort** — 실패해도 외부 URL 폴백이 살아있어 사용자 경험 보존.

운영자 워크플로:
  - 자동 받은 양식 + 수동 추가 양식이 같은 폴더에 공존
  - 수동 추가: `data/forms/<code>.<ext>` 두고 본 스크립트 `--reindex` 옵션으로 DB 동기화
  - 검증 — 사용자 다운로드 시 백엔드가 파일 존재 확인 후 stream

실행:
  cd backend
  python scripts/fetch_forms.py                # 알려진 직링크 모두 시도
  python scripts/fetch_forms.py --reindex      # data/forms/ 폴더 → DB 동기화 (수동 추가 반영)
  python scripts/fetch_forms.py --code FRM001  # 특정 코드만
"""
from __future__ import annotations

import argparse
import mimetypes
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.repositories import base as db  # noqa: E402

FORMS_DIR = ROOT / "data" / "forms"
FORMS_DIR.mkdir(parents=True, exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 "
    "(영세사업장 자율점검 서비스 / fetch_forms.py)"
)

# ════════════════════════════════════════════════════════════════
# 알려진 양식 직링크 — 정부 사이트에서 안정적으로 받을 수 있는 것만
#
# 각 정부 사이트의 자료실 게시판 구조가 다 달라 일반화된 크롤링은 어려움.
# 대신 운영자가 확인한 직접 다운로드 URL 을 코드별로 매핑.
# URL 이 죽으면 같은 자료실 다른 게시물로 갱신.
# ════════════════════════════════════════════════════════════════
DIRECT_LINKS: dict[str, str] = {
    # 고용노동부 표준근로계약서 모음 게시물의 첨부파일 (각 직종별)
    # 시간이 지나 URL 이 바뀔 수 있어 운영자가 자료실에서 직접 받는 게 가장 안전.
    # 비어 있으면 본 스크립트는 skip — 외부 URL 폴백.
}


def _ext_from_url_or_headers(url: str, headers: dict) -> str:
    """확장자 추정 — Content-Disposition · Content-Type · URL 순."""
    cd = headers.get("Content-Disposition", "")
    # filename="..." 또는 filename*=UTF-8''...
    import re

    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", cd, re.I)
    if m:
        name = m.group(1)
        try:
            from urllib.parse import unquote
            name = unquote(name)
        except Exception:
            pass
        suffix = Path(name).suffix
        if suffix:
            return suffix.lower()
    # Content-Type
    ct = (headers.get("Content-Type") or "").split(";")[0].strip().lower()
    by_ct = {
        "application/x-hwp": ".hwp",
        "application/haansofthwp": ".hwp",
        "application/vnd.hancom.hwp": ".hwp",
        "application/pdf": ".pdf",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.ms-excel": ".xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/zip": ".zip",
        "application/x-zip-compressed": ".zip",
    }
    if ct in by_ct:
        return by_ct[ct]
    # URL path
    suffix = Path(urlparse(url).path).suffix
    if suffix:
        return suffix.lower()
    return ".bin"


def _mime_from_ext(ext: str) -> str:
    by_ext = {
        ".hwp": "application/x-hwp",
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": (
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        ".xls": "application/vnd.ms-excel",
        ".xlsx": (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        ".zip": "application/zip",
    }
    return by_ext.get(ext.lower(), mimetypes.guess_type(f"x{ext}")[0] or "application/octet-stream")


def fetch_one(code: str, url: str, timeout: float = 30.0) -> dict | None:
    """직링크에서 파일 받아 forms/<code>.<ext> 로 저장. 결과 메타 반환."""
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": UA},
            allow_redirects=True,
            stream=True,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"  [FAIL] {code}: 다운로드 실패 — {e}")
        return None

    ext = _ext_from_url_or_headers(url, dict(resp.headers))
    if ext == ".html" or ext == ".htm":
        # 게시판 페이지를 받은 경우 — 첨부파일이 아니라 HTML.
        # 진짜 파일 직링크가 아니라는 신호.
        print(f"  [SKIP] {code}: HTML 페이지 응답 — 게시판 인 듯, 첨부 직링크 필요")
        return None

    filename = f"{code}{ext}"
    path = FORMS_DIR / filename
    size = 0
    with path.open("wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
                size += len(chunk)

    if size < 1024:  # 1KB 미만 — 정상 양식 파일일 가능성 낮음
        print(f"  [WARN] {code}: 파일 크기 {size}B (너무 작음 — 에러 페이지 가능)")

    mime = _mime_from_ext(ext)
    return {
        "filename": filename,
        "mime": mime,
        "size": size,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def update_db_local(code: str, meta: dict) -> None:
    with db.connect() as c:
        c.execute(
            "UPDATE form_template SET "
            "  local_filename = ?, local_mime = ?, local_size = ?, fetched_at = ? "
            "WHERE code = ?",
            (meta["filename"], meta["mime"], meta["size"], meta["fetched_at"], code),
        )


def reindex_folder() -> int:
    """`data/forms/<code>.<ext>` 파일을 스캔해 DB 의 local_filename 갱신.

    운영자가 수동으로 양식 파일을 폴더에 두면 자동 인식.
    """
    n = 0
    with db.connect() as c:
        rows = c.execute(
            "SELECT code FROM form_template WHERE excluded_from_service = 0"
        ).fetchall()
        for r in rows:
            code = r["code"]
            # 같은 코드로 시작하는 파일 찾기 — 첫 번째 사용
            matches = sorted(FORMS_DIR.glob(f"{code}.*"))
            if not matches:
                continue
            path = matches[0]
            ext = path.suffix.lower()
            mime = _mime_from_ext(ext)
            size = path.stat().st_size
            c.execute(
                "UPDATE form_template SET "
                "  local_filename = ?, local_mime = ?, local_size = ?, "
                "  fetched_at = COALESCE(fetched_at, ?) "
                "WHERE code = ?",
                (
                    path.name,
                    mime,
                    size,
                    datetime.now(timezone.utc).isoformat(),
                    code,
                ),
            )
            n += 1
            print(f"  [OK]   {code} ← {path.name} ({size:,} B)")
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--code",
        help="특정 양식 코드만 받기 (예: FRM001)",
    )
    ap.add_argument(
        "--reindex",
        action="store_true",
        help="data/forms/ 폴더 스캔 → DB local_filename 동기화 (네트워크 호출 없음)",
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="요청 간 대기 시간 (초). 정부 사이트 부하 배려.",
    )
    args = ap.parse_args()

    if args.reindex:
        print(f"[reindex] {FORMS_DIR}")
        n = reindex_folder()
        print(f"\n총 {n}건 동기화 완료.")
        return 0

    if not DIRECT_LINKS:
        print(
            "DIRECT_LINKS 비어있음 — 운영자가 정부 자료실에서 직링크 채워야 자동 다운로드 가능.\n"
            "현재는 외부 URL 폴백 (download_url) 으로 사용자가 클릭 시 정부 사이트로 redirect 됩니다.\n"
            "\n"
            "수동 추가 워크플로:\n"
            "  1) data/forms/<코드>.<확장자> 에 파일 두기 (예: FRM001.hwp)\n"
            "  2) python scripts/fetch_forms.py --reindex 실행\n"
            "  3) /api/v1/guide/forms 응답의 has_local=true 확인\n"
        )
        return 0

    targets = (
        {args.code: DIRECT_LINKS[args.code]}
        if args.code
        else DIRECT_LINKS
    )
    if args.code and args.code not in DIRECT_LINKS:
        print(f"DIRECT_LINKS 에 {args.code} 없음 — 알려진 직링크 미보유")
        return 1

    print(f"[fetch] {len(targets)}건 시도 → {FORMS_DIR}")
    ok = 0
    fail = 0
    for code, url in targets.items():
        print(f"  · {code} ← {url[:80]}")
        meta = fetch_one(code, url)
        if meta:
            update_db_local(code, meta)
            print(
                f"  [OK]   {code} → {meta['filename']} ({meta['size']:,} B) · {meta['mime']}"
            )
            ok += 1
        else:
            fail += 1
        time.sleep(args.delay)

    print(f"\n총 {ok}건 성공 · {fail}건 실패")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
