"""마크다운 리포트 생성."""
from __future__ import annotations

import json
from pathlib import Path

from app.schemas.wr.values import Finding, Report
from app.services.ai.wr.verdict import classify, detail_label

# 5-Bucket 이모지 — 구 cgr.ui.constants.BUCKET_EMOJI (Streamlit 관리자 제거로 이관)
_BUCKET_EMOJI: dict[str, str] = {
    "누락": "🔴",
    "위반": "🟠",
    "주의": "🟡",
    "검토필요": "🟣",
    "적정": "✅",
}

_STATUS_EMOJI = {"OK": "✅", "VIOLATION": "❌", "MISSING": "🟥", "ERROR": "⚠️", "AMBIGUOUS": "🟣"}


def _format_value(v) -> str:
    if v is None:
        return "_(null)_"
    if isinstance(v, (dict, list)):
        return f"`{json.dumps(v, ensure_ascii=False)}`"
    return f"`{v}`"


def _format_expected(expected) -> str:
    """MasterValue 객체 → 사용자에게 표시할 기준값.

    object_match 슬롯은 value 가 None 이고 추가 키들 (default_months 등) 이 있음.
    이 경우 모든 키를 dict 형태로 표시.
    """
    if expected is None:
        return "_(null)_"
    d = expected.model_dump(exclude_none=True) if hasattr(expected, "model_dump") else dict(expected)
    note = d.pop("note", None)
    unit = d.pop("unit", None)
    if "value" in d:
        v = d["value"]
        result = _format_value(v)
        if unit:
            result = result.rstrip("`") + f" {unit}`"
        return result
    if d:
        return f"`{json.dumps(d, ensure_ascii=False)}`"
    return "_(null)_"


def _format_finding(f: Finding) -> str:
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
    if f.extracted.quote:
        q = f.extracted.quote.replace("\n", " ⏎ ")
        lines.append(f"> {q[:400]}")
    else:
        lines.append("> **🟥 누락 — 사업장 본문에서 관련 규정을 찾지 못함**")
    lines.append("")
    if f.penalty:
        from app.services.ai.wr.penalty_parser import format_for_user
        parts = format_for_user(f.penalty)
        if parts["omission"] or parts["violation"]:
            lines.append("**⚖️ 근거 법령 및 벌칙**")
            lines.append("")
        if parts["omission"]:
            lines.append("📋 *취업규칙에 미기재 시*")
            for p in parts["omission"]:
                lines.append(f"- {p}")
            lines.append("")
        if parts["violation"]:
            lines.append("⚖️ *법령 내용 위반 시*")
            for p in parts["violation"]:
                lines.append(f"- {p}")
            lines.append("")
        if not parts["omission"] and not parts["violation"]:
            # 권고 사항 — 분류 없이 원본 그대로
            lines.append("**📌 적용 벌칙**")
            lines.append("")
            for p in f.penalty:
                lines.append(f"- {p}")
            lines.append("")
    if f.fix_example:
        lines.append("**✏️ 시정 예시**")
        lines.append("")
        lines.append(f"> {f.fix_example}")
        lines.append("")
    # 디버그 정보 — 작게
    debug_bits: list[str] = []
    debug_bits.append(f"추출값 {_format_value(f.extracted.extracted_value)} · 기준값 {_format_expected(f.expected)}")
    if f.user_reason and f.reason and f.user_reason != f.reason:
        debug_bits.append(f"기술적 사유: `{f.reason}`")
    lines.append(f"<sub>🔧 {' · '.join(debug_bits)}</sub>")
    lines.append("")
    return "\n".join(lines)


