from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.dashboard import StrategyDashboardConfig, TfisOperatorDashboardBuilder


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a read-only TFIS operator dashboard from artifact directories. "
            "The first version renders a strategy index plus an S23 strategy page."
        )
    )
    parser.add_argument(
        "--output-root",
        default="tmp/operator_dashboard",
        help="Directory where the generated dashboard HTML and manifest should be written.",
    )
    parser.add_argument(
        "--s23-artifact-root",
        default="data/strategies/S23/fyers_morning_supervised_decision",
        help="Artifact root for the S23 morning supervised decision workflow.",
    )
    parser.add_argument(
        "--s23-strategy-path",
        default="config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
    )
    parser.add_argument(
        "--s23-reference-packet",
        default="config/reference_packets/s23_bear_put_live_decision_reference.json",
    )
    parser.add_argument(
        "--session-id-prefix",
        default="s23-fyers-morning-supervised-decision",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    builder = TfisOperatorDashboardBuilder(
        strategy_configs=(
            StrategyDashboardConfig(
                strategy_code="S23",
                display_name="S23 Operator Dashboard",
                artifact_root=REPO_ROOT / args.s23_artifact_root,
                strategy_path=REPO_ROOT / args.s23_strategy_path,
                reference_packet_path=REPO_ROOT / args.s23_reference_packet,
                session_id_prefix=args.session_id_prefix,
            ),
        )
    )
    result = builder.build(output_root=REPO_ROOT / args.output_root)
    print("TFIS operator dashboard build succeeded.")
    print(f"Index page: {result.index_html}")
    for strategy_code, page in sorted(result.strategy_pages.items()):
        print(f"{strategy_code} page: {page}")
    print(f"Manifest: {result.manifest_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
