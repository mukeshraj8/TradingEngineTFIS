from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

from .expiry_governance import PaperExpiryGovernance
from .models import SelectedContractBarEvent, SelectedContractQuoteEvent
from .order_state import (
    PaperOrderEvent,
    PaperOrderState,
    PaperOrderStateStore,
    PaperOrderStatus,
    paper_order_is_waiting_for_trigger,
)
from .position_manager import (
    build_paper_position_manager,
    PaperPositionManager,
    PaperPositionManagerResult,
    PaperPositionManagerStatus,
)
from .position_state import PaperPositionState
from .trade_ledger import PaperTradeLedgerStore
from .trade_ledger import paper_trade_manager_status_is_lifecycle_terminal


TERMINAL_POSITION_MANAGER_STATUSES = {
    status
    for status in PaperPositionManagerStatus
    if paper_trade_manager_status_is_lifecycle_terminal(status.value)
}


@dataclass(frozen=True, slots=True)
class PaperLifecycleSupervisorContext:
    session_directory: Path
    session_date: date
    trade_id: str
    selected_contract_symbol: str
    order_state: PaperOrderState | None = None
    position_state: PaperPositionState | None = None


@dataclass(frozen=True, slots=True)
class PaperLifecycleSupervisorStep:
    status: str
    reason_code: str
    fill_price: float | None = None
    entry_price: float | None = None
    exit_price: float | None = None


@dataclass(frozen=True, slots=True)
class PaperLifecycleSupervisorResult:
    context: PaperLifecycleSupervisorContext
    steps: tuple[PaperLifecycleSupervisorStep, ...]
    terminal: bool = False

    @property
    def final_step(self) -> PaperLifecycleSupervisorStep:
        return self.steps[-1]


