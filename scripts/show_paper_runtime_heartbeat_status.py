from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.paper import load_paper_runtime_heartbeat_statuses


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show shared TFIS paper runtime heartbeat status by strategy."
    )
    parser.add_argument("--targets-config", default="config/paper_lifecycle_supervisor_targets.yaml")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    statuses = load_paper_runtime_heartbeat_statuses(
        REPO_ROOT / args.targets_config,
        repo_root=REPO_ROOT,
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
            f"backend={status.backend}",
            f"heartbeat_count={status.heartbeat_count}",
        ]
        if status.latest_timestamp:
            parts.append(f"latest_timestamp={status.latest_timestamp}")
        if status.latest_trade_id:
            parts.append(f"latest_trade_id={status.latest_trade_id}")
        if status.latest_owner_id:
            parts.append(f"owner_id={status.latest_owner_id}")
        if status.latest_state_directory:
            parts.append(f"state_directory={status.latest_state_directory}")
        if status.latest_selected_contract_symbol:
            parts.append(f"symbol={status.latest_selected_contract_symbol}")
        if status.latest_runtime_status:
            parts.append(f"runtime_status={status.latest_runtime_status}")
        if status.latest_reason_code:
            parts.append(f"reason_code={status.latest_reason_code}")
        if status.latest_supervisor_pid is not None:
            parts.append(f"supervisor_pid={status.latest_supervisor_pid}")
        if status.age_seconds is not None:
            parts.append(f"age_seconds={status.age_seconds:.1f}")
        parts.append(f"message={status.message}")
        print("HeartbeatStatus: " + " ".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
