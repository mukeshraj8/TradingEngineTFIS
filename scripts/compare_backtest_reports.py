from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tfis.backtest.report_comparison import (
    BacktestReportComparisonError,
    ComparisonLimits,
    comparison_to_dict,
    load_and_compare_backtest_reports,
    render_comparison_markdown,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare existing TFIS backtest JSON reports across modes."
    )
    parser.add_argument(
        "--report",
        action="append",
        required=True,
        help="Report input in LABEL=PATH form. May be repeated.",
    )
    parser.add_argument("--out", required=True, help="Path for JSON comparison output")
    parser.add_argument(
        "--markdown-out",
        help="Optional path for markdown comparison output",
    )
    parser.add_argument(
        "--max-trades",
        type=int,
        default=10000,
        help="Maximum evaluations to normalize per report before truncating comparison detail.",
    )
    parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=5_000_000,
        help="Maximum JSON file size accepted for comparison.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=10.0,
        help="Cooperative timeout for bounded comparison processing.",
    )
    return parser


def _parse_report_arg(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise ValueError(
            f"Invalid --report value '{value}'. Expected LABEL=PATH."
        )
    label, raw_path = value.split("=", 1)
    label = label.strip()
    if not label:
        raise ValueError("Report label must be non-empty.")
    path = Path(raw_path.strip())
    if not path:
        raise ValueError("Report path must be non-empty.")
    return label, path


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.max_trades <= 0:
        parser.error("--max-trades must be positive.")
    if args.max_file_bytes <= 0:
        parser.error("--max-file-bytes must be positive.")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive.")

    labeled_reports: list[tuple[str, Path]] = []
    for raw_report in args.report:
        try:
            label, path = _parse_report_arg(raw_report)
        except ValueError as exc:
            parser.error(str(exc))
        labeled_reports.append((label, path))

    limits = ComparisonLimits(
        max_file_bytes=args.max_file_bytes,
        max_trades=args.max_trades,
        timeout_seconds=args.timeout_seconds,
    )

    try:
        comparison = load_and_compare_backtest_reports(
            labeled_reports,
            limits=limits,
        )
    except BacktestReportComparisonError as exc:
        print(f"Comparison failed: {exc}", file=sys.stderr)
        return 1

    output = comparison_to_dict(comparison)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Comparison JSON written to {out_path}")

    if args.markdown_out:
        markdown_path = Path(args.markdown_out)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(
            render_comparison_markdown(comparison),
            encoding="utf-8",
        )
        print(f"Comparison markdown written to {markdown_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
