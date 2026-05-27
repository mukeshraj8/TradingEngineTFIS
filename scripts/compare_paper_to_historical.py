from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.paper import (
    S23PaperHistoricalComparisonError,
    compare_paper_bundle_to_historical,
    compare_paper_session_to_historical,
    render_paper_historical_comparison_json,
    render_paper_historical_comparison_markdown,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare an S23 paper intent shell against a historical/backtest "
            "report for replay parity verification."
        )
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--session-dir", help="Paper-session artifact directory to compare.")
    group.add_argument("--bundle-dir", help="Replay-bundle directory to compare.")
    parser.add_argument(
        "--historical-report",
        required=True,
        help="Historical/backtest report JSON to compare against.",
    )
    parser.add_argument(
        "--historical-trade-key",
        help="Optional explicit historical trade key.",
    )
    parser.add_argument(
        "--session-date",
        help="Optional YYYY-MM-DD session-date filter when no trade key is supplied.",
    )
    parser.add_argument(
        "--numeric-tolerance",
        type=float,
        default=0.01,
        help="Numeric tolerance used for float field comparisons.",
    )
    parser.add_argument("--out-json", help="Optional output path for JSON comparison.")
    parser.add_argument("--out-md", help="Optional output path for Markdown comparison.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.bundle_dir:
            summary = compare_paper_bundle_to_historical(
                args.bundle_dir,
                args.historical_report,
                historical_trade_key=args.historical_trade_key,
                session_date=args.session_date,
                numeric_tolerance=args.numeric_tolerance,
            )
        else:
            summary = compare_paper_session_to_historical(
                args.session_dir,
                args.historical_report,
                historical_trade_key=args.historical_trade_key,
                session_date=args.session_date,
                numeric_tolerance=args.numeric_tolerance,
            )
    except S23PaperHistoricalComparisonError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    json_text = render_paper_historical_comparison_json(summary)
    markdown_text = render_paper_historical_comparison_markdown(summary)

    if args.out_json:
        Path(args.out_json).write_text(json_text, encoding="utf-8", newline="\n")
    if args.out_md:
        Path(args.out_md).write_text(markdown_text, encoding="utf-8", newline="\n")

    if not args.out_json and not args.out_md:
        print(markdown_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
