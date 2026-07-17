from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any

from tfis.domain import ExpiryType, OptionType, RolloverPolicy, StrategyRule

from .expiry_governance import PaperExpiryGovernance
from .live_decision import S23PaperLiveDecisionResult, S23PaperTradeDecisionSummary
from .models import SelectedContractBarEvent, SelectedContractQuoteEvent
from .order_state import S23PaperOrderState, S23PaperOrderStatus
from .position_state import (
    S23PaperPositionState,
    S23PaperPositionStateStore,
    paper_position_is_no_longer_open,
)
from .trade_ledger import (
    S23PaperTradeLedgerEventType,
    S23PaperTradeLedgerStore,
    paper_trade_event_type_for_manager_status,
)
from .live_state_store import NullS23PaperLiveStateStore, S23PaperLiveStateStore


_ARTIFACT_VERSION = 1
_MANAGER_EVENTS_FILENAME = "paper_position_manager_events.jsonl"
_MANAGER_SUMMARY_FILENAME = "paper_position_manager_summary.json"


class S23PaperPositionManagerError(RuntimeError):
    """Raised when a multi-day S23 paper position cannot be managed safely."""


class S23PaperPositionManagerStatus(str, Enum):
    PAPER_POSITION_OPENED = "PAPER_POSITION_OPENED"
    PAPER_POSITION_HELD = "PAPER_POSITION_HELD"
    PAPER_POSITION_TARGET_HIT = "PAPER_POSITION_TARGET_HIT"
    PAPER_POSITION_STOPLOSS_HIT = "PAPER_POSITION_STOPLOSS_HIT"
    PAPER_POSITION_FORCE_CLOSED = "PAPER_POSITION_FORCE_CLOSED"
    PAPER_POSITION_ROLLOVER_REQUIRED = "PAPER_POSITION_ROLLOVER_REQUIRED"
    PAPER_POSITION_REVERSE_ENTRY_REQUIRED = "PAPER_POSITION_REVERSE_ENTRY_REQUIRED"
    PAPER_POSITION_FRESH_ENTRY_REQUIRED = "PAPER_POSITION_FRESH_ENTRY_REQUIRED"
    PAPER_POSITION_ALREADY_CLOSED = "PAPER_POSITION_ALREADY_CLOSED"
    PAPER_POSITION_NO_MARKET_DATA = "PAPER_POSITION_NO_MARKET_DATA"


@dataclass(frozen=True, slots=True)
class S23PaperPositionManagerEvent:
    artifact_version: int
    timestamp: datetime
    session_date: date
    status: S23PaperPositionManagerStatus
    selected_contract_symbol: str
    reason_code: str
    message: str
    current_price: float | None = None
    current_bid: float | None = None
    current_ask: float | None = None
    exit_price: float | None = None
    source_kind: str | None = None
    source_id: str | None = None
    source_effective_timestamp: datetime | None = None
    target_price: float | None = None
    stop_price: float | None = None
    reverse_entry_required: bool = False
    fresh_entry_required: bool = False
    rollover_required: bool = False


@dataclass(frozen=True, slots=True)
class S23PaperPositionManagerResult:
    artifact_version: int
    session_date: date
    status: S23PaperPositionManagerStatus
    state: S23PaperPositionState
    event: S23PaperPositionManagerEvent
    state_path: Path
    manager_events_path: Path
    manager_summary_path: Path


