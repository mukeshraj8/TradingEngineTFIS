from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

from .expiry_governance import S23PaperExpiryGovernance
from .models import SelectedContractBarEvent, SelectedContractQuoteEvent
from .order_state import S23PaperOrderEvent, S23PaperOrderState, S23PaperOrderStateStore, S23PaperOrderStatus
from .position_manager import (
    S23PaperPositionManager,
    S23PaperPositionManagerResult,
    S23PaperPositionManagerStatus,
)
from .position_state import S23PaperPositionState
from .trade_ledger import S23PaperTradeLedgerStore


TERMINAL_POSITION_MANAGER_STATUSES = {
    S23PaperPositionManagerStatus.PAPER_POSITION_TARGET_HIT,
    S23PaperPositionManagerStatus.PAPER_POSITION_STOPLOSS_HIT,
    S23PaperPositionManagerStatus.PAPER_POSITION_FORCE_CLOSED,
    S23PaperPositionManagerStatus.PAPER_POSITION_ROLLOVER_REQUIRED,
    S23PaperPositionManagerStatus.PAPER_POSITION_REVERSE_ENTRY_REQUIRED,
    S23PaperPositionManagerStatus.PAPER_POSITION_FRESH_ENTRY_REQUIRED,
    S23PaperPositionManagerStatus.PAPER_POSITION_ALREADY_CLOSED,
}


@dataclass(frozen=True, slots=True)
class S23PaperLifecycleSupervisorContext:
    session_directory: Path
    session_date: date
    trade_id: str
    selected_contract_symbol: str
    order_state: S23PaperOrderState | None = None
    position_state: S23PaperPositionState | None = None


@dataclass(frozen=True, slots=True)
class S23PaperLifecycleSupervisorStep:
    status: str
    reason_code: str
    fill_price: float | None = None
    entry_price: float | None = None
    exit_price: float | None = None


@dataclass(frozen=True, slots=True)
class S23PaperLifecycleSupervisorResult:
    context: S23PaperLifecycleSupervisorContext
    steps: tuple[S23PaperLifecycleSupervisorStep, ...]
    terminal: bool = False

    @property
    def final_step(self) -> S23PaperLifecycleSupervisorStep:
        return self.steps[-1]


