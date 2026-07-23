from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.paper import load_paper_runtime_waiting_order_statuses


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show stale/current TFIS paper waiting-order status by strategy."
    )
    parser.add_argument("--targets-config", default="config/paper_lifecycle_supervisor_targets.yaml")
    parser.add_argument("--session-date", help="YYYY-MM-DD. Defaults to each target config timezone's current date.")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    session_date = date.fromisoformat(args.session_date) if args.session_date else None
    statuses = load_paper_runtime_waiting_order_statuses(
        REPO_ROOT / args.targets_config,
        repo_root=REPO_ROOT,
        session_date=session_date,
    )
    if args.json:
        print(
            json.dumps(
                [asdict(status) for status in statuses],
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
        return 0
    for status in statuses:
        parts = [
            f"strategy={status.strategy_code}",
            f"status={status.status}",
            f"session_date={status.session_date.isoformat()}",
            f"total_order_count={status.total_order_count}",
            f"waiting_order_count={status.waiting_order_count}",
            f"current_session_waiting_order_count={status.current_session_waiting_order_count}",
            f"stale_waiting_order_count={status.stale_waiting_order_count}",
            f"terminal_order_count={status.terminal_order_count}",
            f"latest_stale_order_directory={status.latest_stale_order_directory or 'n/a'}",
            f"message={status.message}",
        ]
        print("WaitingOrderStatus: " + " ".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
