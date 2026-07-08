from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any

from tfis.domain import ExpiryType, RolloverPolicy
from tfis.domain import StrategyRule

from .live_decision import S23PaperLiveDecisionResult, S23PaperTradeDecisionSummary
from .models import SelectedContractBarEvent, SelectedContractQuoteEvent


_ARTIFACT_VERSION = 1
_STATE_FILENAME = "paper_order_state.json"
_EVENTS_FILENAME = "paper_order_events.jsonl"


class S23PaperOrderStateError(RuntimeError):
    """Raised when an S23 paper order cannot be persisted or evaluated safely."""


class S23PaperOrderStatus(str, Enum):
    PAPER_ORDER_WAITING_FOR_TRIGGER = "PAPER_ORDER_WAITING_FOR_TRIGGER"
    PAPER_ORDER_FILLED = "PAPER_ORDER_FILLED"
    PAPER_ORDER_NOT_FILLED = "PAPER_ORDER_NOT_FILLED"


@dataclass(frozen=True, slots=True)
class S23PaperOrderState:
    artifact_version: int
    strategy_code: str
    strategy_branch: str
    symbol: str
    selected_contract_symbol: str
    selected_contract_expiry: date
    selected_contract_option_type: str
    selected_contract_strike: float | None
    expiry_type: str
    rollover_policy: str
    forced_close_time: time | None
    no_carry_past_expiry: bool
    order_side: str
    trigger_rule: str
    entry_date: date
    order_timestamp: datetime
    planned_entry_price: float
    target_price: float
    stoploss_price: float
    fsl_price: float | None
    lots: int
    quantity: int
    status: S23PaperOrderStatus
    last_updated_timestamp: datetime
    fill_price: float | None = None
    fill_timestamp: datetime | None = None
    fill_source_kind: str | None = None
    fill_source_id: str | None = None
    fill_source_effective_timestamp: datetime | None = None
    last_market_price: float | None = None
    last_market_bid: float | None = None
    last_market_ask: float | None = None
    last_market_low: float | None = None
    last_market_high: float | None = None
    last_reason_code: str | None = None
    last_message: str | None = None
    provenance_source_ids: tuple[str, ...] = ()
    strategy_parameters: dict[str, float] | None = None
    stoploss_reset_buffer_pct: float | None = None
    stoploss_reset_orpt_time: time | None = None
    stoploss_reset_rc_time: time | None = None


@dataclass(frozen=True, slots=True)
class S23PaperOrderEvent:
    artifact_version: int
    timestamp: datetime
    session_date: date
    status: S23PaperOrderStatus
    selected_contract_symbol: str
    planned_entry_price: float
    reason_code: str
    message: str
    source_kind: str | None = None
    source_id: str | None = None
    source_effective_timestamp: datetime | None = None
    fill_price: float | None = None
    market_price: float | None = None
    bid: float | None = None
    ask: float | None = None
    low: float | None = None
    high: float | None = None


