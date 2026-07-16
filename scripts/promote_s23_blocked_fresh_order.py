from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.importers import load_strategy_rule
from tfis.paper.live_decision import S23PaperTradeDecisionSummary
from tfis.paper.order_state import S23PaperOrderStateStore
from tfis.paper.position_state import (
    S23PaperPositionStateError,
    S23PaperPositionStateStore,
    paper_position_blocks_new_entry,
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

    active_positions = _active_position_paths(artifact_root)
    if active_positions:
        rendered = "\n".join(f"- {path}" for path in active_positions)
        raise SystemExit(
            "Refusing to promote a fresh S23 order because active paper position(s) still exist:\n"
            + rendered
        )

    session_dir = _latest_session_dir(day_root, session_date)
    metadata_path = session_dir / "scheduled_run_metadata.json"
    metadata = _read_json(metadata_path)
    created_at = (
        datetime.fromisoformat(args.created_at)
        if args.created_at
        else datetime.now().astimezone()
    )
    candidates = _promotion_candidates(session_dir, branch=args.branch)
    if not candidates:
        raise SystemExit("No eligible blocked READY S23 branch decisions found to promote.")

    promoted: list[dict[str, str]] = []
    for summary_path, payload in candidates:
        summary = _summary_from_payload(payload)
        strategy_rule = _load_strategy_for_branch(summary.strategy_branch)
        order_path = summary_path.parent / "paper_order_state.json"
        if order_path.exists():
            promoted.append(
                {
                    "branch": summary.strategy_branch,
                    "status": "already_has_order_state",
                    "order_state_json": str(order_path),
                }
            )
            continue
        if not args.dry_run:
            _state, state_path, _events_path = S23PaperOrderStateStore().create_waiting_order_from_live_decision(
                summary_path.parent,
                strategy_rule=strategy_rule,
                decision=summary,
                created_at=created_at,
                provenance_source_ids=(str(summary_path), str(metadata_path)),
            )
            _mark_metadata_promoted(
                metadata=metadata,
                branch=summary.strategy_branch,
                order_state_path=state_path,
                promoted_at=created_at,
            )
            promoted.append(
                {
                    "branch": summary.strategy_branch,
                    "status": "promoted_to_waiting_order",
                    "order_state_json": str(state_path),
                }
            )
        else:
            promoted.append(
                {
                    "branch": summary.strategy_branch,
                    "status": "dry_run_eligible",
                    "order_state_json": str(order_path),
                }
            )

    if not args.dry_run:
        metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    print(json.dumps({"session_dir": str(session_dir), "promotions": promoted}, indent=2, sort_keys=True))
    return 0


def _resolve_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _latest_session_dir(day_root: Path, session_date: str) -> Path:
    candidates = sorted(
        (
            path
            for path in day_root.iterdir()
            if path.is_dir() and path.name.endswith(session_date)
        ),
        key=lambda path: path.stat().st_mtime,
    )
    if not candidates:
        raise SystemExit(f"No S23 session directory found under {day_root}")
    return candidates[-1]


def _promotion_candidates(session_dir: Path, *, branch: str | None) -> list[tuple[Path, dict[str, Any]]]:
    candidates: list[tuple[Path, dict[str, Any]]] = []
    for summary_path in sorted(session_dir.rglob("trade_decision_summary.json")):
        payload = _read_json(summary_path)
        summary = payload.get("summary", payload)
        if not isinstance(summary, dict):
            continue
        branch_name = str(summary.get("strategy_branch") or summary_path.parent.name)
        if branch and branch_name != branch:
            continue
        if summary.get("status") != "READY":
            continue
        if not summary.get("selected_contract_symbol"):
            continue
        if not summary.get("order_placement_blocked"):
            continue
        if summary.get("order_placement_block_reason") != "OPEN_CARRY_FORWARD_POSITION":
            continue
        candidates.append((summary_path, payload))
    return candidates


def _summary_from_payload(payload: dict[str, Any]) -> S23PaperTradeDecisionSummary:
    raw_summary = payload.get("summary", payload)
    if not isinstance(raw_summary, dict):
        raise SystemExit("Invalid trade_decision_summary.json: summary must be an object")
    values: dict[str, Any] = {}
    for field in fields(S23PaperTradeDecisionSummary):
        value = raw_summary.get(field.name)
        if field.name == "session_date" and isinstance(value, str):
            from datetime import date

            value = date.fromisoformat(value)
        elif field.name in {
            "required_market_aliases",
            "required_option_aliases",
            "checkpoint_labels",
            "contract_selection_attempted_expiries",
            "ranked_candidates",
            "governance_event_types",
            "notes",
        }:
            value = tuple(value or ())
        elif field.name == "rejected_candidate_counts":
            value = {str(k): int(v) for k, v in dict(value or {}).items()}
        elif field.name in {"market_levels", "runtime_values"}:
            value = dict(value or {})
        values[field.name] = value
    return S23PaperTradeDecisionSummary(**values)


def _load_strategy_for_branch(branch: str):
    strategy_root = PROJECT_ROOT / "config" / "strategies"
    for strategy_path in sorted(strategy_root.rglob("strategy.yaml")):
        rule = load_strategy_rule(strategy_path)
        if rule.unique_code == branch:
            return rule
    raise SystemExit(f"No strategy.yaml found for branch {branch!r}")


def _active_position_paths(artifact_root: Path) -> list[Path]:
    active: list[Path] = []
    store = S23PaperPositionStateStore()
    for state_path in sorted(artifact_root.rglob("paper_position_state.json")):
        try:
            state = store.load_state(state_path.parent)
        except S23PaperPositionStateError:
            continue
        if paper_position_blocks_new_entry(state.lifecycle_status):
            active.append(state_path)
    return active


def _mark_metadata_promoted(
    *,
    metadata: dict[str, Any],
    branch: str,
    order_state_path: Path,
    promoted_at: datetime,
) -> None:
    branch_order_state_json = metadata.setdefault("branch_order_state_json", {})
    branch_order_state_json[branch] = str(order_state_path)

    blocked = metadata.setdefault("branch_order_placement_blocked", {})
    blocked[branch] = False

    promoted = metadata.setdefault("branch_order_placement_promoted_after_carry_exit", {})
    promoted[branch] = True

    promoted_at_map = metadata.setdefault("branch_order_placement_promoted_at", {})
    promoted_at_map[branch] = promoted_at.isoformat()

    promoted_reason = metadata.setdefault("branch_order_placement_promotion_reason", {})
    promoted_reason[branch] = (
        "Prior carry-forward position exited and no active S23 paper position remained; "
        "promoted the blocked READY decision to a waiting paper order."
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing required JSON file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Expected JSON object in {path}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
