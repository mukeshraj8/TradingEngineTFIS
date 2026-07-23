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

from tfis.paper import load_paper_runtime_lifecycle_audit_statuses


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show shared TFIS paper lifecycle-supervisor audit status by strategy."
    )
    parser.add_argument("--targets-config", default="config/paper_lifecycle_supervisor_targets.yaml")
    parser.add_argument("--stale-after-seconds", type=float, default=300.0)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    statuses = load_paper_runtime_lifecycle_audit_statuses(
        REPO_ROOT / args.targets_config,
        repo_root=REPO_ROOT,
        stale_after_seconds=args.stale_after_seconds,
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
            f"managed_state_count={status.managed_state_count}",
            f"audit_state_count={status.audit_state_count}",
            f"missing_audit_count={status.missing_audit_count}",
            f"stale_audit_count={status.stale_audit_count}",
            f"invalid_audit_count={status.invalid_audit_count}",
            f"actionable_state_count={status.actionable_state_count}",
            f"latest_event_type={status.latest_event_type or 'n/a'}",
            f"latest_reason_code={status.latest_reason_code or 'n/a'}",
            f"message={status.message}",
        ]
        print("LifecycleAuditStatus: " + " ".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
