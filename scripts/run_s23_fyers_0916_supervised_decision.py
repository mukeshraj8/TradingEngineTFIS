from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.paper import (
    S23FyersSnapshotCollectorError,
    run_s23_morning_supervised_decision,
)


DEFAULT_CONFIG = REPO_ROOT / "config" / "paper.s23.fyers_connect_test.yaml"
DEFAULT_REFERENCE_PACKET = (
    REPO_ROOT / "config" / "reference_packets" / "s23_bear_put_live_decision_reference.json"
)
DEFAULT_STRATEGY = (
    REPO_ROOT
    / "config"
    / "strategies"
    / "options_sell"
    / "nifty"
    / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Wait for the S23 morning checkpoints at 09:16, 09:25, and 09:30 local time, "
            "collect supervised TFIS live-paper inputs at each stage, and write a combined "
            "trade-decision explainer plus the final decision summary once RC is available."
        )
    )
    parser.add_argument("--tfis-root", default=str(REPO_ROOT))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--strategy-path", default=str(DEFAULT_STRATEGY))
    parser.add_argument("--reference-packet", default=str(DEFAULT_REFERENCE_PACKET))
    parser.add_argument("--artifact-root", default="tmp/s23_fyers_morning_supervised_decision")
    parser.add_argument("--dashboard-output-root", default="tmp/operator_dashboard")
    parser.add_argument("--session-id-prefix", default="s23-fyers-morning-supervised-decision")
    parser.add_argument("--carry-forward-state-dir")
    parser.add_argument("--enable-smoke-override", action="store_true")
    parser.add_argument("--skip-refresh", action="store_true")
    parser.add_argument("--timezone", default="Asia/Kolkata")
    parser.add_argument("--if-past", choices=["run_now", "abort"], default="run_now")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_s23_morning_supervised_decision(
            tfis_root=args.tfis_root,
            config_path=args.config,
            strategy_path=args.strategy_path,
            reference_packet_path=args.reference_packet,
            artifact_root=args.artifact_root,
            dashboard_output_root=args.dashboard_output_root,
            session_id_prefix=args.session_id_prefix,
            carry_forward_state_dir=args.carry_forward_state_dir,
            enable_smoke_override=args.enable_smoke_override,
            skip_refresh=args.skip_refresh,
            timezone_name=args.timezone,
            if_past=args.if_past,
        )
    except (S23FyersSnapshotCollectorError, RuntimeError) as exc:
        code = getattr(exc, "code", "MORNING_SUPERVISED_DECISION_FAILED")
        print(f"ERROR [{code}]: {exc}", file=sys.stderr)
        return 1
    print("Scheduled morning supervised S23 decision run succeeded.")
    print(f"Session directory: {result.session_directory}")
    print(f"Decision explainer: {result.timeline_markdown}")
    if result.final_summary_markdown is not None:
        print(f"Final decision summary: {result.final_summary_markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
