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

from tfis.paper import load_paper_runtime_reconciliation_statuses


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show shared TFIS paper runtime reconciliation status by strategy."
    )
    parser.add_argument("--targets-config", default="config/paper_lifecycle_supervisor_targets.yaml")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    statuses = load_paper_runtime_reconciliation_statuses(
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
            f"persisted_state_count={status.persisted_state_count}",
            f"checked_trade_count={status.checked_trade_count}",
            f"conflict_count={status.conflict_count}",
            f"message={status.message}",
        ]
        print("ReconciliationStatus: " + " ".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