class S23PaperOrderStateStore:
    def create_waiting_order_from_live_decision(
        self,
        session_directory: str | Path,
        *,
        strategy_rule: StrategyRule,
        decision: S23PaperLiveDecisionResult | S23PaperTradeDecisionSummary,
        created_at: datetime,
        provenance_source_ids: tuple[str, ...] = (),
    ) -> tuple[S23PaperOrderState, Path, Path]:
        summary = decision.summary if isinstance(decision, S23PaperLiveDecisionResult) else decision
        self._validate_ready_summary(summary)
        assert summary.selected_contract_symbol is not None
        assert summary.selected_contract_expiry is not None
        assert summary.selected_contract_option_type is not None
        assert summary.planned_entry_price is not None
        assert summary.target_price is not None
        assert summary.stoploss_price is not None

        state = S23PaperOrderState(
            artifact_version=_ARTIFACT_VERSION,
            strategy_code=summary.strategy_code,
            strategy_branch=summary.strategy_branch,
            symbol=strategy_rule.symbol,
            selected_contract_symbol=summary.selected_contract_symbol,
            selected_contract_expiry=date.fromisoformat(summary.selected_contract_expiry),
            selected_contract_option_type=summary.selected_contract_option_type,
            selected_contract_strike=summary.selected_contract_strike,
            expiry_type=strategy_rule.expiry_policy.expiry_type.value,
            rollover_policy=strategy_rule.expiry_policy.rollover_policy.value,
            forced_close_time=strategy_rule.expiry_policy.forced_close_time,
            no_carry_past_expiry=strategy_rule.expiry_policy.no_carry_past_expiry,
            order_side="SELL",
            trigger_rule="SELL_TRIGGER_WHEN_PREMIUM_AT_OR_BELOW_ENTRY",
            entry_date=summary.session_date,
            order_timestamp=created_at,
            planned_entry_price=float(summary.planned_entry_price),
            target_price=float(summary.target_price),
            stoploss_price=float(summary.stoploss_price),
            fsl_price=summary.fsl_price,
            lots=summary.lots,
            quantity=summary.quantity,
            status=S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER,
            last_updated_timestamp=created_at,
            last_reason_code="paper_order_waiting_for_entry_trigger",
            last_message=(
                "READY decision created a paper sell order. The position will "
                "open only after selected option premium trades at or below entry."
            ),
            provenance_source_ids=provenance_source_ids,
            strategy_parameters=self._normalize_strategy_parameters(strategy_rule.parameters),
            stoploss_reset_buffer_pct=(
                float(strategy_rule.parameters["sl_reference_pct"])
                if "sl_reference_pct" in strategy_rule.parameters
                else None
            ),
            stoploss_reset_orpt_time=strategy_rule.entry_time,
            stoploss_reset_rc_time=strategy_rule.recalculation_time,
        )
        session_dir = Path(session_directory)
        state_path = self.save_state(session_dir, state)
        event = S23PaperOrderEvent(
            artifact_version=_ARTIFACT_VERSION,
            timestamp=created_at,
            session_date=state.entry_date,
            status=state.status,
            selected_contract_symbol=state.selected_contract_symbol,
            planned_entry_price=state.planned_entry_price,
            reason_code=state.last_reason_code or "paper_order_waiting_for_entry_trigger",
            message=state.last_message or "",
        )
        events_path = self.append_event(session_dir, event)
        return state, state_path, events_path

    def evaluate_waiting_order(
        self,
        session_directory: str | Path,
        *,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
        evaluated_at: datetime,
    ) -> tuple[S23PaperOrderState, S23PaperOrderEvent, Path, Path]:
        session_dir = Path(session_directory)
        state = self.load_state(session_dir)
        if state.status is S23PaperOrderStatus.PAPER_ORDER_FILLED:
            event = S23PaperOrderEvent(
                artifact_version=_ARTIFACT_VERSION,
                timestamp=evaluated_at,
                session_date=state.entry_date,
                status=state.status,
                selected_contract_symbol=state.selected_contract_symbol,
                planned_entry_price=state.planned_entry_price,
                reason_code="paper_order_already_filled",
                message="Persisted S23 paper order is already filled.",
                fill_price=state.fill_price,
            )
            return state, event, session_dir / _STATE_FILENAME, self.append_event(session_dir, event)

        sorted_events = tuple(
            sorted(
                market_events,
                key=lambda item: (
                    item.envelope.effective_timestamp,
                    item.envelope.captured_at,
                ),
            )
        )
        last_event: S23PaperOrderEvent | None = None
        for market_event in sorted_events:
            if market_event.symbol != state.selected_contract_symbol:
                continue
            evaluated_state, event = self._evaluate_event(state, market_event)
            state = evaluated_state
            last_event = event
            if state.status is S23PaperOrderStatus.PAPER_ORDER_FILLED:
                state_path = self.save_state(session_dir, state)
                events_path = self.append_event(session_dir, event)
                return state, event, state_path, events_path

        if last_event is None:
            event = S23PaperOrderEvent(
                artifact_version=_ARTIFACT_VERSION,
                timestamp=evaluated_at,
                session_date=state.entry_date,
                status=S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER,
                selected_contract_symbol=state.selected_contract_symbol,
                planned_entry_price=state.planned_entry_price,
                reason_code="paper_order_waiting_no_selected_contract_quote",
                message=(
                    "No selected-contract market event was available, so the paper "
                    "order remains waiting for the entry trigger."
                ),
            )
            state = replace(
                state,
                last_updated_timestamp=evaluated_at,
                last_reason_code=event.reason_code,
                last_message=event.message,
            )
        else:
            event = last_event
        state_path = self.save_state(session_dir, state)
        events_path = self.append_event(session_dir, event)
        return state, event, state_path, events_path

    def mark_not_filled(
        self,
        session_directory: str | Path,
        *,
        marked_at: datetime,
        reason_code: str,
        message: str,
    ) -> tuple[S23PaperOrderState, S23PaperOrderEvent, Path, Path]:
        session_dir = Path(session_directory)
        state = self.load_state(session_dir)
        if state.status is S23PaperOrderStatus.PAPER_ORDER_FILLED:
            event = S23PaperOrderEvent(
                artifact_version=_ARTIFACT_VERSION,
                timestamp=marked_at,
                session_date=state.entry_date,
                status=state.status,
                selected_contract_symbol=state.selected_contract_symbol,
                planned_entry_price=state.planned_entry_price,
                reason_code="paper_order_already_filled",
                message="Persisted S23 paper order is already filled.",
                fill_price=state.fill_price,
            )
            return state, event, session_dir / _STATE_FILENAME, self.append_event(session_dir, event)
        state = replace(
            state,
            status=S23PaperOrderStatus.PAPER_ORDER_NOT_FILLED,
            last_updated_timestamp=marked_at,
            last_reason_code=reason_code,
            last_message=message,
        )
        event = S23PaperOrderEvent(
            artifact_version=_ARTIFACT_VERSION,
            timestamp=marked_at,
            session_date=state.entry_date,
            status=state.status,
            selected_contract_symbol=state.selected_contract_symbol,
            planned_entry_price=state.planned_entry_price,
            reason_code=reason_code,
            message=message,
            market_price=state.last_market_price,
            bid=state.last_market_bid,
            ask=state.last_market_ask,
            low=state.last_market_low,
            high=state.last_market_high,
        )
        state_path = self.save_state(session_dir, state)
        events_path = self.append_event(session_dir, event)
        return state, event, state_path, events_path

    def save_state(self, session_directory: str | Path, state: S23PaperOrderState) -> Path:
        path = Path(session_directory) / _STATE_FILENAME
        self._write_json(path, state)
        return path

    def load_state(self, session_directory: str | Path) -> S23PaperOrderState:
        payload = self._load_json_required(Path(session_directory) / _STATE_FILENAME)
        return S23PaperOrderState(
            artifact_version=int(payload["artifact_version"]),
            strategy_code=str(payload["strategy_code"]),
            strategy_branch=str(payload["strategy_branch"]),
            symbol=str(payload["symbol"]),
            selected_contract_symbol=str(payload["selected_contract_symbol"]),
            selected_contract_expiry=date.fromisoformat(str(payload["selected_contract_expiry"])),
            selected_contract_option_type=str(payload["selected_contract_option_type"]),
            selected_contract_strike=(
                float(payload["selected_contract_strike"])
                if payload.get("selected_contract_strike") is not None
                else None
            ),
            expiry_type=str(payload.get("expiry_type", ExpiryType.WEEKLY.value)),
            rollover_policy=str(payload.get("rollover_policy", RolloverPolicy.T_MINUS_1.value)),
            forced_close_time=(
                time.fromisoformat(str(payload["forced_close_time"]))
                if payload.get("forced_close_time") is not None
                else None
            ),
            no_carry_past_expiry=bool(payload.get("no_carry_past_expiry", True)),
            order_side=str(payload["order_side"]),
            trigger_rule=str(payload["trigger_rule"]),
            entry_date=date.fromisoformat(str(payload["entry_date"])),
            order_timestamp=datetime.fromisoformat(str(payload["order_timestamp"])),
            planned_entry_price=float(payload["planned_entry_price"]),
            target_price=float(payload["target_price"]),
            stoploss_price=float(payload["stoploss_price"]),
            fsl_price=float(payload["fsl_price"]) if payload.get("fsl_price") is not None else None,
            lots=int(payload["lots"]),
            quantity=int(payload["quantity"]),
            status=S23PaperOrderStatus(str(payload["status"])),
            last_updated_timestamp=datetime.fromisoformat(str(payload["last_updated_timestamp"])),
            fill_price=float(payload["fill_price"]) if payload.get("fill_price") is not None else None,
            fill_timestamp=(
                datetime.fromisoformat(str(payload["fill_timestamp"]))
                if payload.get("fill_timestamp") is not None
                else None
            ),
            fill_source_kind=payload.get("fill_source_kind"),
            fill_source_id=payload.get("fill_source_id"),
            fill_source_effective_timestamp=(
                datetime.fromisoformat(str(payload["fill_source_effective_timestamp"]))
                if payload.get("fill_source_effective_timestamp") is not None
                else None
            ),
            last_market_price=(
                float(payload["last_market_price"])
                if payload.get("last_market_price") is not None
                else None
            ),
            last_market_bid=float(payload["last_market_bid"]) if payload.get("last_market_bid") is not None else None,
            last_market_ask=float(payload["last_market_ask"]) if payload.get("last_market_ask") is not None else None,
            last_market_low=float(payload["last_market_low"]) if payload.get("last_market_low") is not None else None,
            last_market_high=float(payload["last_market_high"]) if payload.get("last_market_high") is not None else None,
            last_reason_code=payload.get("last_reason_code"),
            last_message=payload.get("last_message"),
            provenance_source_ids=tuple(str(item) for item in payload.get("provenance_source_ids", ())),
            strategy_parameters=self._parse_strategy_parameters(
                payload.get("strategy_parameters")
            ),
            stoploss_reset_buffer_pct=(
                float(payload["stoploss_reset_buffer_pct"])
                if payload.get("stoploss_reset_buffer_pct") is not None
                else None
            ),
            stoploss_reset_orpt_time=(
                time.fromisoformat(str(payload["stoploss_reset_orpt_time"]))
                if payload.get("stoploss_reset_orpt_time") is not None
                else None
            ),
            stoploss_reset_rc_time=(
                time.fromisoformat(str(payload["stoploss_reset_rc_time"]))
                if payload.get("stoploss_reset_rc_time") is not None
                else None
            ),
        )

    def append_event(self, session_directory: str | Path, event: S23PaperOrderEvent) -> Path:
        path = Path(session_directory) / _EVENTS_FILENAME
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        rendered = existing + json.dumps(self._normalize(event), sort_keys=True) + "\n"
        self._atomic_write_text(path, rendered)
        return path

    def _evaluate_event(
        self,
        state: S23PaperOrderState,
        event: SelectedContractQuoteEvent | SelectedContractBarEvent,
    ) -> tuple[S23PaperOrderState, S23PaperOrderEvent]:
        timestamp = event.envelope.effective_timestamp
        if isinstance(event, SelectedContractQuoteEvent):
            market_price = event.ltp if event.ltp is not None else event.bid
            triggered = market_price is not None and float(market_price) <= state.planned_entry_price
            fill_price = None
            if triggered:
                fill_price = float(event.bid if event.bid is not None else market_price)
            status = (
                S23PaperOrderStatus.PAPER_ORDER_FILLED
                if triggered
                else S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER
            )
            reason_code = (
                "paper_order_filled_from_quote_entry_trigger"
                if triggered
                else "paper_order_waiting_quote_above_entry"
            )
            message = (
                "Selected option premium traded at or below entry, so the paper sell order was filled."
                if triggered
                else "Selected option premium is still above entry; the paper sell order remains waiting."
            )
            updated = replace(
                state,
                status=status,
                last_updated_timestamp=timestamp,
                fill_price=fill_price if triggered else state.fill_price,
                fill_timestamp=timestamp if triggered else state.fill_timestamp,
                fill_source_kind="selected_contract_quote" if triggered else state.fill_source_kind,
                fill_source_id=event.envelope.source_id if triggered else state.fill_source_id,
                fill_source_effective_timestamp=timestamp if triggered else state.fill_source_effective_timestamp,
                last_market_price=float(market_price) if market_price is not None else None,
                last_market_bid=float(event.bid) if event.bid is not None else None,
                last_market_ask=float(event.ask) if event.ask is not None else None,
                last_market_low=None,
                last_market_high=None,
                last_reason_code=reason_code,
                last_message=message,
            )
            order_event = S23PaperOrderEvent(
                artifact_version=_ARTIFACT_VERSION,
                timestamp=timestamp,
                session_date=state.entry_date,
                status=status,
                selected_contract_symbol=state.selected_contract_symbol,
                planned_entry_price=state.planned_entry_price,
                reason_code=reason_code,
                message=message,
                source_kind="selected_contract_quote",
                source_id=event.envelope.source_id,
                source_effective_timestamp=timestamp,
                fill_price=fill_price,
                market_price=float(market_price) if market_price is not None else None,
                bid=float(event.bid) if event.bid is not None else None,
                ask=float(event.ask) if event.ask is not None else None,
            )
            return updated, order_event

        low = float(event.low) if event.low is not None else None
        triggered = low is not None and low <= state.planned_entry_price
        status = (
            S23PaperOrderStatus.PAPER_ORDER_FILLED
            if triggered
            else S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER
        )
        fill_price = state.planned_entry_price if triggered else None
        reason_code = (
            "paper_order_filled_from_bar_entry_trigger"
            if triggered
            else "paper_order_waiting_bar_low_above_entry"
        )
        message = (
            "Selected option bar low reached entry, so the paper sell order was filled."
            if triggered
            else "Selected option bar low stayed above entry; the paper sell order remains waiting."
        )
        updated = replace(
            state,
            status=status,
            last_updated_timestamp=event.bar_end,
            fill_price=fill_price if triggered else state.fill_price,
            fill_timestamp=event.bar_end if triggered else state.fill_timestamp,
            fill_source_kind="selected_contract_bar" if triggered else state.fill_source_kind,
            fill_source_id=event.envelope.source_id if triggered else state.fill_source_id,
            fill_source_effective_timestamp=event.envelope.effective_timestamp if triggered else state.fill_source_effective_timestamp,
            last_market_price=float(event.close) if event.close is not None else None,
            last_market_low=low,
            last_market_high=float(event.high) if event.high is not None else None,
            last_reason_code=reason_code,
            last_message=message,
        )
        order_event = S23PaperOrderEvent(
            artifact_version=_ARTIFACT_VERSION,
            timestamp=event.bar_end,
            session_date=state.entry_date,
            status=status,
            selected_contract_symbol=state.selected_contract_symbol,
            planned_entry_price=state.planned_entry_price,
            reason_code=reason_code,
            message=message,
            source_kind="selected_contract_bar",
            source_id=event.envelope.source_id,
            source_effective_timestamp=event.envelope.effective_timestamp,
            fill_price=fill_price,
            market_price=float(event.close) if event.close is not None else None,
            low=low,
            high=float(event.high) if event.high is not None else None,
        )
        return updated, order_event

    @staticmethod
    def _validate_ready_summary(summary: S23PaperTradeDecisionSummary) -> None:
        if summary.status != "READY":
            raise S23PaperOrderStateError(
                f"Cannot create paper order from decision status {summary.status!r}."
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
            raise S23PaperOrderStateError(
                "Cannot create paper order; decision summary is missing "
                + ", ".join(missing)
            )

    @staticmethod
    def _load_json_required(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise S23PaperOrderStateError(f"Missing S23 paper order state: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise S23PaperOrderStateError(f"Invalid S23 paper order state: {path}")
        return payload

    def _parse_strategy_parameters(self, value: Any) -> dict[str, float] | None:
        if value in (None, ""):
            return None
        if not isinstance(value, dict):
            raise S23PaperOrderStateError("strategy_parameters must be a JSON object")
        return self._normalize_strategy_parameters(value)

    @staticmethod
    def _normalize_strategy_parameters(value: dict[str, Any] | None) -> dict[str, float] | None:
        if value in (None, {}):
            return None
        normalized: dict[str, float] = {}
        for key, raw_value in value.items():
            key_text = str(key).strip()
            if not key_text:
                raise S23PaperOrderStateError(
                    "strategy_parameters keys must be non-empty strings"
                )
            if isinstance(raw_value, bool):
                raise S23PaperOrderStateError(
                    f"strategy parameter {key_text!r} must be numeric"
                )
            try:
                normalized[key_text] = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise S23PaperOrderStateError(
                    f"strategy parameter {key_text!r} must be numeric"
                ) from exc
        return normalized

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
        return value


__all__ = [
    "S23PaperOrderEvent",
    "S23PaperOrderState",
    "S23PaperOrderStateError",
    "S23PaperOrderStateStore",
    "S23PaperOrderStatus",
]
