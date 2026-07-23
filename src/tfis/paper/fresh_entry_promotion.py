from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from tfis.importers import load_strategy_rule

from .decision_summary_discovery import discover_trade_decision_summaries
from .order_state import PaperOrderDecisionIntent, PaperOrderStateDiscovery, PaperOrderStateStore
from .position_discovery import PaperOpenPositionDiscovery
from .session_discovery import (
    find_latest_supervised_session_dir,
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


@dataclass(frozen=True, slots=True)
class PaperFreshEntryBlockedDecisionCandidate:
    session_dir: Path
    branch_directory: Path
    summary_path: Path
    branch: str
    summary: PaperOrderDecisionIntent
    order_state_path: Path | None = None


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

    active_positions = blocking_position_paths(artifact_root_path)
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
    for candidate in candidates:
        strategy_rule = load_strategy(candidate.branch)
        order_path = candidate.order_state_path or (candidate.branch_directory / "paper_order_state.json")
        if candidate.order_state_path is not None:
            promotions.append(
                PaperFreshEntryPromotionRecord(
                    branch=candidate.branch,
                    status="already_has_order_state",
                    order_state_json=str(order_path),
                )
            )
            continue
        if dry_run:
            promotions.append(
                PaperFreshEntryPromotionRecord(
                    branch=candidate.branch,
                    status="dry_run_eligible",
                    order_state_json=str(order_path),
                )
            )
            continue
        _state, state_path, _events_path = PaperOrderStateStore().create_waiting_order_from_live_decision(
            candidate.branch_directory,
            strategy_rule=strategy_rule,
            decision=candidate.summary,
            created_at=created_at,
            provenance_source_ids=(str(candidate.summary_path), str(metadata_path)),
        )
        mark_metadata_promoted(
            metadata=metadata,
            branch=candidate.branch,
            order_state_path=state_path,
            promoted_at=created_at,
        )
        promotions.append(
            PaperFreshEntryPromotionRecord(
                branch=candidate.branch,
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
    latest_session = find_latest_supervised_session_dir(
        day_root,
        session_date=session_date,
        session_id_prefix=session_id_prefix,
    )
    if latest_session is None:
        raise PaperFreshEntryPromotionError(
            f"No supervised session directory found under {day_root}"
        )
    return latest_session


def promotion_candidates(
    session_dir: Path,
    *,
    branch: str | None,
) -> list[PaperFreshEntryBlockedDecisionCandidate]:
    existing_orders = {
        candidate.state_directory.resolve(): candidate.state_directory.resolve() / "paper_order_state.json"
        for candidate in PaperOrderStateDiscovery().find_orders((session_dir,))
    }
    candidates: list[PaperFreshEntryBlockedDecisionCandidate] = []
    for candidate in discover_trade_decision_summaries(session_dir):
        payload = candidate.payload
        summary = candidate.summary
        branch_name = candidate.branch
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
        structured_summary = summary_from_payload(payload)
        candidates.append(
            PaperFreshEntryBlockedDecisionCandidate(
                session_dir=session_dir,
                branch_directory=candidate.branch_directory,
                summary_path=candidate.summary_path,
                branch=branch_name,
                summary=structured_summary,
                order_state_path=(
                    candidate.order_state_path
                    or existing_orders.get(candidate.branch_directory.resolve())
                ),
            )
        )
    return candidates


def summary_from_payload(payload: dict[str, Any]) -> PaperOrderDecisionIntent:
    raw_summary = payload.get("summary", payload)
    if not isinstance(raw_summary, dict):
        raise PaperFreshEntryPromotionError(
            "Invalid trade_decision_summary.json: summary must be an object"
        )
    return PaperOrderDecisionIntent(
        status=str(raw_summary.get("status") or ""),
        session_date=_date_from_payload(raw_summary, "session_date"),
        strategy_code=str(raw_summary.get("strategy_code") or ""),
        strategy_branch=str(raw_summary.get("strategy_branch") or ""),
        lots=int(raw_summary.get("lots") or 0),
        quantity=int(raw_summary.get("quantity") or 0),
        selected_contract_symbol=_optional_text(raw_summary.get("selected_contract_symbol")),
        selected_contract_expiry=_optional_date_from_payload(raw_summary, "selected_contract_expiry"),
        selected_contract_strike=_optional_float(raw_summary.get("selected_contract_strike")),
        selected_contract_option_type=_optional_text(raw_summary.get("selected_contract_option_type")),
        planned_entry_price=_optional_float(raw_summary.get("planned_entry_price")),
        target_price=_optional_float(raw_summary.get("target_price")),
        stoploss_price=_optional_float(raw_summary.get("stoploss_price")),
        fsl_price=_optional_float(raw_summary.get("fsl_price")),
    )


def blocking_position_paths(artifact_root: Path) -> list[Path]:
    return [
        candidate.state_path
        for candidate in PaperOpenPositionDiscovery().find_positions_blocking_new_entry(
            (artifact_root,)
        )
    ]


active_position_paths = blocking_position_paths


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


def _date_from_payload(payload: dict[str, Any], field_name: str) -> date:
    parsed = _optional_date_from_payload(payload, field_name)
    if parsed is None:
        raise PaperFreshEntryPromotionError(f"Missing required date field: {field_name}")
    return parsed


def _optional_date_from_payload(payload: dict[str, Any], field_name: str) -> date | None:
    value = payload.get(field_name)
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise PaperFreshEntryPromotionError(f"{field_name} must be an ISO date") from exc


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


__all__ = [
    "PaperFreshEntryBlockedDecisionCandidate",
    "PaperFreshEntryPromotionError",
    "PaperFreshEntryPromotionRecord",
    "PaperFreshEntryPromotionSummary",
    "blocking_position_paths",
    "active_position_paths",
    "latest_session_dir",
    "mark_metadata_promoted",
    "promote_blocked_fresh_entries",
    "promotion_candidates",
    "summary_from_payload",
]