class PaperLifecycleSupervisor:
    def __init__(
        self,
        *,
        strategy_code: str = "S23",
        order_store: PaperOrderStateStore | None = None,
        position_manager: PaperPositionManager | None = None,
    ) -> None:
        self._order_store = order_store or PaperOrderStateStore()
        self._position_manager = position_manager or build_paper_position_manager(
            strategy_code=strategy_code,
        )

    def expire_waiting_order_from_previous_session(
        self,
        context: PaperLifecycleSupervisorContext,
        *,
        evaluated_at: datetime,
    ) -> PaperLifecycleSupervisorResult | None:
        order_state = context.order_state
        if (
            context.position_state is not None
            or order_state is None
            or not paper_order_is_waiting_for_trigger(order_state.status)
            or order_state.entry_date >= context.session_date
        ):
            return None
        order_state, order_event, _state_path, _events_path = self._order_store.mark_not_filled(
            context.session_directory,
            marked_at=evaluated_at,
            reason_code="paper_order_expired_untriggered_previous_session",
            message=(
                "Pending paper entry orders are session-only. This order did "
                "not trigger on its entry date, so it was cancelled instead of "
                "being carried forward."
            ),
        )
        return PaperLifecycleSupervisorResult(
            context=self._replace_order_context(context, order_state=order_state),
            steps=(self._step_from_order_event(order_event),),
            terminal=True,
        )

    def supervise(
        self,
        context: PaperLifecycleSupervisorContext,
        *,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
        evaluated_at: datetime,
        watch_cutoff_time: time,
        expiry_governance: PaperExpiryGovernance,
        allow_reverse_on_stoploss: bool = False,
        provenance_source_ids: tuple[str, ...] = (),
    ) -> PaperLifecycleSupervisorResult:
        if context.position_state is None:
            return self._supervise_waiting_order(
                context,
                market_events=market_events,
                evaluated_at=evaluated_at,
                watch_cutoff_time=watch_cutoff_time,
                expiry_governance=expiry_governance,
                allow_reverse_on_stoploss=allow_reverse_on_stoploss,
                provenance_source_ids=provenance_source_ids,
            )
        return self._supervise_open_position(
            context,
            market_events=market_events,
            evaluated_at=evaluated_at,
            expiry_governance=expiry_governance,
            allow_reverse_on_stoploss=allow_reverse_on_stoploss,
            provenance_source_ids=provenance_source_ids,
        )

    def _supervise_waiting_order(
        self,
        context: PaperLifecycleSupervisorContext,
        *,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
        evaluated_at: datetime,
        watch_cutoff_time: time,
        expiry_governance: PaperExpiryGovernance,
        allow_reverse_on_stoploss: bool,
        provenance_source_ids: tuple[str, ...],
    ) -> PaperLifecycleSupervisorResult:
        order_state = context.order_state
        if order_state is None:
            raise RuntimeError("Waiting-order supervision requires an order_state.")

        order_state, order_event, _state_path, _events_path = self._order_store.evaluate_waiting_order(
            context.session_directory,
            market_events=market_events,
            evaluated_at=evaluated_at,
        )
        steps: list[PaperLifecycleSupervisorStep] = [self._step_from_order_event(order_event)]
        next_context = self._replace_order_context(context, order_state=order_state)

        if order_state.status is not PaperOrderStatus.PAPER_ORDER_FILLED:
            if evaluated_at.timetz().replace(tzinfo=None) >= watch_cutoff_time:
                order_state, order_event, _state_path, _events_path = self._order_store.mark_not_filled(
                    context.session_directory,
                    marked_at=evaluated_at,
                    reason_code="paper_order_not_triggered_by_watch_cutoff",
                    message=(
                        "Selected option premium did not reach entry before the "
                        "paper watch cutoff, so the pending paper order was "
                        "not filled."
                    ),
                )
                steps.append(self._step_from_order_event(order_event))
                return PaperLifecycleSupervisorResult(
                    context=self._replace_order_context(context, order_state=order_state),
                    steps=tuple(steps),
                    terminal=True,
                )
            return PaperLifecycleSupervisorResult(
                context=next_context,
                steps=tuple(steps),
                terminal=False,
            )

        opened = self._position_manager.open_from_filled_order(
            context.session_directory,
            order_state=order_state,
            provenance_source_ids=("paper_order_state.json", "s23_paper_position_watch"),
        )
        steps.append(self._step_from_position_manager_result(opened, entry_price=opened.state.entry_price))
        position_context = PaperLifecycleSupervisorContext(
            session_directory=context.session_directory,
            session_date=context.session_date,
            trade_id=PaperTradeLedgerStore.trade_id_for_state(opened.state),
            selected_contract_symbol=opened.state.selected_contract_symbol,
            position_state=opened.state,
        )
        position_result = self._supervise_open_position(
            position_context,
            market_events=market_events,
            evaluated_at=evaluated_at,
            expiry_governance=expiry_governance,
            allow_reverse_on_stoploss=allow_reverse_on_stoploss,
            provenance_source_ids=provenance_source_ids,
        )
        return PaperLifecycleSupervisorResult(
            context=position_result.context,
            steps=tuple([*steps, *position_result.steps]),
            terminal=position_result.terminal,
        )

    def _supervise_open_position(
        self,
        context: PaperLifecycleSupervisorContext,
        *,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
        evaluated_at: datetime,
        expiry_governance: PaperExpiryGovernance,
        allow_reverse_on_stoploss: bool,
        provenance_source_ids: tuple[str, ...],
    ) -> PaperLifecycleSupervisorResult:
        if context.position_state is None:
            raise RuntimeError("Open-position supervision requires a position_state.")
        result = self._position_manager.process_session(
            context.session_directory,
            session_date=context.session_date,
            market_events=market_events,
            evaluated_at=evaluated_at,
            expiry_governance=expiry_governance,
            allow_reverse_on_stoploss=allow_reverse_on_stoploss,
            provenance_source_ids=provenance_source_ids,
        )
        next_context = PaperLifecycleSupervisorContext(
            session_directory=context.session_directory,
            session_date=context.session_date,
            trade_id=context.trade_id,
            selected_contract_symbol=result.state.selected_contract_symbol,
            position_state=result.state,
        )
        return PaperLifecycleSupervisorResult(
            context=next_context,
            steps=(self._step_from_position_manager_result(result),),
            terminal=result.status in TERMINAL_POSITION_MANAGER_STATUSES,
        )

    @staticmethod
    def _replace_order_context(
        context: PaperLifecycleSupervisorContext,
        *,
        order_state: PaperOrderState,
    ) -> PaperLifecycleSupervisorContext:
        return PaperLifecycleSupervisorContext(
            session_directory=context.session_directory,
            session_date=context.session_date,
            trade_id=context.trade_id,
            selected_contract_symbol=order_state.selected_contract_symbol,
            order_state=order_state,
        )

    @staticmethod
    def _step_from_order_event(event: PaperOrderEvent) -> PaperLifecycleSupervisorStep:
        return PaperLifecycleSupervisorStep(
            status=event.status.value,
            reason_code=event.reason_code,
            fill_price=event.fill_price,
        )

    @staticmethod
    def _step_from_position_manager_result(
        result: PaperPositionManagerResult,
        *,
        entry_price: float | None = None,
    ) -> PaperLifecycleSupervisorStep:
        return PaperLifecycleSupervisorStep(
            status=result.status.value,
            reason_code=result.event.reason_code,
            entry_price=entry_price,
            exit_price=result.event.exit_price,
        )


S23PaperLifecycleSupervisorContext = PaperLifecycleSupervisorContext
S23PaperLifecycleSupervisorStep = PaperLifecycleSupervisorStep
S23PaperLifecycleSupervisorResult = PaperLifecycleSupervisorResult
S23PaperLifecycleSupervisor = PaperLifecycleSupervisor


__all__ = [
    "S23PaperLifecycleSupervisor",
    "S23PaperLifecycleSupervisorContext",
    "S23PaperLifecycleSupervisorResult",
    "S23PaperLifecycleSupervisorStep",
    "TERMINAL_POSITION_MANAGER_STATUSES",
    "PaperLifecycleSupervisor",
    "PaperLifecycleSupervisorContext",
    "PaperLifecycleSupervisorResult",
    "PaperLifecycleSupervisorStep",
]