class S23PaperPositionManager:
    """Manages S23 paper positions across sessions from selected-contract prices.

    This class is deliberately adapter-agnostic. A live runner can feed it FYERS
    selected-contract quotes/bars, while unit tests and replay tools can feed the
    same normalized events from fixtures.
    """

    def __init__(
        self,
        *,
        state_store: S23PaperPositionStateStore | None = None,
        ledger_store: S23PaperTradeLedgerStore | None = None,
        live_state_store: S23PaperLiveStateStore | None = None,
        slippage_exit_points: float = 0.0,
    ) -> None:
        self._state_store = state_store or S23PaperPositionStateStore()
        self._ledger_store = ledger_store or S23PaperTradeLedgerStore()
        self._live_state_store = live_state_store or NullS23PaperLiveStateStore()
        self._slippage_exit_points = float(slippage_exit_points)

    def open_from_live_decision(
        self,
        session_directory: str | Path,
        *,
        strategy_rule: StrategyRule,
        decision: S23PaperLiveDecisionResult | S23PaperTradeDecisionSummary,
        opened_at: datetime,
        provenance_source_ids: tuple[str, ...] = (),
    ) -> S23PaperPositionManagerResult:
        summary = decision.summary if isinstance(decision, S23PaperLiveDecisionResult) else decision
        self._validate_ready_summary(summary)
        assert summary.selected_contract_symbol is not None
        assert summary.selected_contract_expiry is not None
        assert summary.selected_contract_option_type is not None
        assert summary.planned_entry_price is not None
        assert summary.target_price is not None
        assert summary.stoploss_price is not None

        try:
            option_type = OptionType(summary.selected_contract_option_type)
        except ValueError as exc:
            raise S23PaperPositionManagerError(
                f"Unsupported selected option type: {summary.selected_contract_option_type}"
            ) from exc

        state = self._state_store.create_open_position_state(
            strategy_code=summary.strategy_code,
            unique_code=summary.strategy_branch,
            symbol=strategy_rule.symbol,
            option_type=option_type,
            selected_contract_symbol=summary.selected_contract_symbol,
            expiry_date=date.fromisoformat(summary.selected_contract_expiry),
            expiry_type=strategy_rule.expiry_policy.expiry_type,
            rollover_policy=strategy_rule.expiry_policy.rollover_policy,
            forced_close_time=strategy_rule.expiry_policy.forced_close_time,
            no_carry_past_expiry=strategy_rule.expiry_policy.no_carry_past_expiry,
            entry_date=summary.session_date,
            entry_timestamp=opened_at,
            entry_price=summary.planned_entry_price,
            lots=summary.lots,
            quantity=summary.quantity,
            side="SELL",
            target_price=summary.target_price,
            stoploss_price=summary.stoploss_price,
            fsl_price=summary.fsl_price,
            trp_price=None,
            carry_forward_allowed=True,
            last_updated_timestamp=opened_at,
            provenance_source_ids=provenance_source_ids,
            strategy_parameters=strategy_rule.parameters,
            stoploss_reset_buffer_pct=(
                float(strategy_rule.parameters["sl_reference_pct"])
                if "sl_reference_pct" in strategy_rule.parameters
                else None
            ),
            stoploss_reset_orpt_time=strategy_rule.entry_time,
            stoploss_reset_rc_time=strategy_rule.recalculation_time,
        )
        session_dir = Path(session_directory)
        state_path = self._state_store.save_state(session_dir, state)
        event = S23PaperPositionManagerEvent(
            artifact_version=_ARTIFACT_VERSION,
            timestamp=opened_at,
            session_date=summary.session_date,
            status=S23PaperPositionManagerStatus.PAPER_POSITION_OPENED,
            selected_contract_symbol=state.selected_contract_symbol,
            reason_code="paper_position_opened_from_ready_decision",
            message="S23 READY decision was persisted as an open multi-day paper position.",
            target_price=state.target_price,
            stop_price=self._effective_stop_price(state),
        )
        return self._persist_result(
            session_dir,
            session_date=summary.session_date,
            status=event.status,
            state=state,
            event=event,
            state_path=state_path,
        )

    def open_from_filled_order(
        self,
        session_directory: str | Path,
        *,
        strategy_rule: StrategyRule | None = None,
        order_state: S23PaperOrderState,
        provenance_source_ids: tuple[str, ...] = (),
    ) -> S23PaperPositionManagerResult:
        if order_state.status is not S23PaperOrderStatus.PAPER_ORDER_FILLED:
            raise S23PaperPositionManagerError(
                "Cannot open paper position from an S23 paper order that is not filled."
            )
        if order_state.fill_price is None or order_state.fill_timestamp is None:
            raise S23PaperPositionManagerError(
                "Cannot open paper position from filled order without fill price and timestamp."
            )

        try:
            option_type = OptionType(order_state.selected_contract_option_type)
        except ValueError as exc:
            raise S23PaperPositionManagerError(
                f"Unsupported selected option type: {order_state.selected_contract_option_type}"
            ) from exc
        try:
            expiry_type = (
                strategy_rule.expiry_policy.expiry_type
                if strategy_rule is not None
                else ExpiryType(order_state.expiry_type)
            )
            rollover_policy = (
                strategy_rule.expiry_policy.rollover_policy
                if strategy_rule is not None
                else RolloverPolicy(order_state.rollover_policy)
            )
        except ValueError as exc:
            raise S23PaperPositionManagerError(
                "Unsupported expiry policy in filled paper order."
            ) from exc
        forced_close_time = (
            strategy_rule.expiry_policy.forced_close_time
            if strategy_rule is not None
            else order_state.forced_close_time
        )
        no_carry_past_expiry = (
            strategy_rule.expiry_policy.no_carry_past_expiry
            if strategy_rule is not None
            else order_state.no_carry_past_expiry
        )
        strategy_parameters = (
            strategy_rule.parameters
            if strategy_rule is not None
            else order_state.strategy_parameters
        )
        stoploss_reset_buffer_pct = (
            float(strategy_rule.parameters["sl_reference_pct"])
            if strategy_rule is not None and "sl_reference_pct" in strategy_rule.parameters
            else order_state.stoploss_reset_buffer_pct
        )
        stoploss_reset_orpt_time = (
            strategy_rule.entry_time
            if strategy_rule is not None
            else order_state.stoploss_reset_orpt_time
        )
        stoploss_reset_rc_time = (
            strategy_rule.recalculation_time
            if strategy_rule is not None
            else order_state.stoploss_reset_rc_time
        )

        state = self._state_store.create_open_position_state(
            strategy_code=order_state.strategy_code,
            unique_code=order_state.strategy_branch,
            symbol=strategy_rule.symbol if strategy_rule is not None else order_state.symbol,
            option_type=option_type,
            selected_contract_symbol=order_state.selected_contract_symbol,
            expiry_date=order_state.selected_contract_expiry,
            expiry_type=expiry_type,
            rollover_policy=rollover_policy,
            forced_close_time=forced_close_time,
            no_carry_past_expiry=no_carry_past_expiry,
            entry_date=order_state.entry_date,
            entry_timestamp=order_state.fill_timestamp,
            entry_price=order_state.fill_price,
            lots=order_state.lots,
            quantity=order_state.quantity,
            side=order_state.order_side,
            target_price=order_state.target_price,
            stoploss_price=order_state.stoploss_price,
            fsl_price=order_state.fsl_price,
            trp_price=None,
            carry_forward_allowed=True,
            last_updated_timestamp=order_state.fill_timestamp,
            provenance_source_ids=provenance_source_ids,
            strategy_parameters=strategy_parameters,
            stoploss_reset_buffer_pct=stoploss_reset_buffer_pct,
            stoploss_reset_orpt_time=stoploss_reset_orpt_time,
            stoploss_reset_rc_time=stoploss_reset_rc_time,
        )
        session_dir = Path(session_directory)
        state_path = self._state_store.save_state(session_dir, state)
        event = S23PaperPositionManagerEvent(
            artifact_version=_ARTIFACT_VERSION,
            timestamp=order_state.fill_timestamp,
            session_date=order_state.entry_date,
            status=S23PaperPositionManagerStatus.PAPER_POSITION_OPENED,
            selected_contract_symbol=state.selected_contract_symbol,
            reason_code="paper_position_opened_from_filled_order",
            message="S23 paper order filled; persisted as an open multi-day paper position.",
            source_kind=order_state.fill_source_kind,
            source_id=order_state.fill_source_id,
            source_effective_timestamp=order_state.fill_source_effective_timestamp,
            target_price=state.target_price,
            stop_price=self._effective_stop_price(state),
        )
        return self._persist_result(
            session_dir,
            session_date=order_state.entry_date,
            status=event.status,
            state=state,
            event=event,
            state_path=state_path,
        )

    def process_session(
        self,
        session_directory: str | Path,
        *,
        session_date: date,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
        evaluated_at: datetime,
        expiry_governance: PaperExpiryGovernance | None = None,
        allow_reverse_on_stoploss: bool = True,
        provenance_source_ids: tuple[str, ...] = (),
    ) -> S23PaperPositionManagerResult:
        session_dir = Path(session_directory)
        state = self._state_store.load_state(session_dir)
        if paper_position_is_no_longer_open(state.lifecycle_status):
            event = S23PaperPositionManagerEvent(
                artifact_version=_ARTIFACT_VERSION,
                timestamp=evaluated_at,
                session_date=session_date,
                status=S23PaperPositionManagerStatus.PAPER_POSITION_ALREADY_CLOSED,
                selected_contract_symbol=state.selected_contract_symbol,
                reason_code="position_not_open",
                message="Persisted S23 paper position is no longer open.",
            )
            return self._persist_result(
                session_dir,
                session_date=session_date,
                status=event.status,
                state=state,
                event=event,
                state_path=session_dir / "paper_position_state.json",
            )

        expiry_decision = None
        if expiry_governance is not None:
            expiry_decision = expiry_governance.evaluate_position(
                state,
                session_date=session_date,
                current_time=evaluated_at.timetz().replace(tzinfo=None),
            )
            if expiry_decision.should_select_next_expiry:
                state = self._state_store.mark_rollover_required(
                    session_dir,
                    session_date=session_date,
                    marked_at=evaluated_at,
                    message=expiry_decision.message,
                    provenance_source_ids=provenance_source_ids,
                )
                event = S23PaperPositionManagerEvent(
                    artifact_version=_ARTIFACT_VERSION,
                    timestamp=evaluated_at,
                    session_date=session_date,
                    status=S23PaperPositionManagerStatus.PAPER_POSITION_ROLLOVER_REQUIRED,
                    selected_contract_symbol=state.selected_contract_symbol,
                    reason_code="rollover_required_before_session_processing",
                    message=(
                        "Current contract entered the rollover window. Close/reselect "
                        "using the next weekly expiry before continuing paper exposure."
                    ),
                    rollover_required=True,
                )
                return self._persist_result(
                    session_dir,
                    session_date=session_date,
                    status=event.status,
                    state=state,
                    event=event,
                    state_path=session_dir / "paper_position_state.json",
                )

        if self._pending_next_day_stoploss_reset(state, session_date):
            target_event = self._first_exit_event(
                state=state,
                session_date=session_date,
                market_events=market_events,
                evaluated_at=evaluated_at,
                allow_reverse_on_stoploss=allow_reverse_on_stoploss,
                stoploss_enabled=False,
            )
            if target_event is not None:
                state = self._state_store.mark_position_closed(
                    session_dir,
                    session_date=session_date,
                    closed_at=target_event.timestamp,
                    reason_code=target_event.reason_code,
                    message=target_event.message,
                    reverse_entry_required=target_event.reverse_entry_required,
                    fresh_entry_required=target_event.fresh_entry_required,
                    provenance_source_ids=provenance_source_ids,
                )
                return self._persist_result(
                    session_dir,
                    session_date=session_date,
                    status=target_event.status,
                    state=state,
                    event=target_event,
                    state_path=session_dir / "paper_position_state.json",
                )
            reset_event, state = self._evaluate_next_day_stoploss_reset(
                session_directory=session_dir,
                state=state,
                session_date=session_date,
                market_events=market_events,
                evaluated_at=evaluated_at,
                provenance_source_ids=provenance_source_ids,
            )
            if reset_event is not None and not state.stoploss_active:
                return self._persist_result(
                    session_dir,
                    session_date=session_date,
                    status=reset_event.status,
                    state=state,
                    event=reset_event,
                    state_path=session_dir / "paper_position_state.json",
                )

        exit_event = self._first_exit_event(
            state=state,
            session_date=session_date,
            market_events=market_events,
            evaluated_at=evaluated_at,
            allow_reverse_on_stoploss=allow_reverse_on_stoploss,
            stoploss_enabled=state.stoploss_active,
        )
        if exit_event is not None:
            state = self._state_store.mark_position_closed(
                session_dir,
                session_date=session_date,
                closed_at=exit_event.timestamp,
                reason_code=exit_event.reason_code,
                message=exit_event.message,
                reverse_entry_required=exit_event.reverse_entry_required,
                fresh_entry_required=exit_event.fresh_entry_required,
                provenance_source_ids=provenance_source_ids,
            )
            return self._persist_result(
                session_dir,
                session_date=session_date,
                status=exit_event.status,
                state=state,
                event=exit_event,
                state_path=session_dir / "paper_position_state.json",
            )

        if expiry_decision is not None and expiry_decision.must_force_close:
            event = self._build_force_close_event(
                state=state,
                session_date=session_date,
                evaluated_at=evaluated_at,
                market_events=market_events,
                message=expiry_decision.message,
            )
            state = self._state_store.mark_position_closed(
                session_dir,
                session_date=session_date,
                closed_at=event.timestamp,
                reason_code=event.reason_code,
                message=event.message,
                provenance_source_ids=provenance_source_ids,
            )
            return self._persist_result(
                session_dir,
                session_date=session_date,
                status=event.status,
                state=state,
                event=event,
                state_path=session_dir / "paper_position_state.json",
            )

        continuation_event = self._evaluate_1500_continuation_rule(
            state=state,
            session_date=session_date,
            evaluated_at=evaluated_at,
            market_events=market_events,
        )
        if continuation_event is not None and continuation_event.exit_price is not None:
            state = self._state_store.mark_position_closed(
                session_dir,
                session_date=session_date,
                closed_at=continuation_event.timestamp,
                reason_code=continuation_event.reason_code,
                message=continuation_event.message,
                provenance_source_ids=provenance_source_ids,
            )
            return self._persist_result(
                session_dir,
                session_date=session_date,
                status=continuation_event.status,
                state=state,
                event=continuation_event,
                state_path=session_dir / "paper_position_state.json",
            )
        if continuation_event is not None:
            state = self._state_store.mark_stoploss_inactive_for_carry_forward(
                session_dir,
                session_date=session_date,
                updated_at=continuation_event.timestamp,
                reference_price=state.stoploss_price,
                reason_code=continuation_event.reason_code,
                message=continuation_event.message,
                provenance_source_ids=provenance_source_ids,
            )
            return self._persist_result(
                session_dir,
                session_date=session_date,
                status=continuation_event.status,
                state=state,
                event=continuation_event,
                state_path=session_dir / "paper_position_state.json",
            )

        if not market_events:
            status = S23PaperPositionManagerStatus.PAPER_POSITION_NO_MARKET_DATA
            reason_code = "missing_selected_contract_market_data"
            message = (
                "No selected-contract market events were available; the open paper "
                "position remains unchanged and must be resumed with fresh data."
            )
        else:
            status = S23PaperPositionManagerStatus.PAPER_POSITION_HELD
            reason_code = "no_exit_threshold_hit"
            message = (
                "No target, stoploss, FSL, expiry, or rollover condition was hit; "
                "the paper position remains open for the next session."
            )
        current_price, current_bid, current_ask, current_kind, current_id, current_timestamp = (
            self._latest_market_reference(state, market_events)
        )
        event = S23PaperPositionManagerEvent(
            artifact_version=_ARTIFACT_VERSION,
            timestamp=evaluated_at,
            session_date=session_date,
            status=status,
            selected_contract_symbol=state.selected_contract_symbol,
            reason_code=reason_code,
            message=message,
            current_price=current_price,
            current_bid=current_bid,
            current_ask=current_ask,
            source_kind=current_kind,
            source_id=current_id,
            source_effective_timestamp=current_timestamp,
            target_price=state.target_price,
            stop_price=self._effective_stop_price(state) if state.stoploss_active else None,
        )
        return self._persist_result(
            session_dir,
            session_date=session_date,
            status=status,
            state=state,
            event=event,
            state_path=session_dir / "paper_position_state.json",
        )

    def _first_exit_event(
        self,
        *,
        state: S23PaperPositionState,
        session_date: date,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
        evaluated_at: datetime,
        allow_reverse_on_stoploss: bool,
        stoploss_enabled: bool = True,
    ) -> S23PaperPositionManagerEvent | None:
        for event in self._sorted_market_events(market_events):
            if event.symbol != state.selected_contract_symbol:
                continue
            if isinstance(event, SelectedContractQuoteEvent):
                exit_event = self._evaluate_quote(
                    state=state,
                    session_date=session_date,
                    event=event,
                    allow_reverse_on_stoploss=allow_reverse_on_stoploss,
                    stoploss_enabled=stoploss_enabled,
                )
            else:
                exit_event = self._evaluate_bar(
                    state=state,
                    session_date=session_date,
                    event=event,
                    allow_reverse_on_stoploss=allow_reverse_on_stoploss,
                    stoploss_enabled=stoploss_enabled,
                )
            if exit_event is not None:
                return exit_event
        return None

    def _pending_next_day_stoploss_reset(
        self,
        state: S23PaperPositionState,
        session_date: date,
    ) -> bool:
        return (
            state.stoploss_reset_pending
            and not state.stoploss_active
            and session_date > (state.stoploss_reset_session_date or state.entry_date)
        )

    def _evaluate_next_day_stoploss_reset(
        self,
        *,
        session_directory: Path,
        state: S23PaperPositionState,
        session_date: date,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
        evaluated_at: datetime,
        provenance_source_ids: tuple[str, ...],
    ) -> tuple[S23PaperPositionManagerEvent | None, S23PaperPositionState]:
        orpt_time = state.stoploss_reset_orpt_time or time(9, 24, 59)
        rc_time = state.stoploss_reset_rc_time or time(9, 29, 59)
        current_time = evaluated_at.timetz().replace(tzinfo=None)
        current_price, current_bid, current_ask, source_kind, source_id, source_timestamp = (
            self._latest_market_reference(state, market_events)
        )
        original_stop = float(state.stoploss_price)
        if current_time < orpt_time:
            return (
                self._held_event(
                    state=state,
                    session_date=session_date,
                    evaluated_at=evaluated_at,
                    reason_code="carry_forward_stoploss_waiting_for_orpt",
                    message=(
                        "Carried S23 position has target active, but stoploss remains "
                        "inactive until ORPT before the next-day SL reset check."
                    ),
                    current_price=current_price,
                    current_bid=current_bid,
                    current_ask=current_ask,
                    source_kind=source_kind,
                    source_id=source_id,
                    source_timestamp=source_timestamp,
                    stop_price=None,
                ),
                state,
            )

        open_high = self._bar_high_for_minute(
            state=state,
            market_events=market_events,
            target_time=time(9, 15),
        )
        if open_high is None:
            return (
                self._held_event(
                    state=state,
                    session_date=session_date,
                    evaluated_at=evaluated_at,
                    reason_code="carry_forward_stoploss_waiting_for_0915_high",
                    message=(
                        "Carried S23 position needs the 09:15 selected-option high "
                        "to decide whether the original SL was missed. Stoploss "
                        "remains inactive; target remains active."
                    ),
                    current_price=current_price,
                    current_bid=current_bid,
                    current_ask=current_ask,
                    source_kind=source_kind,
                    source_id=source_id,
                    source_timestamp=source_timestamp,
                    stop_price=None,
                ),
                state,
            )

        if open_high <= original_stop:
            updated = self._state_store.activate_stoploss_after_reset(
                session_directory,
                session_date=session_date,
                updated_at=evaluated_at,
                stoploss_price=original_stop,
                fsl_price=None,
                reason_code="carry_forward_stoploss_not_missed_orpt_activated",
                message=(
                    f"09:15 high {open_high:.2f} did not exceed original SL "
                    f"{original_stop:.2f}; stoploss is active again from ORPT."
                ),
                provenance_source_ids=provenance_source_ids,
            )
            return None, updated

        if current_time < rc_time:
            return (
                self._held_event(
                    state=state,
                    session_date=session_date,
                    evaluated_at=evaluated_at,
                    reason_code="carry_forward_stoploss_missed_waiting_for_rc",
                    message=(
                        f"09:15 high {open_high:.2f} exceeded original SL "
                        f"{original_stop:.2f}. TFIS is waiting until RC to set "
                        "the revised SL from the RC high plus the configured buffer."
                    ),
                    current_price=current_price,
                    current_bid=current_bid,
                    current_ask=current_ask,
                    source_kind=source_kind,
                    source_id=source_id,
                    source_timestamp=source_timestamp,
                    stop_price=None,
                ),
                state,
            )

        rc_high = self._bar_high_for_minute(
            state=state,
            market_events=market_events,
            target_time=rc_time,
        )
        if rc_high is None:
            return (
                self._held_event(
                    state=state,
                    session_date=session_date,
                    evaluated_at=evaluated_at,
                    reason_code="carry_forward_stoploss_waiting_for_rc_high",
                    message=(
                        "09:15 high exceeded the original SL, but the RC selected-option "
                        "high is not available yet. Stoploss remains inactive; target "
                        "remains active."
                    ),
                    current_price=current_price,
                    current_bid=current_bid,
                    current_ask=current_ask,
                    source_kind=source_kind,
                    source_id=source_id,
                    source_timestamp=source_timestamp,
                    stop_price=None,
                ),
                state,
            )

        buffer_pct = float(
            state.stoploss_reset_buffer_pct
            if state.stoploss_reset_buffer_pct is not None
            else (state.strategy_parameters or {}).get("sl_reference_pct", 0.0)
        )
        revised_stop = rc_high * (1.0 + buffer_pct / 100.0)
        updated = self._state_store.activate_stoploss_after_reset(
            session_directory,
            session_date=session_date,
            updated_at=evaluated_at,
            stoploss_price=revised_stop,
            fsl_price=None,
            reason_code="carry_forward_stoploss_recalculated_from_rc_high",
            message=(
                f"09:15 high {open_high:.2f} exceeded original SL {original_stop:.2f}; "
                f"revised SL = RC high {rc_high:.2f} + {buffer_pct:.2f}% = "
                f"{revised_stop:.2f}."
            ),
            provenance_source_ids=provenance_source_ids,
        )
        return None, updated

    def _held_event(
        self,
        *,
        state: S23PaperPositionState,
        session_date: date,
        evaluated_at: datetime,
        reason_code: str,
        message: str,
        current_price: float | None,
        current_bid: float | None,
        current_ask: float | None,
        source_kind: str | None,
        source_id: str | None,
        source_timestamp: datetime | None,
        stop_price: float | None,
    ) -> S23PaperPositionManagerEvent:
        return S23PaperPositionManagerEvent(
            artifact_version=_ARTIFACT_VERSION,
            timestamp=source_timestamp or evaluated_at,
            session_date=session_date,
            status=S23PaperPositionManagerStatus.PAPER_POSITION_HELD,
            selected_contract_symbol=state.selected_contract_symbol,
            reason_code=reason_code,
            message=message,
            current_price=current_price,
            current_bid=current_bid,
            current_ask=current_ask,
            source_kind=source_kind,
            source_id=source_id,
            source_effective_timestamp=source_timestamp,
            target_price=state.target_price,
            stop_price=stop_price,
        )

    def _bar_high_for_minute(
        self,
        *,
        state: S23PaperPositionState,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
        target_time: time,
    ) -> float | None:
        target_hour = target_time.hour
        target_minute = target_time.minute
        highs: list[float] = []
        for event in self._sorted_market_events(market_events):
            if not isinstance(event, SelectedContractBarEvent):
                continue
            if event.symbol != state.selected_contract_symbol or event.high is None:
                continue
            if (
                (event.bar_start.hour, event.bar_start.minute) == (target_hour, target_minute)
                or (event.bar_end.hour, event.bar_end.minute) == (target_hour, target_minute)
            ):
                highs.append(float(event.high))
        return max(highs) if highs else None

    def _evaluate_1500_continuation_rule(
        self,
        *,
        state: S23PaperPositionState,
        session_date: date,
        evaluated_at: datetime,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
    ) -> S23PaperPositionManagerEvent | None:
        if evaluated_at.timetz().replace(tzinfo=None) < time(15, 0):
            return None
        current_price, current_bid, current_ask, source_kind, source_id, source_timestamp = (
            self._latest_market_reference(state, market_events)
        )
        if current_price is None:
            return None
        timestamp = source_timestamp or evaluated_at
        original_stoploss = float(state.stoploss_price)
        if float(current_price) > original_stoploss:
            exit_price = float(current_price) + self._slippage_exit_points
            return self._exit_event(
                session_date=session_date,
                event_timestamp=timestamp,
                status=S23PaperPositionManagerStatus.PAPER_POSITION_FORCE_CLOSED,
                selected_contract_symbol=state.selected_contract_symbol,
                reason_code="s23_1500_close_above_original_sl",
                message=(
                    "At or after 15:00, selected option price was above the original "
                    "S23 stoploss, so the paper position was squared off at CMP."
                ),
                current_price=float(current_price),
                current_bid=current_bid,
                current_ask=current_ask,
                exit_price=exit_price,
                source_kind=source_kind or "selected_contract_market_data",
                source_id=source_id or "unknown",
                source_effective_timestamp=timestamp,
                target_price=state.target_price,
                stop_price=original_stoploss,
            )
        return S23PaperPositionManagerEvent(
            artifact_version=_ARTIFACT_VERSION,
            timestamp=timestamp,
            session_date=session_date,
            status=S23PaperPositionManagerStatus.PAPER_POSITION_HELD,
            selected_contract_symbol=state.selected_contract_symbol,
            reason_code="s23_1500_carry_forward_stop_inactive",
            message=(
                "At or after 15:00, selected option price was not above the original "
                "S23 stoploss. Position is carried forward; overnight stoploss is "
                "inactive and must be recalculated on the next trading day."
            ),
            current_price=float(current_price),
            current_bid=current_bid,
            current_ask=current_ask,
            source_kind=source_kind,
            source_id=source_id,
            source_effective_timestamp=timestamp,
            target_price=state.target_price,
            stop_price=original_stoploss,
        )

    def _evaluate_quote(
        self,
        *,
        state: S23PaperPositionState,
        session_date: date,
        event: SelectedContractQuoteEvent,
        allow_reverse_on_stoploss: bool,
        stoploss_enabled: bool = True,
    ) -> S23PaperPositionManagerEvent | None:
        exit_reference = (
            float(event.ask)
            if event.ask is not None
            else (float(event.ltp) if event.ltp is not None else None)
        )
        if exit_reference is None:
            return None
        stop_price = self._effective_stop_price(state)
        if stoploss_enabled and exit_reference >= stop_price:
            exit_price = max(stop_price, exit_reference) + self._slippage_exit_points
            return self._exit_event(
                session_date=session_date,
                event_timestamp=event.envelope.effective_timestamp,
                status=(
                    S23PaperPositionManagerStatus.PAPER_POSITION_REVERSE_ENTRY_REQUIRED
                    if allow_reverse_on_stoploss
                    else S23PaperPositionManagerStatus.PAPER_POSITION_STOPLOSS_HIT
                ),
                selected_contract_symbol=state.selected_contract_symbol,
                reason_code="stoploss_or_fsl_hit",
                message=(
                    "Selected-contract quote breached stoploss/FSL. The paper "
                    "position was closed; reverse entry requires a fresh opposite "
                    "S23 decision."
                ),
                current_price=float(event.ltp) if event.ltp is not None else None,
                current_bid=float(event.bid) if event.bid is not None else None,
                current_ask=float(event.ask) if event.ask is not None else None,
                exit_price=exit_price,
                source_kind="selected_contract_quote",
                source_id=event.envelope.source_id,
                source_effective_timestamp=event.envelope.effective_timestamp,
                target_price=state.target_price,
                stop_price=stop_price,
                reverse_entry_required=allow_reverse_on_stoploss,
            )
        if exit_reference <= state.target_price:
            exit_price = max(state.target_price, exit_reference) + self._slippage_exit_points
            return self._exit_event(
                session_date=session_date,
                event_timestamp=event.envelope.effective_timestamp,
                status=S23PaperPositionManagerStatus.PAPER_POSITION_FRESH_ENTRY_REQUIRED,
                selected_contract_symbol=state.selected_contract_symbol,
                reason_code="target_hit",
                message=(
                    "Selected-contract quote proved target hit. The paper position "
                    "was closed; a fresh S23 position must be recalculated from "
                    "current market data before any new entry."
                ),
                current_price=float(event.ltp) if event.ltp is not None else None,
                current_bid=float(event.bid) if event.bid is not None else None,
                current_ask=float(event.ask) if event.ask is not None else None,
                exit_price=exit_price,
                source_kind="selected_contract_quote",
                source_id=event.envelope.source_id,
                source_effective_timestamp=event.envelope.effective_timestamp,
                target_price=state.target_price,
                stop_price=stop_price,
                fresh_entry_required=True,
            )
        return None

    def _evaluate_bar(
        self,
        *,
        state: S23PaperPositionState,
        session_date: date,
        event: SelectedContractBarEvent,
        allow_reverse_on_stoploss: bool,
        stoploss_enabled: bool = True,
    ) -> S23PaperPositionManagerEvent | None:
        if event.high is None or event.low is None:
            return None
        high = float(event.high)
        low = float(event.low)
        stop_price = self._effective_stop_price(state)
        stop_hit = stoploss_enabled and high >= stop_price
        target_hit = low <= state.target_price
        if stop_hit:
            reason = (
                "same_bar_target_stop_conflict_stoploss_wins"
                if target_hit
                else "stoploss_or_fsl_hit"
            )
            return self._exit_event(
                session_date=session_date,
                event_timestamp=event.bar_end,
                status=(
                    S23PaperPositionManagerStatus.PAPER_POSITION_REVERSE_ENTRY_REQUIRED
                    if allow_reverse_on_stoploss
                    else S23PaperPositionManagerStatus.PAPER_POSITION_STOPLOSS_HIT
                ),
                selected_contract_symbol=state.selected_contract_symbol,
                reason_code=reason,
                message=(
                    "Selected-contract bar breached stoploss/FSL. If target was "
                    "also possible in the same bar, stoploss wins conservatively. "
                    "Reverse entry requires a fresh opposite S23 decision."
                ),
                current_price=float(event.close) if event.close is not None else None,
                exit_price=stop_price + self._slippage_exit_points,
                source_kind="selected_contract_bar",
                source_id=event.envelope.source_id,
                source_effective_timestamp=event.envelope.effective_timestamp,
                target_price=state.target_price,
                stop_price=stop_price,
                reverse_entry_required=allow_reverse_on_stoploss,
            )
        if target_hit:
            return self._exit_event(
                session_date=session_date,
                event_timestamp=event.bar_end,
                status=S23PaperPositionManagerStatus.PAPER_POSITION_FRESH_ENTRY_REQUIRED,
                selected_contract_symbol=state.selected_contract_symbol,
                reason_code="target_hit",
                message=(
                    "Selected-contract bar proved target hit. The paper position "
                    "was closed; a fresh S23 position must be recalculated from "
                    "current market data before any new entry."
                ),
                current_price=float(event.close) if event.close is not None else None,
                exit_price=state.target_price + self._slippage_exit_points,
                source_kind="selected_contract_bar",
                source_id=event.envelope.source_id,
                source_effective_timestamp=event.envelope.effective_timestamp,
                target_price=state.target_price,
                stop_price=stop_price,
                fresh_entry_required=True,
            )
        return None

    def _build_force_close_event(
        self,
        *,
        state: S23PaperPositionState,
        session_date: date,
        evaluated_at: datetime,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
        message: str,
    ) -> S23PaperPositionManagerEvent:
        price, source_kind, source_id, source_timestamp = self._latest_exit_price(
            state,
            market_events,
        )
        return S23PaperPositionManagerEvent(
            artifact_version=_ARTIFACT_VERSION,
            timestamp=source_timestamp or evaluated_at,
            session_date=session_date,
            status=S23PaperPositionManagerStatus.PAPER_POSITION_FORCE_CLOSED,
            selected_contract_symbol=state.selected_contract_symbol,
            reason_code="expiry_force_close",
            message=message,
            current_price=price,
            exit_price=price,
            source_kind=source_kind,
            source_id=source_id,
            source_effective_timestamp=source_timestamp,
            target_price=state.target_price,
            stop_price=self._effective_stop_price(state),
        )

    def _latest_exit_price(
        self,
        state: S23PaperPositionState,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
    ) -> tuple[float | None, str | None, str | None, datetime | None]:
        for event in reversed(self._sorted_market_events(market_events)):
            if event.symbol != state.selected_contract_symbol:
                continue
            if isinstance(event, SelectedContractQuoteEvent):
                price = event.ask if event.ask is not None else event.ltp
                if price is not None:
                    return (
                        float(price) + self._slippage_exit_points,
                        "selected_contract_quote",
                        event.envelope.source_id,
                        event.envelope.effective_timestamp,
                    )
            elif event.close is not None:
                return (
                    float(event.close) + self._slippage_exit_points,
                    "selected_contract_bar",
                    event.envelope.source_id,
                    event.envelope.effective_timestamp,
                )
        return None, None, None, None

    def _latest_market_reference(
        self,
        state: S23PaperPositionState,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
    ) -> tuple[float | None, float | None, float | None, str | None, str | None, datetime | None]:
        for event in reversed(self._sorted_market_events(market_events)):
            if event.symbol != state.selected_contract_symbol:
                continue
            if isinstance(event, SelectedContractQuoteEvent):
                price = event.ltp
                if price is None:
                    price = event.bid if event.bid is not None else event.ask
                return (
                    float(price) if price is not None else None,
                    float(event.bid) if event.bid is not None else None,
                    float(event.ask) if event.ask is not None else None,
                    "selected_contract_quote",
                    event.envelope.source_id,
                    event.envelope.effective_timestamp,
                )
            return (
                float(event.close) if event.close is not None else None,
                None,
                None,
                "selected_contract_bar",
                event.envelope.source_id,
                event.envelope.effective_timestamp,
            )
        return None, None, None, None, None, None

    def _exit_event(
        self,
        *,
        session_date: date,
        event_timestamp: datetime,
        status: S23PaperPositionManagerStatus,
        selected_contract_symbol: str,
        reason_code: str,
        message: str,
        current_price: float | None = None,
        current_bid: float | None = None,
        current_ask: float | None = None,
        exit_price: float,
        source_kind: str,
        source_id: str,
        source_effective_timestamp: datetime,
        target_price: float,
        stop_price: float,
        reverse_entry_required: bool = False,
        fresh_entry_required: bool = False,
    ) -> S23PaperPositionManagerEvent:
        return S23PaperPositionManagerEvent(
            artifact_version=_ARTIFACT_VERSION,
            timestamp=event_timestamp,
            session_date=session_date,
            status=status,
            selected_contract_symbol=selected_contract_symbol,
            reason_code=reason_code,
            message=message,
            current_price=current_price,
            current_bid=current_bid,
            current_ask=current_ask,
            exit_price=exit_price,
            source_kind=source_kind,
            source_id=source_id,
            source_effective_timestamp=source_effective_timestamp,
            target_price=target_price,
            stop_price=stop_price,
            reverse_entry_required=reverse_entry_required,
            fresh_entry_required=fresh_entry_required,
        )

    @staticmethod
    def _effective_stop_price(state: S23PaperPositionState) -> float:
        candidates = [state.stoploss_price]
        if state.fsl_price is not None:
            candidates.append(state.fsl_price)
        return min(candidates)

    @staticmethod
    def _sorted_market_events(
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
    ) -> tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...]:
        return tuple(
            sorted(
                market_events,
                key=lambda event: (
                    event.envelope.effective_timestamp,
                    event.envelope.captured_at,
                ),
            )
        )

    @staticmethod
    def _validate_ready_summary(summary: S23PaperTradeDecisionSummary) -> None:
        if summary.status != "READY":
            raise S23PaperPositionManagerError(
                f"Cannot open paper position from decision status {summary.status!r}."
            )
        missing = [
            name
            for name in (
                "selected_contract_symbol",
                "selected_contract_expiry",
                "selected_contract_option_type",
                "planned_entry_price",
                "target_price",
                "stoploss_price",
            )
            if getattr(summary, name) is None
        ]
        if missing:
            raise S23PaperPositionManagerError(
                "Cannot open paper position; decision summary is missing "
                + ", ".join(missing)
            )

    def _persist_result(
        self,
        session_directory: Path,
        *,
        session_date: date,
        status: S23PaperPositionManagerStatus,
        state: S23PaperPositionState,
        event: S23PaperPositionManagerEvent,
        state_path: Path,
    ) -> S23PaperPositionManagerResult:
        events_path = session_directory / _MANAGER_EVENTS_FILENAME
        summary_path = session_directory / _MANAGER_SUMMARY_FILENAME
        self._append_jsonl(events_path, event)
        result = S23PaperPositionManagerResult(
            artifact_version=_ARTIFACT_VERSION,
            session_date=session_date,
            status=status,
            state=state,
            event=event,
            state_path=state_path,
            manager_events_path=events_path,
            manager_summary_path=summary_path,
        )
        self._write_json(summary_path, result)
        ledger_row = self._ledger_store.build_row(
            state=state,
            event_timestamp=event.timestamp,
            event_type=self._ledger_event_type(status),
            session_date=session_date,
            manager_status=status.value,
            reason_code=event.reason_code,
            message=event.message,
            exit_timestamp=(
                event.timestamp
                if event.exit_price is not None
                else None
            ),
            current_price=event.current_price,
            current_bid=event.current_bid,
            current_ask=event.current_ask,
            exit_price=event.exit_price,
            source_kind=event.source_kind,
            source_id=event.source_id,
            source_effective_timestamp=event.source_effective_timestamp,
            fresh_entry_required=event.fresh_entry_required,
            reverse_entry_required=event.reverse_entry_required,
            rollover_required=event.rollover_required,
            state_directory=session_directory,
        )
        self._ledger_store.append(session_directory, ledger_row)
        trade_id = self._ledger_store.trade_id_for_state(state)
        live_payload = {
            "artifact_version": _ARTIFACT_VERSION,
            "trade_id": trade_id,
            "state": self._normalize(state),
            "manager_event": self._normalize(event),
            "ledger_row": self._normalize(ledger_row),
            "state_path": str(state_path),
            "manager_events_path": str(events_path),
            "manager_summary_path": str(summary_path),
            "state_directory": str(session_directory),
        }
        self._live_state_store.mirror_position_state(
            session_date=session_date,
            trade_id=trade_id,
            payload=live_payload,
        )
        self._live_state_store.mirror_trade_event(
            session_date=session_date,
            trade_id=trade_id,
            payload=live_payload,
        )
        return result

    @staticmethod
    def _ledger_event_type(
        status: S23PaperPositionManagerStatus,
    ) -> S23PaperTradeLedgerEventType:
        return paper_trade_event_type_for_manager_status(status.value)

    def _append_jsonl(self, path: Path, event: S23PaperPositionManagerEvent) -> None:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        rendered = existing + json.dumps(self._normalize(event), sort_keys=True) + "\n"
        self._atomic_write_text(path, rendered)

    def _write_json(self, path: Path, payload: Any) -> None:
        self._atomic_write_text(
            path,
            json.dumps(self._normalize(payload), indent=2, sort_keys=True) + "\n",
        )

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.parent / f".{path.name}.tmp"
        try:
            temp_path.write_text(content, encoding="utf-8", newline="\n")
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _normalize(self, value: Any) -> Any:
        if is_dataclass(value):
            return {
                field.name: self._normalize(getattr(value, field.name))
                for field in fields(value)
            }
        if isinstance(value, dict):
            return {
                str(key): self._normalize(val)
                for key, val in sorted(value.items(), key=lambda item: str(item[0]))
            }
        if isinstance(value, tuple | list):
            return [self._normalize(item) for item in value]
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, time):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, S23PaperPositionState):
            return asdict(value)
        return value


