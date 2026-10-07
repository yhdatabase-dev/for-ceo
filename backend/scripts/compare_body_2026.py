#
# 2025 마스터 DB 본문(D) vs 2026 HWP 본문 — 전수 비교 검토표 생성.
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
"""2025 마스터 DB 본문(D) vs 2026 HWP 본문 — 전수 비교 검토표 생성.

- 목적: 어느 조가 진짜로 본문이 바뀌었는지, 어떻게 바뀌었는지(unified diff) 한눈에 보여주는
  자료를 만든다. 셀 갱신은 이 단계에선 하지 않음 — 사용자 검토 후 후속 단계.
- 산출물: mvp/output/2026_body_diff.md
"""
from __future__ import annotations

import difflib
import io
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MVP_ROOT = SCRIPT_DIR.parent
if str(MVP_ROOT) not in sys.path:
    sys.path.insert(0, str(MVP_ROOT))

from app.repositories.wr.master import get_master_db
from app.integrations.parsers.hwp import parse_hwp

# refresh_law_penalty_2026 import 가 win32 stdout 을 utf-8 로 재설정하므로 여기선 별도 처리 불필요
from mvp.scripts.refresh_law_penalty_2026 import (
    DEFAULT_HWP,
    DEFAULT_MASTER,
    extract_body_region,
    split_into_articles,
)


_HEADING = re.compile(r"^제\s*\d+\s*조\s*\(.*?\)\s*")
_GUIDE_HEAD = re.compile(r"^\[\s*(필수|선택)")  # [필수] [선택] [필수, 선택] [선택,필수] 모두 매칭


def strict_body_from_hwp_block(block: str) -> str:
    """HWP 조문 블록에서 [필수]/[선택]/☞(참고)/◈ 아래는 잘라내고
    첫 줄의 '제N조(제목)' 헤딩 prefix도 제거한 '본문'만 반환.
    """
    lines = block.split("\n")
    if lines:
        m = _HEADING.match(lines[0])
        if m:
            lines[0] = lines[0][m.end():]
    cut = len(lines)
    for i, ln in enumerate(lines):
        s = ln.strip()
        if _GUIDE_HEAD.match(s) or s.startswith("☞") or s.startswith("◈"):
            cut = i
            break
    return "\n".join(lines[:cut]).strip()


def normalize_for_compare(s: str) -> str:
    """비교용 — 공백·전각 기호 정규화. 사람이 읽는 셀 값이 아닌 비교 키."""
    if not s:
        return ""
    # 전각/유사 기호 통일
    s = s.replace("｢", "「").replace("｣", "」")
    s = s.replace("‧", "·").replace("∙", "·").replace("․", ".")
    # 공백 모두 제거 (의미 없는 공백 차이 무시)
    s = re.sub(r"\s+", "", s)
    return s


def render_unified_diff(a: str, b: str) -> str:
    a_lines = a.splitlines()
    b_lines = b.splitlines()
    diff = list(
        difflib.unified_diff(
            a_lines, b_lines,
            fromfile="2025 master D",
            tofile="2026 HWP body",
            lineterm="",
            n=2,
        )
    )
    return "\n".join(diff) if diff else "(unified diff 없음 — 정규화 후에만 차이)"


def main() -> int:
    out_md = MVP_ROOT / "output" / "2026_body_diff.md"

    print(f"master 로드: {DEFAULT_MASTER}")
    db = get_master_db(str(DEFAULT_MASTER))

    print(f"HWP 파싱: {DEFAULT_HWP}")
    arts2026 = split_into_articles(extract_body_region(parse_hwp(DEFAULT_HWP)))

    diffs: list[dict] = []
    for n in range(1, 99):
        d_2025 = db.body(n) or ""
        d_2026 = strict_body_from_hwp_block(arts2026[n])
        if normalize_for_compare(d_2025) == normalize_for_compare(d_2026):
            continue
        diffs.append({
            "no": n,
            "title": db.title(n),
            "scope": (db._cell(n, "scope") or ""),
            "d_2025": d_2025,
            "d_2026": d_2026,
        })

    print(f"본문 차이가 있는 조: {len(diffs)}개")

    out_md.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# 2026 표준취업규칙 본문(D) — 2025 master 대비 차이 검토표\n")
    lines.append("**경고: 이 검토표는 HWP 파일 안의 본문만 비교합니다.**")
    lines.append("HWP 배포 이후의 추가 입법 개정(예: 난임치료휴가 4일 유급 등)은 이 표에 잡히지 않습니다.")
    lines.append(f"본문 차이 발견 조: **{len(diffs)}개**\n")
    lines.append("아래 각 조 별로 **공백·기호 정규화 후에도 다른** 부분만 unified diff로 표시.\n")
    lines.append("---\n")

    for d in diffs:
        lines.append(f"## 제{d['no']}조 ({d['title']}) — {d['scope'] or '구분미기재'}")
        lines.append("")
        lines.append("### 2025 master D")
        lines.append("```")
        lines.append(d["d_2025"])
        lines.append("```")
        lines.append("")
        lines.append("### 2026 HWP body")
        lines.append("```")
        lines.append(d["d_2026"])
        lines.append("```")
        lines.append("")
        lines.append("### 변경 (unified diff)")
        lines.append("```diff")
        lines.append(render_unified_diff(d["d_2025"], d["d_2026"]))
        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")

    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"검토표 저장: {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
