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

from tfis.paper import load_paper_runtime_fresh_entry_handoff_statuses


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show shared TFIS paper fresh-entry handoff status by strategy."
    )
    parser.add_argument("--targets-config", default="config/paper_lifecycle_supervisor_targets.yaml")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    statuses = load_paper_runtime_fresh_entry_handoff_statuses(
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
            f"fresh_close_count={status.fresh_close_count}",
            f"resolved_count={status.resolved_count}",
            f"unresolved_count={status.unresolved_count}",
            f"message={status.message}",
        ]
        print("FreshEntryHandoffStatus: " + " ".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
