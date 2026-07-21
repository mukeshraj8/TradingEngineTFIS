from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

from .order_state import (
    S23PaperOrderStateDiscovery,
    S23PaperOrderState,
    S23PaperOrderStateError,
    S23PaperOrderStateStore,
    S23PaperOrderStatus,
    paper_order_is_waiting_for_trigger,
)


@dataclass(frozen=True, slots=True)
class S23PaperOrderFinalizerDecision:
    order_directory: Path
    selected_contract_symbol: str
    entry_date: date | None
    previous_status: str | None
    final_status: str | None
    action: str
    reason_code: str
    message: str


@dataclass(frozen=True, slots=True)
class S23PaperOrderFinalizerSummary:
    artifact_root: Path
    session_date: date
    marked_at: datetime
    cutoff_time: time
    dry_run: bool
    scanned_count: int
    finalized_count: int
    skipped_count: int
    decisions: tuple[S23PaperOrderFinalizerDecision, ...]


class S23PaperOrderFinalizer:
    """Marks session-only S23 waiting paper orders as not filled after cutoff."""

    def __init__(self, *, order_store: S23PaperOrderStateStore | None = None) -> None:
        self._order_store = order_store or S23PaperOrderStateStore()
        self._order_discovery = S23PaperOrderStateDiscovery(order_store=self._order_store)

    def finalize(
        self,
        artifact_root: str | Path,
        *,
        session_date: date,
        marked_at: datetime,
        cutoff_time: time,
        include_prior_sessions: bool = False,
        allow_before_cutoff: bool = False,
        dry_run: bool = False,
    ) -> S23PaperOrderFinalizerSummary:
        root = Path(artifact_root)
        decisions: list[S23PaperOrderFinalizerDecision] = []
        if not root.exists():
            return S23PaperOrderFinalizerSummary(
                artifact_root=root,
                session_date=session_date,
                marked_at=marked_at,
                cutoff_time=cutoff_time,
                dry_run=dry_run,
                scanned_count=0,
                finalized_count=0,
                skipped_count=0,
                decisions=(),
            )

        after_cutoff = marked_at.timetz().replace(tzinfo=None) >= cutoff_time
        for candidate in self._order_discovery.find_orders((root,)):
            order_dir = candidate.state_directory
            state = candidate.state
            eligibility = self._eligible_waiting_state(
                state,
                session_date=session_date,
                after_cutoff=after_cutoff,
                include_prior_sessions=include_prior_sessions,
                allow_before_cutoff=allow_before_cutoff,
            )
            if eligibility is not None:
                decisions.append(
                    S23PaperOrderFinalizerDecision(
                        order_directory=order_dir,
                        selected_contract_symbol=state.selected_contract_symbol,
                        entry_date=state.entry_date,
                        previous_status=state.status.value,
                        final_status=state.status.value,
                        action="SKIPPED",
                        reason_code=eligibility,
                        message=self._skip_message(eligibility, state, session_date, cutoff_time),
                    )
                )
                continue

            reason_code = (
                "paper_order_expired_untriggered_previous_session_sweeper"
                if state.entry_date < session_date
                else "paper_order_not_triggered_by_cutoff_sweeper"
            )
            message = (
                "Pending paper entry orders are session-only. The cutoff "
                "finalizer found this order still waiting after its entry "
                "session cutoff, so it was marked not filled instead of being "
                "carried forward."
            )
            final_status = S23PaperOrderStatus.PAPER_ORDER_NOT_FILLED.value
            if not dry_run:
                updated_state, _event, _state_path, _events_path = self._order_store.mark_not_filled(
                    order_dir,
                    marked_at=marked_at,
                    reason_code=reason_code,
                    message=message,
                )
                final_status = updated_state.status.value
            decisions.append(
                S23PaperOrderFinalizerDecision(
                    order_directory=order_dir,
                    selected_contract_symbol=state.selected_contract_symbol,
                    entry_date=state.entry_date,
                    previous_status=state.status.value,
                    final_status=final_status,
                    action="WOULD_FINALIZE" if dry_run else "FINALIZED",
                    reason_code=reason_code,
                    message=message,
                )
            )

        finalized_count = sum(1 for decision in decisions if decision.action in {"FINALIZED", "WOULD_FINALIZE"})
        return S23PaperOrderFinalizerSummary(
            artifact_root=root,
            session_date=session_date,
            marked_at=marked_at,
            cutoff_time=cutoff_time,
            dry_run=dry_run,
            scanned_count=len(decisions),
            finalized_count=finalized_count,
            skipped_count=len(decisions) - finalized_count,
            decisions=tuple(decisions),
        )

    @staticmethod
    def _eligible_waiting_state(
        state: S23PaperOrderState,
        *,
        session_date: date,
        after_cutoff: bool,
        include_prior_sessions: bool,
        allow_before_cutoff: bool,
    ) -> str | None:
        if not paper_order_is_waiting_for_trigger(state.status):
            return "paper_order_not_waiting_for_trigger"
        if state.entry_date > session_date:
            return "paper_order_entry_date_after_session"
        if state.entry_date < session_date and not include_prior_sessions:
            return "paper_order_prior_session_not_included"
        if state.entry_date == session_date and not after_cutoff and not allow_before_cutoff:
            return "paper_order_cutoff_not_reached"
        return None

    @staticmethod
    def _skip_message(
        reason_code: str,
        state: S23PaperOrderState,
        session_date: date,
        cutoff_time: time,
    ) -> str:
        if reason_code == "paper_order_not_waiting_for_trigger":
            return f"Order status is {state.status.value}; no waiting-order finalization is needed."
        if reason_code == "paper_order_entry_date_after_session":
            return f"Order entry date {state.entry_date.isoformat()} is after session {session_date.isoformat()}."
        if reason_code == "paper_order_prior_session_not_included":
            return (
                f"Order entry date {state.entry_date.isoformat()} is before session "
                f"{session_date.isoformat()}; rerun with include-prior to repair older stale orders."
            )
        if reason_code == "paper_order_cutoff_not_reached":
            return f"Session cutoff {cutoff_time.isoformat(timespec='minutes')} has not been reached."
        return "Order was skipped by the finalizer."


__all__ = [
    "PaperOrderFinalizer",
    "PaperOrderFinalizerDecision",
    "PaperOrderFinalizerSummary",
    "S23PaperOrderFinalizer",
    "S23PaperOrderFinalizerDecision",
    "S23PaperOrderFinalizerSummary",
]


PaperOrderFinalizerDecision = S23PaperOrderFinalizerDecision
PaperOrderFinalizerSummary = S23PaperOrderFinalizerSummary
PaperOrderFinalizer = S23PaperOrderFinalizer
