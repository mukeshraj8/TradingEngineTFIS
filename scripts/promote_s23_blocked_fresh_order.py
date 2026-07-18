from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.importers import load_strategy_rule
from tfis.paper import (
    PaperFreshEntryPromotionError,
    promote_blocked_fresh_entries,
)


_DEFAULT_ARTIFACT_ROOT = Path("data/strategies/S23/fyers_morning_supervised_decision")
def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Promote today's blocked S23 fresh-entry decision to a waiting paper order "
            "after the carry-forward position has exited."
        )
    )
    parser.add_argument("--date", required=True, help="Session date in YYYY-MM-DD format.")
    parser.add_argument(
        "--artifact-root",
        default=str(_DEFAULT_ARTIFACT_ROOT),
        help="Durable S23 artifact root.",
    )
    parser.add_argument(
        "--branch",
        help="Optional S23 branch unique code to promote. Defaults to all eligible blocked READY branches.",
    )
    parser.add_argument(
        "--created-at",
        help="Order timestamp override as ISO datetime. Defaults to current local time.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report eligible promotions without writing paper order state.",
    )
    args = parser.parse_args()

    artifact_root = _resolve_path(args.artifact_root)
    session_date = args.date.strip()
    day_root = artifact_root / session_date
    if not day_root.exists():
        raise SystemExit(f"No S23 artifact day directory exists for {session_date}: {day_root}")

    created_at = (
        datetime.fromisoformat(args.created_at)
        if args.created_at
        else datetime.now().astimezone()
    )
    try:
        summary = promote_blocked_fresh_entries(
            artifact_root,
            session_date=datetime.fromisoformat(f"{session_date}T00:00:00").date(),
            created_at=created_at,
            branch=args.branch,
            dry_run=args.dry_run,
            strategy_loader=_load_strategy_for_branch,
        )
    except PaperFreshEntryPromotionError as exc:
        raise SystemExit(str(exc))

    print(
        json.dumps(
            {
                "session_dir": str(summary.session_dir),
                "promotions": [
                    {
                        "branch": item.branch,
                        "status": item.status,
                        "order_state_json": item.order_state_json,
                    }
                    for item in summary.promotions
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _resolve_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _load_strategy_for_branch(branch: str):
    strategy_root = PROJECT_ROOT / "config" / "strategies"
    for strategy_path in sorted(strategy_root.rglob("strategy.yaml")):
        rule = load_strategy_rule(strategy_path)
        if rule.unique_code == branch:
            return rule
    raise SystemExit(f"No strategy.yaml found for branch {branch!r}")


if __name__ == "__main__":
    raise SystemExit(main())
