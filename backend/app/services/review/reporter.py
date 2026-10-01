"""마크다운 리포트 렌더링 + 저장.

===============================================================================
원본 이관
===============================================================================
원본: `cgr/reporter.py` (235줄) → v2 로 이관.

변경점
- `cgr.models.Finding / Report` → `FindingVO / ReportVO`
- FindingVO 는 평면 구조라 `f.extracted.quote/extracted_value` 접근 불가:
  · `f.quote` / `f.extracted_value` 직접 사용
- `Finding.expected` → v2 는 없음. 대신 slots_by_id 를 render 시 주입해서 master_value 조회.
- `Finding.penalty` → v2 는 이미 `penalty_omission / penalty_violation` 로 분리됨
  (rules.evaluate 에서 처리) → **penalty_parser 불필요, 직접 사용**
- `Report.article_results[]` (조별 그룹핑 객체) → v2 는 flat `findings` +
  `article_titles` dict → 이 파일 안에서 즉석 그룹핑
- `cgr.store.history.append_history` — v2 는 별도 이력 리포지토리로 이관 예정 (TODO)
- `BUCKET_EMOJI` 는 원본 `cgr/ui.py` 에서 내려온 상수 → 여기 상수로 인라인

원본 대비 렌더 결과는 동일 (동일 5-bucket 이모지·순서, 조별 상세, 선택조 참고).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.schemas.review.values import FindingVO, ReportVO, SlotDefVO
from app.services.review.verdict import classify, detail_label

log = get_logger(__name__)


# 원본 cgr/ui.py:BUCKET_EMOJI 그대로
_BUCKET_EMOJI = {
    "누락": "🔴",
    "위반": "🟠",
    "주의": "🟡",
    "검토필요": "🟣",
    "적정": "✅",
}


def _format_value(v: Any) -> str:
    if v is None:
        return "_(null)_"
    if isinstance(v, (dict, list)):
        return f"`{json.dumps(v, ensure_ascii=False)}`"
    return f"`{v}`"


def _format_expected(slot: SlotDefVO | None) -> str:
    """SlotDefVO.master_value → 사용자에게 표시할 기준값 문자열."""
    if slot is None or slot.master_value is None:
        return "_(null)_"
    mv = slot.master_value
    if mv.value is not None:
        return _format_value(mv.value)
    if mv.keys:
        return f"`{json.dumps(mv.keys, ensure_ascii=False)}`"
    return "_(null)_"


def _format_finding(f: FindingVO, slot: SlotDefVO | None) -> str:
    """감독관 가독성 우선 — 사유 → 인용 → 근거 법령·벌칙 → (디버그)."""
    main_reason = f.user_reason or f.reason
    bucket = classify(f)
    bucket_emoji = _BUCKET_EMOJI.get(bucket, "")
    lines = [
        f"### {bucket_emoji} {bucket} · `{f.slot_id}`",
        f"**상태**: {f.status} · severity={f.severity}",
        "",
    ]
    if main_reason:
        lines.append("**📝 사유**")
        lines.append("")
        lines.append(main_reason)
        lines.append("")
    lines.append("**📌 인용 (사업장 본문)**")
    lines.append("")
    if f.quote:
        q = f.quote.replace("\n", " ⏎ ")
        lines.append(f"> {q[:400]}")
    else:
        lines.append("> **🟥 누락 — 사업장 본문에서 관련 규정을 찾지 못함**")
    lines.append("")

    # rules.evaluate 가 이미 omission / violation 로 분리해줌 (penalty_parser 불필요)
    if f.penalty_omission or f.penalty_violation:
        lines.append("**⚖️ 근거 법령 및 벌칙**")
        lines.append("")
    if f.penalty_omission:
        lines.append("📋 *취업규칙에 미기재 시*")
        for p in f.penalty_omission:
            lines.append(f"- {p}")
        lines.append("")
    if f.penalty_violation:
        lines.append("⚖️ *법령 내용 위반 시*")
        for p in f.penalty_violation:
            lines.append(f"- {p}")
        lines.append("")

    if f.fix_example:
        lines.append("**✏️ 시정 예시**")
        lines.append("")
        lines.append(f"> {f.fix_example}")
        lines.append("")

    # 디버그 정보
    debug_bits: list[str] = [
        f"추출값 {_format_value(f.extracted_value)} · 기준값 {_format_expected(slot)}",
    ]
    if f.user_reason and f.reason and f.user_reason != f.reason:
        debug_bits.append(f"기술적 사유: `{f.reason}`")
    lines.append(f"<sub>🔧 {' · '.join(debug_bits)}</sub>")
    lines.append("")
    return "\n".join(lines)


def render_markdown(
    report: ReportVO,
    slots_by_id: dict[str, SlotDefVO] | None = None,
) -> str:
    """리포트 → 마크다운.

    Args:
        report:      완성된 ReportVO (verdict.finalize_report 완료 상태)
        slots_by_id: 슬롯 사전 (master_value 참고용 · 없어도 렌더는 됨)
    """
    slots_by_id = slots_by_id or {}
    lines: list[str] = []
    lines.append("# 취업규칙 검토 리포트")
    lines.append("")
    lines.append(f"- **사건 ID**: `{report.case_id}`")
    if report.source_file:
        lines.append(f"- **원본 파일**: `{report.source_file}`")
    if report.generated_at:
        lines.append(f"- **생성 시각**: `{report.generated_at}`")
    lines.append("")

    # 종합 판정
    label = detail_label(report.findings)
    lines.append("## 종합 판정")
    lines.append("")
    lines.append(f"**🏛 {label}**")
    lines.append("")

    # 5-bucket 요약
    if report.summary:
        order = ["누락", "위반", "주의", "검토필요", "적정"]
        parts = [
            f"{_BUCKET_EMOJI.get(k, '')} {k}: {report.summary.get(k, 0)}"
            for k in order
        ]
        lines.append("**분포**: " + ", ".join(parts))
        lines.append("")

    # 조별 상세 — v2 는 findings 가 flat 이라 즉석 그룹핑
    by_article: dict[int, list[FindingVO]] = {}
    for f in report.findings:
        by_article.setdefault(f.article, []).append(f)

    for art in sorted(by_article.keys()):
        art_findings = by_article[art]
        miss = [f for f in art_findings if classify(f) == "누락"]
        viol = [f for f in art_findings if classify(f) == "위반"]
        warn = [f for f in art_findings if classify(f) == "주의"]
        amb = [f for f in art_findings if classify(f) == "검토필요"]
        ok = [f for f in art_findings if classify(f) == "적정"]
        err = [f for f in art_findings if f.status == "ERROR"]
        art_label = detail_label(art_findings)
        title = report.article_titles.get(art, "")
        lines.append(f"## 제{art}조 — {title}  · {art_label}")
        lines.append("")
        lines.append(
            f"슬롯 {len(art_findings)}개 · "
            f"🔴 {len(miss)} · 🟠 {len(viol)} · 🟡 {len(warn)} · "
            f"🟣 {len(amb)} · ✅ {len(ok)} · ⚠️ {len(err)}"
        )
        lines.append("")
        for header, items in (
            ("### 🔴 누락", miss),
            ("### 🟠 위반", viol),
            ("### 🟡 주의", warn),
            ("### 🟣 검토필요", amb),
            ("### ⚠️ 오류", err),
            ("### ✅ 적정", ok),
        ):
            if not items:
                continue
            lines.append(header)
            for f in items:
                lines.append(_format_finding(f, slots_by_id.get(f.slot_id)))
                lines.append("")
        lines.append("")

    # 선택 조 디스플레이
    if report.optional_displays:
        lines.append("---")
        lines.append("")
        lines.append("# 선택 조항 참고 (검사 안 함)")
        lines.append("")
        lines.append(
            "아래는 표준취업규칙의 **선택 사항**입니다. 검토 AI 가 적정/부적정 판정을 내리지 않으며, "
            "감독관 판단의 참고 자료로 마스터 DB 의 작성시 착안사항·참고와 사업장 본문 인용을 함께 표시합니다."
        )
        lines.append("")
        for od in report.optional_displays:
            lines.append(f"## 제{od.article}조 — {od.title}  (선택)")
            lines.append("")
            present = (
                "📄 사업장 본문에 관련 규정 **있음**"
                if od.user_present
                else "🔍 사업장 본문에 관련 규정 **없음**(미검출)"
            )
            lines.append(present)
            lines.append("")
            if od.user_quote:
                q = od.user_quote.replace("\n", " ⏎ ")
                lines.append(f"**사업장 인용**: `{q[:400]}`")
                lines.append("")
            if od.master_guide:
                lines.append("**📋 작성시 착안사항**:")
                lines.append("")
                lines.append("> " + od.master_guide.replace("\n", "\n> "))
                lines.append("")
            if od.master_note:
                lines.append("**📌 참고**:")
                lines.append("")
                lines.append("> " + od.master_note.replace("\n", "\n> "))
                lines.append("")
            lines.append("")

    return "\n".join(lines)


def save_report(
    report: ReportVO,
    out_dir: str | Path,
    slots_by_id: dict[str, SlotDefVO] | None = None,
) -> tuple[Path, Path]:
    """리포트를 md + json 파일 쌍으로 저장.

    반환: (md_path, json_path)

    TODO: 원본은 여기서 `store.history.append_history` 로 관리자 이력 누적 —
          v2 는 별도 history repository 로 이관 예정 (오케스트레이터에서 처리).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"report_{report.case_id}.md"
    json_path = out_dir / f"report_{report.case_id}.json"
    md_path.write_text(render_markdown(report, slots_by_id), encoding="utf-8")
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return md_path, json_path