def render_markdown(report: Report) -> str:
    lines: list[str] = []
    lines.append(f"# 취업규칙 검토 리포트")
    lines.append("")
    lines.append(f"- **사건 ID**: `{report.case_id}`")
    lines.append(f"- **원본 파일**: `{report.source_file}`")
    lines.append(f"- **생성 시각**: `{report.generated_at}`")
    lines.append("")

    # 사업장 종합 판정
    all_findings: list[Finding] = []
    for ar in report.article_results:
        all_findings.extend(ar.findings)
    label = detail_label(all_findings)
    lines.append(f"## 종합 판정")
    lines.append("")
    lines.append(f"**🏛 {label}**")
    lines.append("")

    # 5-bucket 요약
    if report.summary:
        order = ["누락", "위반", "주의", "검토필요", "적정"]
        parts = []
        for k in order:
            v = report.summary.get(k, 0)
            parts.append(f"{_BUCKET_EMOJI.get(k,'')} {k}: {v}")
        lines.append("**분포**: " + ", ".join(parts))
        lines.append("")

    # 조별 상세 (필수)
    for ar in report.article_results:
        miss = [f for f in ar.findings if classify(f) == "누락"]
        viol = [f for f in ar.findings if classify(f) == "위반"]
        warn = [f for f in ar.findings if classify(f) == "주의"]
        amb = [f for f in ar.findings if classify(f) == "검토필요"]
        ok = [f for f in ar.findings if classify(f) == "적정"]
        err = [f for f in ar.findings if f.status == "ERROR"]
        art_label = detail_label(ar.findings)
        lines.append(f"## 제{ar.article}조 — {ar.title}  · {art_label}")
        lines.append("")
        lines.append(
            f"슬롯 {len(ar.findings)}개 · "
            f"🔴 {len(miss)} · 🟠 {len(viol)} · 🟡 {len(warn)} · 🟣 {len(amb)} · ✅ {len(ok)} · ⚠️ {len(err)}"
        )
        lines.append("")
        if miss:
            lines.append("### 🔴 누락")
            for f in miss:
                lines.append(_format_finding(f))
                lines.append("")
        if viol:
            lines.append("### 🟠 위반")
            for f in viol:
                lines.append(_format_finding(f))
                lines.append("")
        if warn:
            lines.append("### 🟡 주의")
            for f in warn:
                lines.append(_format_finding(f))
                lines.append("")
        if amb:
            lines.append("### 🟣 검토필요")
            for f in amb:
                lines.append(_format_finding(f))
                lines.append("")
        if err:
            lines.append("### ⚠️ 오류")
            for f in err:
                lines.append(_format_finding(f))
                lines.append("")
        if ok:
            lines.append("### ✅ 적정")
            for f in ok:
                lines.append(_format_finding(f))
                lines.append("")
        lines.append("")

    # 선택 조 디스플레이 — 검사 안 함, 참고용 표시
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
            present = "📄 사업장 본문에 관련 규정 **있음**" if od.user_present else "🔍 사업장 본문에 관련 규정 **없음**(미검출)"
            lines.append(present)
            lines.append("")
            if od.user_quote:
                q = od.user_quote.replace("\n", " ⏎ ")
                lines.append(f"**사업장 인용**: `{q[:400]}`")
                lines.append("")
            if od.master_guide:
                lines.append(f"**📋 작성시 착안사항**:")
                lines.append("")
                lines.append("> " + od.master_guide.replace("\n", "\n> "))
                lines.append("")
            if od.master_note:
                lines.append(f"**📌 참고**:")
                lines.append("")
                lines.append("> " + od.master_note.replace("\n", "\n> "))
                lines.append("")
            lines.append("")

    return "\n".join(lines)


def save_report(report: Report, out_dir: str | Path) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"report_{report.case_id}.md"
    json_path = out_dir / f"report_{report.case_id}.json"
    md_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    # 관리자 대시보드 이력 누적 (실패해도 검토 통과)
    try:
        from app.repositories.shared.review_history import append_history, build_entry_from_report
        entry = build_entry_from_report(report)
        entry["report_path"] = str(json_path)
        append_history(entry)
    except Exception:
        pass

    return md_path, json_path
