from __future__ import annotations

import argparse
import json
import sys
import time as time_module
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.paper import (
    S23LiveDecisionScheduleError,
    build_schedule_note,
    compute_schedule_delay_seconds,
    run_s23_live_decision_check,
)


DEFAULT_TRADINGENGINE_ROOT = Path(r"D:\TradingEngineProd")
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
            "Wait until 09:16 local time, collect the supervised TFIS live-paper "
            "decision inputs, and write both the decision summary and the detailed explainer."
        )
    )
    parser.add_argument("--tradingengine-root", default=str(DEFAULT_TRADINGENGINE_ROOT))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--strategy-path", default=str(DEFAULT_STRATEGY))
    parser.add_argument("--reference-packet", default=str(DEFAULT_REFERENCE_PACKET))
    parser.add_argument("--artifact-root", default="tmp/s23_fyers_0916_supervised_decision")
    parser.add_argument("--session-id-prefix", default="s23-fyers-0916-supervised-decision")
    parser.add_argument("--carry-forward-state-dir")
    parser.add_argument("--enable-smoke-override", action="store_true")
    parser.add_argument("--skip-refresh", action="store_true")
    parser.add_argument("--run-hour", type=int, default=9)
    parser.add_argument("--run-minute", type=int, default=16)
    parser.add_argument("--timezone", default="Asia/Kolkata")
    parser.add_argument("--if-past", choices=["run_now", "abort"], default="run_now")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    timezone = ZoneInfo(args.timezone)
    now = datetime.now(timezone)
    try:
        delay_seconds = compute_schedule_delay_seconds(
            now=now,
            target_hour=args.run_hour,
            target_minute=args.run_minute,
            if_past=args.if_past,
        )
    except S23LiveDecisionScheduleError as exc:
        print(f"ERROR [SCHEDULE_ABORTED]: {exc}", file=sys.stderr)
        return 1

    note = build_schedule_note(
        now=now,
        target_hour=args.run_hour,
        target_minute=args.run_minute,
        delay_seconds=delay_seconds,
    )
    print(note)
    if delay_seconds > 0:
        time_module.sleep(delay_seconds)

    trigger_time = datetime.now(timezone)
    session_id = f"{args.session_id_prefix}-{trigger_time.strftime('%Y-%m-%d')}"
    result = run_s23_live_decision_check(
        tradingengine_root=args.tradingengine_root,
        config_path=args.config,
        strategy_path=args.strategy_path,
        reference_packet_path=args.reference_packet,
        artifact_root=args.artifact_root,
        session_id=session_id,
        carry_forward_state_dir=args.carry_forward_state_dir,
        enable_smoke_override=args.enable_smoke_override,
        skip_refresh=args.skip_refresh,
    )
    metadata_path = result.snapshot_artifacts.session_directory / "scheduled_run_metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "requested_run_hour": args.run_hour,
                "requested_run_minute": args.run_minute,
                "timezone": args.timezone,
                "if_past": args.if_past,
                "initial_check_time": now.isoformat(),
                "trigger_time": trigger_time.isoformat(),
                "delay_seconds": delay_seconds,
                "note": note,
                "decision_summary_json": str(result.decision_summary_json),
                "decision_summary_markdown": str(result.decision_summary_markdown),
                "decision_explainer_json": str(result.decision_explainer_json),
                "decision_explainer_markdown": str(result.decision_explainer_markdown),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print("Scheduled supervised S23 decision run succeeded.")
    print(f"Session directory: {result.snapshot_artifacts.session_directory}")
    print(f"Decision summary: {result.decision_summary_markdown}")
    print(f"Decision explainer: {result.decision_explainer_markdown}")
    print(f"Schedule metadata: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
