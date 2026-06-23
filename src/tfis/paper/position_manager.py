from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any

from tfis.domain import OptionType, StrategyRule

from .expiry_governance import S23PaperExpiryGovernance
from .live_decision import S23PaperLiveDecisionResult, S23PaperTradeDecisionSummary
from .models import SelectedContractBarEvent, SelectedContractQuoteEvent
from .position_state import (
    S23PaperPositionState,
    S23PaperPositionStateStatus,
    S23PaperPositionStateStore,
)
from .trade_ledger import S23PaperTradeLedgerEventType, S23PaperTradeLedgerStore
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

    def process_session(
        self,
        session_directory: str | Path,
        *,
        session_date: date,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
        evaluated_at: datetime,
        expiry_governance: S23PaperExpiryGovernance | None = None,
        allow_reverse_on_stoploss: bool = True,
        provenance_source_ids: tuple[str, ...] = (),
    ) -> S23PaperPositionManagerResult:
        session_dir = Path(session_directory)
        state = self._state_store.load_state(session_dir)
        if state.lifecycle_status in {
            S23PaperPositionStateStatus.PAPER_POSITION_CLOSED,
            S23PaperPositionStateStatus.PAPER_REVERSE_ENTRY_REQUIRED,
            S23PaperPositionStateStatus.PAPER_FRESH_ENTRY_REQUIRED,
            S23PaperPositionStateStatus.PAPER_ROLLOVER_REQUIRED,
        }:
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

        if expiry_governance is not None:
            decision = expiry_governance.evaluate_position(
                state,
                session_date=session_date,
                current_time=evaluated_at.timetz().replace(tzinfo=None),
            )
            if decision.should_select_next_expiry:
                state = self._state_store.mark_rollover_required(
                    session_dir,
                    session_date=session_date,
                    marked_at=evaluated_at,
                    message=decision.message,
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
            if decision.must_force_close:
                event = self._build_force_close_event(
                    state=state,
                    session_date=session_date,
                    evaluated_at=evaluated_at,
                    market_events=market_events,
                    message=decision.message,
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

        exit_event = self._first_exit_event(
            state=state,
            session_date=session_date,
            market_events=market_events,
            evaluated_at=evaluated_at,
            allow_reverse_on_stoploss=allow_reverse_on_stoploss,
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
        event = S23PaperPositionManagerEvent(
            artifact_version=_ARTIFACT_VERSION,
            timestamp=evaluated_at,
            session_date=session_date,
            status=status,
            selected_contract_symbol=state.selected_contract_symbol,
            reason_code=reason_code,
            message=message,
            target_price=state.target_price,
            stop_price=self._effective_stop_price(state),
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
                )
            else:
                exit_event = self._evaluate_bar(
                    state=state,
                    session_date=session_date,
                    event=event,
                    allow_reverse_on_stoploss=allow_reverse_on_stoploss,
                )
            if exit_event is not None:
                return exit_event
        return None

    def _evaluate_quote(
        self,
        *,
        state: S23PaperPositionState,
        session_date: date,
        event: SelectedContractQuoteEvent,
        allow_reverse_on_stoploss: bool,
    ) -> S23PaperPositionManagerEvent | None:
        exit_reference = (
            float(event.ask)
            if event.ask is not None
            else (float(event.ltp) if event.ltp is not None else None)
        )
        if exit_reference is None:
            return None
        stop_price = self._effective_stop_price(state)
        if exit_reference >= stop_price:
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
    ) -> S23PaperPositionManagerEvent | None:
        if event.high is None or event.low is None:
            return None
        high = float(event.high)
        low = float(event.low)
        stop_price = self._effective_stop_price(state)
        stop_hit = high >= stop_price
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

    def _exit_event(
        self,
        *,
        session_date: date,
        event_timestamp: datetime,
        status: S23PaperPositionManagerStatus,
        selected_contract_symbol: str,
        reason_code: str,
        message: str,
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
        if status is S23PaperPositionManagerStatus.PAPER_POSITION_OPENED:
            return S23PaperTradeLedgerEventType.OPEN
        if status is S23PaperPositionManagerStatus.PAPER_POSITION_HELD:
            return S23PaperTradeLedgerEventType.HOLD
        if status in {
            S23PaperPositionManagerStatus.PAPER_POSITION_TARGET_HIT,
            S23PaperPositionManagerStatus.PAPER_POSITION_STOPLOSS_HIT,
            S23PaperPositionManagerStatus.PAPER_POSITION_FORCE_CLOSED,
            S23PaperPositionManagerStatus.PAPER_POSITION_FRESH_ENTRY_REQUIRED,
            S23PaperPositionManagerStatus.PAPER_POSITION_REVERSE_ENTRY_REQUIRED,
        }:
            return S23PaperTradeLedgerEventType.CLOSE
        return S23PaperTradeLedgerEventType.ACTION_REQUIRED

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


__all__ = [
    "S23PaperPositionManager",
    "S23PaperPositionManagerError",
    "S23PaperPositionManagerEvent",
    "S23PaperPositionManagerResult",
    "S23PaperPositionManagerStatus",
]
