from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.paper import (
    PaperFyersSnapshotCollectorError,
    paper_morning_supervised_market_closed_no_action,
    paper_morning_supervised_process_lock_path,
    run_paper_morning_supervised_decision,
)
from tfis.runtime import ProcessLockError, ProcessLockHandle, acquire_process_lock


DEFAULT_CONFIG = REPO_ROOT / "config" / "paper.s21.fyers_connect_test.yaml"
DEFAULT_REFERENCE_PACKET = (
    REPO_ROOT / "config" / "reference_packets" / "s21_banknifty_monthly_live_decision_reference.json"
)
DEFAULT_STRATEGIES = (
    "S21_BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL",
    "S21_BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT",
    "S21_BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL",
    "S21_BANKNIFTY_OP_SELL_MONTHLY_BEAR_PUT",
)
DEFAULT_STRATEGY_ROOT = REPO_ROOT / "config" / "strategies" / "options_sell" / "banknifty"
DEFAULT_SUPERVISOR_LAUNCHER = REPO_ROOT / "scripts" / "start_tfis_paper_lifecycle_supervisor.ps1"
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Wait for the S21 morning checkpoints at 09:16, 09:25, and 09:30 local time, "
            "collect supervised TFIS live-paper inputs at each stage, and write a combined "
            "trade-decision explainer plus the final decision summary once RC is available."
        )
    )
    parser.add_argument("--tfis-root", default=str(REPO_ROOT))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument(
        "--strategy-path",
        action="append",
        default=None,
        help=(
            "S21 strategy folder to evaluate. Repeat for multiple branches. "
            "Defaults to all configured BANKNIFTY S21 CE/PE branches."
        ),
    )
    parser.add_argument("--reference-packet", default=str(DEFAULT_REFERENCE_PACKET))
    parser.add_argument("--artifact-root", default="data/strategies/S21/fyers_morning_supervised_decision")
    parser.add_argument("--dashboard-output-root", default="tmp/operator_dashboard")
    parser.add_argument("--session-id-prefix", default="s21-fyers-morning-supervised-decision")
    parser.add_argument("--process-lock-root", default="tmp/process_locks/s21_supervised_decision")
    parser.add_argument("--carry-forward-state-dir")
    parser.add_argument("--enable-smoke-override", action="store_true")
    parser.add_argument("--skip-refresh", action="store_true")
    parser.add_argument("--timezone", default="Asia/Kolkata")
    parser.add_argument("--if-past", choices=["run_now", "abort"], default="run_now")
    parser.add_argument("--disable-position-watch", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    strategy_paths = tuple(
        Path(item)
        for item in (
            args.strategy_path
            if args.strategy_path is not None
            else [str(DEFAULT_STRATEGY_ROOT / name) for name in DEFAULT_STRATEGIES]
        )
    )
    process_lock_handle: ProcessLockHandle | None = None
    try:
        process_lock_handle = acquire_process_lock(
            paper_morning_supervised_process_lock_path(
                artifact_root=Path(args.artifact_root),
                session_id_prefix=args.session_id_prefix,
                lock_root=Path(args.process_lock_root),
                strategy_code="S21",
            ),
            label=f"s21-supervised-decision:{args.session_id_prefix}",
            metadata={
                "artifact_root": str(Path(args.artifact_root).resolve()),
                "session_id_prefix": args.session_id_prefix,
                "strategy_paths": [str(item) for item in strategy_paths],
            },
            logger=lambda message: print(message, file=sys.stderr, flush=True),
        )
    except ProcessLockError as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        return 1
    try:
        result = run_paper_morning_supervised_decision(
            tfis_root=args.tfis_root,
            config_path=args.config,
            strategy_path=strategy_paths[0],
            strategy_paths=strategy_paths,
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
    except (PaperFyersSnapshotCollectorError, RuntimeError) as exc:
        code = getattr(exc, "code", "MORNING_SUPERVISED_DECISION_FAILED")
        if paper_morning_supervised_market_closed_no_action(code=code, message=str(exc)):
            print(
                "MARKET_CLOSED_NO_ACTION: No intraday market candles were available "
                "for the supervised S21 snapshot window. No trade decision or supervisor "
                "startup was triggered."
            )
            return 0
        print(f"ERROR [{code}]: {exc}", file=sys.stderr)
        return 1
    finally:
        if process_lock_handle is not None:
            process_lock_handle.release()
    print("Scheduled morning supervised S21 decision run succeeded.")
    print(f"Session directory: {result.session_directory}")
    print(f"Decision explainer: {result.timeline_markdown}")
    if result.branch_final_summary_markdown:
        for branch, path in sorted(result.branch_final_summary_markdown.items()):
            print(f"Final decision summary [{branch}]: {path}")
    if result.final_summary_markdown is not None:
        print(f"Final decision summary: {result.final_summary_markdown}")
    if (
        not args.disable_position_watch
        and (result.branch_order_state_json or result.branch_position_state_json)
    ):
        _start_s21_supervisor(
            tfis_root=Path(args.tfis_root),
            config_path=Path(args.config),
            artifact_root=Path(args.artifact_root),
            session_date=result.session_directory.parent.name,
        )
    return 0

def _start_s21_supervisor(
    *,
    tfis_root: Path,
    config_path: Path,
    artifact_root: Path,
    session_date: str,
) -> None:
    if not DEFAULT_SUPERVISOR_LAUNCHER.exists():
        print(
            f"WARNING: TFIS lifecycle supervisor launcher not found: {DEFAULT_SUPERVISOR_LAUNCHER}",
            file=sys.stderr,
        )
        return
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(DEFAULT_SUPERVISOR_LAUNCHER),
        "-TfisRoot",
        str(tfis_root),
        "-SessionDate",
        session_date,
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        print(f"WARNING: failed to launch TFIS lifecycle supervisor bootstrap: {exc}", file=sys.stderr)
        return
    if completed.stdout.strip():
        print(completed.stdout.strip())
    if completed.returncode != 0:
        stderr_text = completed.stderr.strip() or "unknown lifecycle supervisor bootstrap failure"
        print(
            f"WARNING: TFIS lifecycle supervisor bootstrap exited with code {completed.returncode}: {stderr_text}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    raise SystemExit(main())
