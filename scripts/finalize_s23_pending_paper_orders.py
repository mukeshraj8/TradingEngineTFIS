from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.dashboard import StrategyDashboardConfig, TfisOperatorDashboardBuilder
from tfis.dashboard.config_loader import load_dashboard_strategy_configs
from tfis.paper import S23PaperOrderFinalizer, S23PaperOrderFinalizerSummary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Finalize stale S23 waiting paper orders after the entry-session "
            "cutoff. This is a safety net for watcher crashes; it never fills "
            "orders and never calls a broker."
        )
    )
    parser.add_argument("--artifact-root", default="data/strategies/S23/fyers_morning_supervised_decision")
    parser.add_argument("--session-date", help="YYYY-MM-DD. Defaults to current date in --timezone.")
    parser.add_argument("--timezone", default="Asia/Kolkata")
    parser.add_argument("--cutoff", default="15:30", help="HH:MM local cutoff.")
    parser.add_argument("--include-prior-sessions", action="store_true")
    parser.add_argument("--allow-before-cutoff", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary JSON.")
    parser.add_argument("--rebuild-dashboard", action="store_true")
    parser.add_argument("--dashboard-output-root", default="tmp/operator_dashboard")
    parser.add_argument(
        "--s23-strategy-path",
        default="config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
    )
    parser.add_argument(
        "--s23-reference-packet",
        default="config/reference_packets/s23_bear_put_live_decision_reference.json",
    )
    parser.add_argument("--session-id-prefix", default="s23-fyers-morning-supervised-decision")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    timezone = ZoneInfo(args.timezone)
    session_date = date.fromisoformat(args.session_date) if args.session_date else datetime.now(timezone).date()
    marked_at = datetime.now(timezone)
    summary = S23PaperOrderFinalizer().finalize(
        REPO_ROOT / args.artifact_root,
        session_date=session_date,
        marked_at=marked_at,
        cutoff_time=_parse_hhmm(args.cutoff),
        include_prior_sessions=args.include_prior_sessions,
        allow_before_cutoff=args.allow_before_cutoff,
        dry_run=args.dry_run,
    )
    if args.json:
        print(_summary_json(summary))
    else:
        _print_summary(summary)
    if args.rebuild_dashboard and not args.dry_run:
        dashboard_config_path = REPO_ROOT / "config" / "operator_dashboard_strategies.yaml"
        if dashboard_config_path.exists():
            strategy_configs = load_dashboard_strategy_configs(
                dashboard_config_path,
                repo_root=REPO_ROOT,
            )
        else:
            strategy_configs = (
                StrategyDashboardConfig(
                    strategy_code="S23",
                    display_name="S23 Operator Dashboard",
                    artifact_root=REPO_ROOT / args.artifact_root,
                    strategy_path=REPO_ROOT / args.s23_strategy_path,
                    reference_packet_path=REPO_ROOT / args.s23_reference_packet,
                    session_id_prefix=args.session_id_prefix,
                ),
            )
        result = TfisOperatorDashboardBuilder(
            strategy_configs=strategy_configs,
        ).build(output_root=REPO_ROOT / args.dashboard_output_root)
        print(f"Dashboard rebuilt: {result.strategy_pages['S23']}")
    return 0


def _parse_hhmm(value: str) -> time:
    try:
        hour_text, minute_text = value.split(":", 1)
        return time(int(hour_text), int(minute_text))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--cutoff must be HH:MM") from exc


def _summary_json(summary: S23PaperOrderFinalizerSummary) -> str:
    payload = asdict(summary)
    return json.dumps(_normalize(payload), indent=2, sort_keys=True)


def _normalize(value):
    if isinstance(value, dict):
        return {str(key): _normalize(val) for key, val in value.items()}
    if isinstance(value, list | tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    return value


def _print_summary(summary: S23PaperOrderFinalizerSummary) -> None:
    mode = "DRY RUN" if summary.dry_run else "APPLIED"
    print("TFIS S23 paper order finalizer")
    print(f"Mode       : {mode}")
    print(f"Root       : {summary.artifact_root}")
    print(f"Session    : {summary.session_date.isoformat()}")
    print(f"Marked at  : {summary.marked_at.isoformat()}")
    print(f"Cutoff     : {summary.cutoff_time.isoformat(timespec='minutes')}")
    print(f"Scanned    : {summary.scanned_count}")
    print(f"Finalized  : {summary.finalized_count}")
    print(f"Skipped    : {summary.skipped_count}")
    for decision in summary.decisions:
        print(
            f"- {decision.action}: {decision.selected_contract_symbol} "
            f"[{decision.reason_code}] {decision.order_directory}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