def build_paper_position_manager(
    *,
    strategy_code: str,
    live_state_store: S23PaperLiveStateStore | None = None,
    slippage_exit_points: float = 0.0,
) -> S23PaperPositionManager:
    normalized_strategy_code = strategy_code.strip().upper()
    if normalized_strategy_code in {"S21", "S23"}:
        return S23PaperPositionManager(
            live_state_store=live_state_store,
            slippage_exit_points=slippage_exit_points,
        )
    raise S23PaperPositionManagerError(
        f"Unsupported paper position manager strategy code: {strategy_code}"
    )


PaperPositionManager = S23PaperPositionManager
PaperPositionManagerError = S23PaperPositionManagerError
PaperPositionManagerEvent = S23PaperPositionManagerEvent
PaperPositionManagerResult = S23PaperPositionManagerResult
PaperPositionManagerStatus = S23PaperPositionManagerStatus


__all__ = [
    "build_paper_position_manager",
    "PaperPositionManager",
    "PaperPositionManagerError",
    "PaperPositionManagerEvent",
    "PaperPositionManagerResult",
    "PaperPositionManagerStatus",
    "S23PaperPositionManager",
    "S23PaperPositionManagerError",
    "S23PaperPositionManagerEvent",
    "S23PaperPositionManagerResult",
    "S23PaperPositionManagerStatus",
]
