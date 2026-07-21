from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.paper import (
    PaperFyersSnapshotCollectorError,
    S23PaperLiveDecisionError,
    run_paper_live_decision_check,
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
            "Refresh TFIS-owned FYERS auth, collect normalized TFIS "
            "market inputs, and build a paper-only S23 decision summary."
        )
    )
    parser.add_argument("--tfis-root", default=str(REPO_ROOT))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--strategy-path", default=str(DEFAULT_STRATEGY))
    parser.add_argument("--reference-packet", default=str(DEFAULT_REFERENCE_PACKET))
    parser.add_argument("--artifact-root", default="tmp/s23_fyers_live_decision")
    parser.add_argument("--session-id", default="s23-fyers-live-decision")
    parser.add_argument("--carry-forward-state-dir")
    parser.add_argument("--enable-smoke-override", action="store_true")
    parser.add_argument("--skip-refresh", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_paper_live_decision_check(
            tfis_root=args.tfis_root,
            config_path=args.config,
            strategy_path=args.strategy_path,
            reference_packet_path=args.reference_packet,
            artifact_root=args.artifact_root,
            session_id=args.session_id,
            carry_forward_state_dir=args.carry_forward_state_dir,
            enable_smoke_override=args.enable_smoke_override,
            skip_refresh=args.skip_refresh,
        )
    except (PaperFyersSnapshotCollectorError, S23PaperLiveDecisionError, RuntimeError) as exc:
        code = getattr(exc, "code", "LIVE_DECISION_FAILED")
        print(f"ERROR [{code}]: {exc}", file=sys.stderr)
        return 1
    print("S23 live decision check succeeded.")
    print(f"Snapshot session directory: {result.snapshot_artifacts.session_directory}")
    print(f"Underlying snapshot: {result.snapshot_artifacts.normalized_underlying_snapshot_path}")
    print(f"Underlying bars: {result.snapshot_artifacts.normalized_underlying_bars_path}")
    print(f"Option-chain snapshot: {result.snapshot_artifacts.normalized_option_chain_snapshot_path}")
    print(f"Decision summary (JSON): {result.decision_summary_json}")
    print(f"Decision summary (Markdown): {result.decision_summary_markdown}")
    print(f"Decision explainer (JSON): {result.decision_explainer_json}")
    print(f"Decision explainer (Markdown): {result.decision_explainer_markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