class S23PaperLifecycleSupervisor:
    def __init__(
        self,
        *,
        order_store: S23PaperOrderStateStore | None = None,
        position_manager: S23PaperPositionManager | None = None,
    ) -> None:
        self._order_store = order_store or S23PaperOrderStateStore()
        self._position_manager = position_manager or S23PaperPositionManager()

    def expire_waiting_order_from_previous_session(
        self,
        context: S23PaperLifecycleSupervisorContext,
        *,
        evaluated_at: datetime,
    ) -> S23PaperLifecycleSupervisorResult | None:
        order_state = context.order_state
        if (
            context.position_state is not None
            or order_state is None
            or order_state.status is not S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER
            or order_state.entry_date >= context.session_date
        ):
            return None
        order_state, order_event, _state_path, _events_path = self._order_store.mark_not_filled(
            context.session_directory,
            marked_at=evaluated_at,
            reason_code="paper_order_expired_untriggered_previous_session",
            message=(
                "Pending S23 paper entry orders are session-only. This order did "
                "not trigger on its entry date, so it was cancelled instead of "
                "being carried forward."
            ),
        )
        return S23PaperLifecycleSupervisorResult(
            context=self._replace_order_context(context, order_state=order_state),
            steps=(self._step_from_order_event(order_event),),
            terminal=True,
        )

    def supervise(
        self,
        context: S23PaperLifecycleSupervisorContext,
        *,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
        evaluated_at: datetime,
        watch_cutoff_time: time,
        expiry_governance: S23PaperExpiryGovernance,
        allow_reverse_on_stoploss: bool = False,
        provenance_source_ids: tuple[str, ...] = (),
    ) -> S23PaperLifecycleSupervisorResult:
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
        context: S23PaperLifecycleSupervisorContext,
        *,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
        evaluated_at: datetime,
        watch_cutoff_time: time,
        expiry_governance: S23PaperExpiryGovernance,
        allow_reverse_on_stoploss: bool,
        provenance_source_ids: tuple[str, ...],
    ) -> S23PaperLifecycleSupervisorResult:
        order_state = context.order_state
        if order_state is None:
            raise RuntimeError("Waiting-order supervision requires an order_state.")

        order_state, order_event, _state_path, _events_path = self._order_store.evaluate_waiting_order(
            context.session_directory,
            market_events=market_events,
            evaluated_at=evaluated_at,
        )
        steps: list[S23PaperLifecycleSupervisorStep] = [self._step_from_order_event(order_event)]
        next_context = self._replace_order_context(context, order_state=order_state)

        if order_state.status is not S23PaperOrderStatus.PAPER_ORDER_FILLED:
            if evaluated_at.timetz().replace(tzinfo=None) >= watch_cutoff_time:
                order_state, order_event, _state_path, _events_path = self._order_store.mark_not_filled(
                    context.session_directory,
                    marked_at=evaluated_at,
                    reason_code="paper_order_not_triggered_by_watch_cutoff",
                    message=(
                        "Selected option premium did not reach entry before the "
                        "paper watch cutoff, so the pending S23 paper order was "
                        "not filled."
                    ),
                )
                steps.append(self._step_from_order_event(order_event))
                return S23PaperLifecycleSupervisorResult(
                    context=self._replace_order_context(context, order_state=order_state),
                    steps=tuple(steps),
                    terminal=True,
                )
            return S23PaperLifecycleSupervisorResult(
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
        position_context = S23PaperLifecycleSupervisorContext(
            session_directory=context.session_directory,
            session_date=context.session_date,
            trade_id=S23PaperTradeLedgerStore.trade_id_for_state(opened.state),
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
        return S23PaperLifecycleSupervisorResult(
            context=position_result.context,
            steps=tuple([*steps, *position_result.steps]),
            terminal=position_result.terminal,
        )

    def _supervise_open_position(
        self,
        context: S23PaperLifecycleSupervisorContext,
        *,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
        evaluated_at: datetime,
        expiry_governance: S23PaperExpiryGovernance,
        allow_reverse_on_stoploss: bool,
        provenance_source_ids: tuple[str, ...],
    ) -> S23PaperLifecycleSupervisorResult:
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
        next_context = S23PaperLifecycleSupervisorContext(
            session_directory=context.session_directory,
            session_date=context.session_date,
            trade_id=context.trade_id,
            selected_contract_symbol=result.state.selected_contract_symbol,
            position_state=result.state,
        )
        return S23PaperLifecycleSupervisorResult(
            context=next_context,
            steps=(self._step_from_position_manager_result(result),),
            terminal=result.status in TERMINAL_POSITION_MANAGER_STATUSES,
        )

    @staticmethod
    def _replace_order_context(
        context: S23PaperLifecycleSupervisorContext,
        *,
        order_state: S23PaperOrderState,
    ) -> S23PaperLifecycleSupervisorContext:
        return S23PaperLifecycleSupervisorContext(
            session_directory=context.session_directory,
            session_date=context.session_date,
            trade_id=context.trade_id,
            selected_contract_symbol=order_state.selected_contract_symbol,
            order_state=order_state,
        )

    @staticmethod
    def _step_from_order_event(event: S23PaperOrderEvent) -> S23PaperLifecycleSupervisorStep:
        return S23PaperLifecycleSupervisorStep(
            status=event.status.value,
            reason_code=event.reason_code,
            fill_price=event.fill_price,
        )

    @staticmethod
    def _step_from_position_manager_result(
        result: S23PaperPositionManagerResult,
        *,
        entry_price: float | None = None,
    ) -> S23PaperLifecycleSupervisorStep:
        return S23PaperLifecycleSupervisorStep(
            status=result.status.value,
            reason_code=result.event.reason_code,
            entry_price=entry_price,
            exit_price=result.event.exit_price,
        )
