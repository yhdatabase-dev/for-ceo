"""취업규칙 검토 CLI (구 `python -m cgr`).

사용법 (backend/ 에서):
  python scripts/review_cli.py review <input_file> [--catalog data/slots/atomic_slots_v0.yaml]
                                                   [--output output/]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import assert_ready  # noqa: E402
from app.services.wr.reporter import save_report  # noqa: E402
from app.services.wr.review import review_file  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="review_cli", description="취업규칙 검토 MVP")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_review = sub.add_parser("review", help="사업장 취업규칙 1건 검토")
    p_review.add_argument("input", type=Path, help="docx/hwp/hwpx/pdf/txt")
    p_review.add_argument(
        "--catalog",
        type=Path,
        default=Path("data/slots/atomic_slots_v0.yaml"),
        help="원자 슬롯 카탈로그 yaml",
    )
    p_review.add_argument(
        "--output",
        type=Path,
        default=Path("output"),
        help="리포트 출력 디렉토리",
    )

    args = parser.parse_args(argv)

    if args.cmd == "review":
        assert_ready()
        if not args.input.exists():
            print(f"[오류] 입력 파일 없음: {args.input}", file=sys.stderr)
            return 2
        if not args.catalog.exists():
            print(f"[오류] 카탈로그 없음: {args.catalog}", file=sys.stderr)
            return 2
        print(f"[검토 시작] {args.input}", file=sys.stderr)
        report = review_file(args.input, args.catalog, output_dir=args.output)
        md_path, json_path = save_report(report, args.output)
        print(f"[완료] 종합: {report.overall_label}", file=sys.stderr)
        print(f"  - 리포트: {md_path}", file=sys.stderr)
        print(f"  - JSON  : {json_path}", file=sys.stderr)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
