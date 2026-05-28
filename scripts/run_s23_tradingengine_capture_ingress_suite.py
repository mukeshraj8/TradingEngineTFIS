from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.paper.tradingengine_capture_ingress_suite import (
    S23TradingEngineCaptureIngressSuiteError,
    S23TradingEngineCaptureIngressSuiteRunner,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run S23 ingress-only dry runs using TradingEngine capture-derived "
            "market events paired with TFIS validation preludes."
        )
    )
    parser.add_argument(
        "--data-root",
        required=True,
        help="TradingData root, for example D:\\TradingData.",
    )
    parser.add_argument(
        "--dates",
        nargs="+",
        help="One or more session dates in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--prelude-template",
        help="Optional JSON file with default or per-date synthetic prelude overrides.",
    )
    parser.add_argument(
        "--out-root",
        default="tmp/s23_tradingengine_capture_dry_runs",
        help="Output root for converted files, dry-run artifacts, and aggregate summaries.",
    )
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Audit sessions only without running ingress dry runs.",
    )
    parser.add_argument(
        "--out-json",
        help="Optional explicit path for the aggregate JSON summary.",
    )
    parser.add_argument(
        "--out-md",
        help="Optional explicit path for the aggregate Markdown summary.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    runner = S23TradingEngineCaptureIngressSuiteRunner(out_root=args.out_root)
    try:
        summary = runner.run(
            data_root=args.data_root,
            dates=args.dates,
            prelude_template_path=args.prelude_template,
            audit_only=args.audit_only,
        )
    except S23TradingEngineCaptureIngressSuiteError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.out_json:
        target = Path(args.out_json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(runner.render_json(summary), encoding="utf-8")
    if args.out_md:
        target = Path(args.out_md)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(runner.render_markdown(summary), encoding="utf-8")

    print(f"Suite output root: {args.out_root}")
    print(f"Sessions processed: {summary.total_sessions}")
    print(f"Rollout recommendation: {summary.rollout_recommendation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
