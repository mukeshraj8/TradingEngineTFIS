from __future__ import annotations

import json
from dataclasses import dataclass, fields
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from tfis.importers import load_strategy_rule

from .live_decision import S23PaperTradeDecisionSummary
from .order_state import S23PaperOrderStateStore
from .position_state import (
    S23PaperPositionStateStatus,
    S23PaperPositionStateError,
    S23PaperPositionStateStore,
    paper_position_blocks_new_entry,
)


class PaperFreshEntryPromotionError(RuntimeError):
    """Raised when a blocked fresh-entry decision cannot be promoted safely."""


@dataclass(frozen=True, slots=True)
class PaperFreshEntryPromotionRecord:
    branch: str
    status: str
    order_state_json: str


@dataclass(frozen=True, slots=True)
class PaperFreshEntryPromotionSummary:
    session_dir: Path
    promotions: tuple[PaperFreshEntryPromotionRecord, ...]


def promote_blocked_fresh_entries(
    artifact_root: str | Path,
    *,
    session_date: date,
    created_at: datetime,
    branch: str | None = None,
    dry_run: bool = False,
    session_id_prefix: str | None = None,
    strategy_loader: Callable[[str], Any] | None = None,
) -> PaperFreshEntryPromotionSummary:
    artifact_root_path = Path(artifact_root)
    day_root = artifact_root_path / session_date.isoformat()
    if not day_root.exists():
        raise PaperFreshEntryPromotionError(
            f"No strategy artifact day directory exists for {session_date.isoformat()}: {day_root}"
        )

    active_positions = active_position_paths(artifact_root_path)
    if active_positions:
        rendered = "\n".join(f"- {path}" for path in active_positions)
        raise PaperFreshEntryPromotionError(
            "Refusing to promote a blocked fresh-entry decision because active paper "
            f"position(s) still exist:\n{rendered}"
        )

    session_dir = latest_session_dir(
        day_root,
        session_date=session_date,
        session_id_prefix=session_id_prefix,
    )
    metadata_path = session_dir / "scheduled_run_metadata.json"
    metadata = _read_json(metadata_path)
    candidates = promotion_candidates(session_dir, branch=branch)
    if not candidates:
        raise PaperFreshEntryPromotionError(
            "No eligible blocked READY branch decisions were found to promote."
        )

    load_strategy = strategy_loader or _default_strategy_loader
    promotions: list[PaperFreshEntryPromotionRecord] = []
    for summary_path, payload in candidates:
        summary = summary_from_payload(payload)
        strategy_rule = load_strategy(summary.strategy_branch)
        order_path = summary_path.parent / "paper_order_state.json"
        if order_path.exists():
            promotions.append(
                PaperFreshEntryPromotionRecord(
                    branch=summary.strategy_branch,
                    status="already_has_order_state",
                    order_state_json=str(order_path),
                )
            )
            continue
        if dry_run:
            promotions.append(
                PaperFreshEntryPromotionRecord(
                    branch=summary.strategy_branch,
                    status="dry_run_eligible",
                    order_state_json=str(order_path),
                )
            )
            continue
        _state, state_path, _events_path = S23PaperOrderStateStore().create_waiting_order_from_live_decision(
            summary_path.parent,
            strategy_rule=strategy_rule,
            decision=summary,
            created_at=created_at,
            provenance_source_ids=(str(summary_path), str(metadata_path)),
        )
        mark_metadata_promoted(
            metadata=metadata,
            branch=summary.strategy_branch,
            order_state_path=state_path,
            promoted_at=created_at,
        )
        promotions.append(
            PaperFreshEntryPromotionRecord(
                branch=summary.strategy_branch,
                status="promoted_to_waiting_order",
                order_state_json=str(state_path),
            )
        )

    if not dry_run:
        metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return PaperFreshEntryPromotionSummary(
        session_dir=session_dir,
        promotions=tuple(promotions),
    )


def latest_session_dir(
    day_root: Path,
    *,
    session_date: date,
    session_id_prefix: str | None = None,
) -> Path:
    suffix = session_date.isoformat()
    candidates = sorted(
        (
            path
            for path in day_root.iterdir()
            if path.is_dir()
            and path.name.endswith(suffix)
            and (not session_id_prefix or path.name.startswith(session_id_prefix))
        ),
        key=lambda path: path.stat().st_mtime,
    )
    if not candidates:
        raise PaperFreshEntryPromotionError(
            f"No supervised session directory found under {day_root}"
        )
    return candidates[-1]


def promotion_candidates(
    session_dir: Path,
    *,
    branch: str | None,
) -> list[tuple[Path, dict[str, Any]]]:
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


def summary_from_payload(payload: dict[str, Any]) -> S23PaperTradeDecisionSummary:
    raw_summary = payload.get("summary", payload)
    if not isinstance(raw_summary, dict):
        raise PaperFreshEntryPromotionError(
            "Invalid trade_decision_summary.json: summary must be an object"
        )
    values: dict[str, Any] = {}
    for field in fields(S23PaperTradeDecisionSummary):
        value = raw_summary.get(field.name)
        if field.name == "session_date" and isinstance(value, str):
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


def active_position_paths(artifact_root: Path) -> list[Path]:
    active: list[Path] = []
    store = S23PaperPositionStateStore()
    for state_path in sorted(artifact_root.rglob("paper_position_state.json")):
        try:
            state = store.load_state(state_path.parent)
        except S23PaperPositionStateError:
            continue
        if paper_position_blocks_new_entry(state.lifecycle_status) or state.lifecycle_status is S23PaperPositionStateStatus.PAPER_REVERSE_ENTRY_REQUIRED:
            active.append(state_path)
    return active


def mark_metadata_promoted(
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
        "Prior carry-forward position exited and no active paper position remained; "
        "promoted the blocked READY decision to a waiting paper order."
    )


def _default_strategy_loader(branch: str):
    strategy_root = Path(__file__).resolve().parents[3] / "config" / "strategies"
    for strategy_path in sorted(strategy_root.rglob("strategy.yaml")):
        rule = load_strategy_rule(strategy_path)
        if rule.unique_code == branch:
            return rule
    raise PaperFreshEntryPromotionError(f"No strategy.yaml found for branch {branch!r}")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PaperFreshEntryPromotionError(f"Missing required JSON file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PaperFreshEntryPromotionError(f"Expected JSON object in {path}")
    return payload


__all__ = [
    "PaperFreshEntryPromotionError",
    "PaperFreshEntryPromotionRecord",
    "PaperFreshEntryPromotionSummary",
    "active_position_paths",
    "latest_session_dir",
    "mark_metadata_promoted",
    "promote_blocked_fresh_entries",
    "promotion_candidates",
    "summary_from_payload",
]
