from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.replay.s21_archived_session import (
    S21ArchivedStrategySessionAdapter,
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Discover durable S21 strategy sessions and expose them to replay."
    )
    ap.add_argument(
        "--source-root",
        default="data/strategies/S21/fyers_morning_supervised_decision",
    )
    ap.add_argument(
        "--compatibility-root",
        default="reports/s21_archived_session_views",
    )
    ap.add_argument(
        "--index-output",
        default="reports/s21_archived_session_views/session_index.json",
    )
    ap.add_argument("--session-date", action="append")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--replace-existing", action="store_true")
    ap.add_argument("--index-only", action="store_true")
    args = ap.parse_args()

    adapter = S21ArchivedStrategySessionAdapter(REPO_ROOT / args.source_root)
    dates = adapter.discover_dates()
    print(f"Discovered {len(dates)} durable S21 sessions")
    for d in dates:
        session = adapter.load(d)
        print(
            f"{d.isoformat()}: 0916_ready={session.checkpoint_0916.market_evidence_ready} "
            f"original_decision={session.has_original_decision_evidence} "
            f"selected_contract_events={session.has_persisted_selected_contract_events}"
        )

    index_path = adapter.write_index(REPO_ROOT / args.index_output)
    print(f"Index: {index_path}")

    if args.index_only:
        return 0

    requested: tuple[date, ...]
    if args.all:
        requested = dates
    elif args.session_date:
        requested = tuple(date.fromisoformat(x) for x in args.session_date)
    else:
        raise SystemExit("Choose --all, one or more --session-date, or --index-only.")

    for d in requested:
        link = adapter.materialize_compatibility_view(
            session_date=d,
            compatibility_root=REPO_ROOT / args.compatibility_root,
            replace_existing=args.replace_existing,
        )
        print(f"VIEW {d.isoformat()}: {link} -> {link.resolve()}")

    print()
    print("Existing replay builder compatibility root:")
    print(REPO_ROOT / args.compatibility_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
