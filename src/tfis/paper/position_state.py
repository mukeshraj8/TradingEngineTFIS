from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any

from tfis.domain import ExpiryType, RolloverPolicy, StrategyExpiryPolicy
from tfis.domain.enums import OptionType


_ARTIFACT_VERSION = 1
_STATE_FILENAME = "paper_position_state.json"
_EVENTS_FILENAME = "paper_position_state_events.jsonl"


class S23PaperPositionStateError(RuntimeError):
    """Raised when persisted paper position state cannot be used safely."""


class S23PaperPositionStateStatus(str, Enum):
    PAPER_POSITION_OPEN = "PAPER_POSITION_OPEN"
    PAPER_POSITION_CARRIED_FORWARD = "PAPER_POSITION_CARRIED_FORWARD"
    PAPER_POSITION_RESUMED = "PAPER_POSITION_RESUMED"


class S23PaperPositionStateEventType(str, Enum):
    PAPER_POSITION_CARRIED_FORWARD = "PAPER_POSITION_CARRIED_FORWARD"
    PAPER_POSITION_RESUMED = "PAPER_POSITION_RESUMED"
    PAPER_POSITION_STATE_INVALID = "PAPER_POSITION_STATE_INVALID"
    PAPER_EXPIRY_FORCE_CLOSE_REQUIRED = "PAPER_EXPIRY_FORCE_CLOSE_REQUIRED"
    PAPER_EXPIRY_FORCE_CLOSED = "PAPER_EXPIRY_FORCE_CLOSED"
    PAPER_NEXT_EXPIRY_REQUIRED = "PAPER_NEXT_EXPIRY_REQUIRED"
    PAPER_ROLLOVER_POLICY_APPLIED = "PAPER_ROLLOVER_POLICY_APPLIED"


@dataclass(frozen=True, slots=True)
class S23PaperPositionState:
    artifact_version: int
    strategy_code: str
    unique_code: str
    symbol: str
    option_type: OptionType
    selected_contract_symbol: str
    expiry_date: date
    expiry_policy: StrategyExpiryPolicy
    entry_date: date
    entry_timestamp: datetime
    entry_price: float
    lots: int
    quantity: int
    side: str
    target_price: float
    stoploss_price: float
    fsl_price: float | None
    trp_price: float | None
    carry_forward_allowed: bool
    no_carry_past_expiry: bool
    lifecycle_status: S23PaperPositionStateStatus
    last_updated_timestamp: datetime
    provenance_source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "strategy_code",
            "unique_code",
            "symbol",
            "selected_contract_symbol",
            "side",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

        if not isinstance(self.option_type, OptionType):
            raise TypeError("option_type must be an OptionType value")
        if not isinstance(self.expiry_date, date):
            raise TypeError("expiry_date must be a date")
        if not isinstance(self.expiry_policy, StrategyExpiryPolicy):
            raise TypeError("expiry_policy must be a StrategyExpiryPolicy instance")
        if not isinstance(self.entry_date, date):
            raise TypeError("entry_date must be a date")
        if not isinstance(self.entry_timestamp, datetime):
            raise TypeError("entry_timestamp must be a datetime")
        if not isinstance(self.last_updated_timestamp, datetime):
            raise TypeError("last_updated_timestamp must be a datetime")
        if self.entry_price <= 0:
            raise ValueError("entry_price must be positive")
        if self.target_price <= 0:
            raise ValueError("target_price must be positive")
        if self.stoploss_price <= 0:
            raise ValueError("stoploss_price must be positive")
        if self.lots <= 0:
            raise ValueError("lots must be positive")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if not isinstance(self.carry_forward_allowed, bool):
            raise TypeError("carry_forward_allowed must be a bool")
        if not isinstance(self.no_carry_past_expiry, bool):
            raise TypeError("no_carry_past_expiry must be a bool")
        if not isinstance(self.lifecycle_status, S23PaperPositionStateStatus):
            raise TypeError(
                "lifecycle_status must be a S23PaperPositionStateStatus value"
            )
        if any(not isinstance(item, str) or not item.strip() for item in self.provenance_source_ids):
            raise ValueError("provenance_source_ids must contain non-empty strings")


@dataclass(frozen=True, slots=True)
class S23PaperPositionStateEvent:
    timestamp: datetime
    event_type: S23PaperPositionStateEventType
    strategy_code: str
    unique_code: str
    selected_contract_symbol: str
    lifecycle_status: S23PaperPositionStateStatus | None
    session_date: date | None
    reason_code: str | None
    message: str
    provenance_source_ids: tuple[str, ...] = ()


class S23PaperPositionStateStore:
    def __init__(
        self,
        *,
        state_filename: str = _STATE_FILENAME,
        events_filename: str = _EVENTS_FILENAME,
    ) -> None:
        self._state_filename = state_filename
        self._events_filename = events_filename

    def create_open_position_state(
        self,
        *,
        strategy_code: str,
        unique_code: str,
        symbol: str,
        option_type: OptionType,
        selected_contract_symbol: str,
        expiry_date: date,
        expiry_type: ExpiryType,
        rollover_policy: RolloverPolicy,
        forced_close_time: time | None,
        no_carry_past_expiry: bool,
        entry_date: date,
        entry_timestamp: datetime,
        entry_price: float,
        lots: int,
        quantity: int,
        side: str,
        target_price: float,
        stoploss_price: float,
        fsl_price: float | None,
        trp_price: float | None,
        carry_forward_allowed: bool,
        last_updated_timestamp: datetime,
        provenance_source_ids: tuple[str, ...] = (),
    ) -> S23PaperPositionState:
        return S23PaperPositionState(
            artifact_version=_ARTIFACT_VERSION,
            strategy_code=strategy_code,
            unique_code=unique_code,
            symbol=symbol,
            option_type=option_type,
            selected_contract_symbol=selected_contract_symbol,
            expiry_date=expiry_date,
            expiry_policy=StrategyExpiryPolicy(
                expiry_type=expiry_type,
                rollover_policy=rollover_policy,
                forced_close_time=forced_close_time,
                no_carry_past_expiry=no_carry_past_expiry,
            ),
            entry_date=entry_date,
            entry_timestamp=entry_timestamp,
            entry_price=entry_price,
            lots=lots,
            quantity=quantity,
            side=side,
            target_price=target_price,
            stoploss_price=stoploss_price,
            fsl_price=fsl_price,
            trp_price=trp_price,
            carry_forward_allowed=carry_forward_allowed,
            no_carry_past_expiry=no_carry_past_expiry,
            lifecycle_status=S23PaperPositionStateStatus.PAPER_POSITION_OPEN,
            last_updated_timestamp=last_updated_timestamp,
            provenance_source_ids=provenance_source_ids,
        )

    def save_state(
        self,
        session_directory: str | Path,
        state: S23PaperPositionState,
    ) -> Path:
        session_dir = Path(session_directory)
        path = session_dir / self._state_filename
        self._write_json(path, self._state_payload(state))
        return path

    def load_state(self, session_directory: str | Path) -> S23PaperPositionState:
        session_dir = Path(session_directory)
        path = session_dir / self._state_filename
        try:
            payload = self._load_json_required(path)
            return self._state_from_payload(payload)
        except Exception as exc:
            self._append_invalid_state_event(
                session_dir,
                timestamp=datetime.now(),
                message=f"Persisted paper position state is invalid: {exc}",
            )
            raise S23PaperPositionStateError(str(exc)) from exc

    def carry_forward(
        self,
        session_directory: str | Path,
        *,
        next_session_date: date,
        updated_at: datetime,
        expiry_governance: Any | None = None,
        provenance_source_ids: tuple[str, ...] = (),
    ) -> S23PaperPositionState:
        state = self.load_state(session_directory)
        session_dir = Path(session_directory)
        if not state.carry_forward_allowed:
            raise S23PaperPositionStateError(
                "Carry-forward is not allowed for this persisted paper position state."
            )
        if expiry_governance is not None:
            self._apply_expiry_governance_gate(
                session_directory=session_dir,
                state=state,
                session_date=next_session_date,
                event_timestamp=updated_at,
                current_time=updated_at.timetz().replace(tzinfo=None),
                expiry_governance=expiry_governance,
                provenance_source_ids=provenance_source_ids,
            )
        if next_session_date > state.expiry_date:
            self._append_invalid_state_event(
                session_dir,
                timestamp=updated_at,
                strategy_code=state.strategy_code,
                unique_code=state.unique_code,
                selected_contract_symbol=state.selected_contract_symbol,
                session_date=next_session_date,
                reason_code="carry_forward_past_expiry",
                message=(
                    "Carry-forward was requested after contract expiry, which is not allowed."
                ),
                provenance_source_ids=provenance_source_ids,
            )
            raise S23PaperPositionStateError(
                "Cannot carry the paper position beyond expiry."
            )

        updated_state = S23PaperPositionState(
            artifact_version=state.artifact_version,
            strategy_code=state.strategy_code,
            unique_code=state.unique_code,
            symbol=state.symbol,
            option_type=state.option_type,
            selected_contract_symbol=state.selected_contract_symbol,
            expiry_date=state.expiry_date,
            expiry_policy=state.expiry_policy,
            entry_date=state.entry_date,
            entry_timestamp=state.entry_timestamp,
            entry_price=state.entry_price,
            lots=state.lots,
            quantity=state.quantity,
            side=state.side,
            target_price=state.target_price,
            stoploss_price=state.stoploss_price,
            fsl_price=state.fsl_price,
            trp_price=state.trp_price,
            carry_forward_allowed=state.carry_forward_allowed,
            no_carry_past_expiry=state.no_carry_past_expiry,
            lifecycle_status=S23PaperPositionStateStatus.PAPER_POSITION_CARRIED_FORWARD,
            last_updated_timestamp=updated_at,
            provenance_source_ids=self._merge_provenance(
                state.provenance_source_ids,
                provenance_source_ids,
            ),
        )
        self.save_state(session_dir, updated_state)
        self._append_event(
            session_dir,
            S23PaperPositionStateEvent(
                timestamp=updated_at,
                event_type=S23PaperPositionStateEventType.PAPER_POSITION_CARRIED_FORWARD,
                strategy_code=updated_state.strategy_code,
                unique_code=updated_state.unique_code,
                selected_contract_symbol=updated_state.selected_contract_symbol,
                lifecycle_status=updated_state.lifecycle_status,
                session_date=next_session_date,
                reason_code=None,
                message="Paper position state was marked as carried forward.",
                provenance_source_ids=provenance_source_ids,
            ),
        )
        return updated_state

    def resume_position(
        self,
        session_directory: str | Path,
        *,
        session_date: date,
        resumed_at: datetime,
        expiry_governance: Any | None = None,
        provenance_source_ids: tuple[str, ...] = (),
    ) -> S23PaperPositionState:
        state = self.load_state(session_directory)
        session_dir = Path(session_directory)
        if not state.carry_forward_allowed:
            raise S23PaperPositionStateError(
                "Carry-forward resume is not allowed for this persisted paper position state."
            )
        if expiry_governance is not None:
            self._apply_expiry_governance_gate(
                session_directory=session_dir,
                state=state,
                session_date=session_date,
                event_timestamp=resumed_at,
                current_time=resumed_at.timetz().replace(tzinfo=None),
                expiry_governance=expiry_governance,
                provenance_source_ids=provenance_source_ids,
            )
        if session_date > state.expiry_date:
            self._append_invalid_state_event(
                session_dir,
                timestamp=resumed_at,
                strategy_code=state.strategy_code,
                unique_code=state.unique_code,
                selected_contract_symbol=state.selected_contract_symbol,
                session_date=session_date,
                reason_code="resume_past_expiry",
                message=(
                    "Paper position resume was requested after contract expiry, which is not allowed."
                ),
                provenance_source_ids=provenance_source_ids,
            )
            raise S23PaperPositionStateError(
                "Cannot resume a paper position after expiry has passed."
            )

        updated_state = S23PaperPositionState(
            artifact_version=state.artifact_version,
            strategy_code=state.strategy_code,
            unique_code=state.unique_code,
            symbol=state.symbol,
            option_type=state.option_type,
            selected_contract_symbol=state.selected_contract_symbol,
            expiry_date=state.expiry_date,
            expiry_policy=state.expiry_policy,
            entry_date=state.entry_date,
            entry_timestamp=state.entry_timestamp,
            entry_price=state.entry_price,
            lots=state.lots,
            quantity=state.quantity,
            side=state.side,
            target_price=state.target_price,
            stoploss_price=state.stoploss_price,
            fsl_price=state.fsl_price,
            trp_price=state.trp_price,
            carry_forward_allowed=state.carry_forward_allowed,
            no_carry_past_expiry=state.no_carry_past_expiry,
            lifecycle_status=S23PaperPositionStateStatus.PAPER_POSITION_RESUMED,
            last_updated_timestamp=resumed_at,
            provenance_source_ids=self._merge_provenance(
                state.provenance_source_ids,
                provenance_source_ids,
            ),
        )
        self.save_state(session_dir, updated_state)
        self._append_event(
            session_dir,
            S23PaperPositionStateEvent(
                timestamp=resumed_at,
                event_type=S23PaperPositionStateEventType.PAPER_POSITION_RESUMED,
                strategy_code=updated_state.strategy_code,
                unique_code=updated_state.unique_code,
                selected_contract_symbol=updated_state.selected_contract_symbol,
                lifecycle_status=updated_state.lifecycle_status,
                session_date=session_date,
                reason_code=None,
                message="Paper position state was resumed for the new session.",
                provenance_source_ids=provenance_source_ids,
            ),
        )
        return updated_state

    def load_events(
        self,
        session_directory: str | Path,
    ) -> tuple[S23PaperPositionStateEvent, ...]:
        path = Path(session_directory) / self._events_filename
        if not path.exists():
            return ()
        events: list[S23PaperPositionStateEvent] = []
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            events.append(
                S23PaperPositionStateEvent(
                    timestamp=self._parse_datetime(payload.get("timestamp"), "timestamp"),
                    event_type=self._parse_event_type(payload.get("event_type")),
                    strategy_code=self._parse_text(payload.get("strategy_code"), "strategy_code"),
                    unique_code=self._parse_text(payload.get("unique_code"), "unique_code"),
                    selected_contract_symbol=self._parse_text(
                        payload.get("selected_contract_symbol"),
                        "selected_contract_symbol",
                    ),
                    lifecycle_status=self._parse_optional_lifecycle_status(
                        payload.get("lifecycle_status")
                    ),
                    session_date=self._parse_optional_date(payload.get("session_date")),
                    reason_code=self._parse_optional_text(payload.get("reason_code")),
                    message=self._parse_text(payload.get("message"), "message"),
                    provenance_source_ids=self._parse_optional_text_tuple(
                        payload.get("provenance_source_ids")
                    ),
                )
            )
        return tuple(events)

    def record_expiry_force_closed(
        self,
        session_directory: str | Path,
        *,
        session_date: date,
        closed_at: datetime,
        provenance_source_ids: tuple[str, ...] = (),
    ) -> None:
        state = self.load_state(session_directory)
        self._append_event(
            Path(session_directory),
            S23PaperPositionStateEvent(
                timestamp=closed_at,
                event_type=S23PaperPositionStateEventType.PAPER_EXPIRY_FORCE_CLOSED,
                strategy_code=state.strategy_code,
                unique_code=state.unique_code,
                selected_contract_symbol=state.selected_contract_symbol,
                lifecycle_status=state.lifecycle_status,
                session_date=session_date,
                reason_code="expiry_force_closed",
                message="Current-expiry paper exposure was force-closed under expiry governance.",
                provenance_source_ids=provenance_source_ids,
            ),
        )

    def _append_invalid_state_event(
        self,
        session_directory: Path,
        *,
        timestamp: datetime,
        message: str,
        strategy_code: str = "S23",
        unique_code: str = "unknown",
        selected_contract_symbol: str = "unknown",
        session_date: date | None = None,
        reason_code: str = "invalid_persisted_position_state",
        provenance_source_ids: tuple[str, ...] = (),
    ) -> None:
        self._append_event(
            session_directory,
            S23PaperPositionStateEvent(
                timestamp=timestamp,
                event_type=S23PaperPositionStateEventType.PAPER_POSITION_STATE_INVALID,
                strategy_code=strategy_code,
                unique_code=unique_code,
                selected_contract_symbol=selected_contract_symbol,
                lifecycle_status=None,
                session_date=session_date,
                reason_code=reason_code,
                message=message,
                provenance_source_ids=provenance_source_ids,
            ),
        )

    def _append_event(
        self,
        session_directory: Path,
        event: S23PaperPositionStateEvent,
    ) -> None:
        existing = list(self.load_events(session_directory))
        existing.append(event)
        path = session_directory / self._events_filename
        self._write_jsonl(path, tuple(existing))

    def _apply_expiry_governance_gate(
        self,
        *,
        session_directory: Path,
        state: S23PaperPositionState,
        session_date: date,
        event_timestamp: datetime,
        current_time: time,
        expiry_governance: Any,
        provenance_source_ids: tuple[str, ...],
    ) -> None:
        decision = expiry_governance.evaluate_position(
            state,
            session_date=session_date,
            current_time=current_time,
        )
        if decision.can_carry_forward:
            return
        for event in expiry_governance.build_events(
            state,
            session_date=session_date,
            event_timestamp=event_timestamp,
            current_time=current_time,
            provenance_source_ids=provenance_source_ids,
        ):
            self._append_event(session_directory, event)
        reason = (
            "Current-expiry continuation is blocked by the configured rollover policy."
            if decision.should_select_next_expiry
            else "Current-expiry continuation is blocked by expiry governance."
        )
        raise S23PaperPositionStateError(reason)

    def _state_from_payload(self, payload: dict[str, Any]) -> S23PaperPositionState:
        expiry_policy_payload = payload.get("expiry_policy") if isinstance(payload.get("expiry_policy"), dict) else None
        return S23PaperPositionState(
            artifact_version=self._parse_int(payload.get("artifact_version"), "artifact_version"),
            strategy_code=self._parse_text(payload.get("strategy_code"), "strategy_code"),
            unique_code=self._parse_text(payload.get("unique_code"), "unique_code"),
            symbol=self._parse_text(payload.get("symbol"), "symbol"),
            option_type=self._parse_option_type(payload.get("option_type")),
            selected_contract_symbol=self._parse_text(
                payload.get("selected_contract_symbol"),
                "selected_contract_symbol",
            ),
            expiry_date=self._parse_date(payload.get("expiry_date"), "expiry_date"),
            expiry_policy=StrategyExpiryPolicy(
                expiry_type=self._parse_expiry_type(
                    payload.get("expiry_type")
                    if payload.get("expiry_type") is not None
                    else (expiry_policy_payload or {}).get("expiry_type")
                ),
                rollover_policy=self._parse_rollover_policy(
                    payload.get("rollover_policy")
                    if payload.get("rollover_policy") is not None
                    else (expiry_policy_payload or {}).get("rollover_policy")
                ),
                forced_close_time=self._parse_optional_time(
                    payload.get("forced_close_time")
                    if payload.get("forced_close_time") is not None
                    else (expiry_policy_payload or {}).get("forced_close_time")
                ),
                no_carry_past_expiry=self._parse_bool(
                    payload.get("no_carry_past_expiry")
                    if payload.get("no_carry_past_expiry") is not None
                    else (expiry_policy_payload or {}).get("no_carry_past_expiry"),
                    "no_carry_past_expiry",
                ),
            ),
            entry_date=self._parse_date(payload.get("entry_date"), "entry_date"),
            entry_timestamp=self._parse_datetime(
                payload.get("entry_timestamp"),
                "entry_timestamp",
            ),
            entry_price=self._parse_float(payload.get("entry_price"), "entry_price"),
            lots=self._parse_int(payload.get("lots"), "lots"),
            quantity=self._parse_int(payload.get("quantity"), "quantity"),
            side=self._parse_text(payload.get("side"), "side"),
            target_price=self._parse_float(payload.get("target_price"), "target_price"),
            stoploss_price=self._parse_float(
                payload.get("stoploss_price"),
                "stoploss_price",
            ),
            fsl_price=self._parse_optional_float(payload.get("fsl_price")),
            trp_price=self._parse_optional_float(payload.get("trp_price")),
            carry_forward_allowed=self._parse_bool(
                payload.get("carry_forward_allowed"),
                "carry_forward_allowed",
            ),
            no_carry_past_expiry=self._parse_bool(
                payload.get("no_carry_past_expiry"),
                "no_carry_past_expiry",
            ),
            lifecycle_status=self._parse_lifecycle_status(payload.get("lifecycle_status")),
            last_updated_timestamp=self._parse_datetime(
                payload.get("last_updated_timestamp"),
                "last_updated_timestamp",
            ),
            provenance_source_ids=self._parse_optional_text_tuple(
                payload.get("provenance_source_ids")
            ),
        )

    def _load_json_required(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise S23PaperPositionStateError(
                f"Persisted paper position state is missing: {path}"
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise S23PaperPositionStateError(
                f"Persisted paper position state is corrupt JSON: {path}"
            ) from exc
        if not isinstance(payload, dict):
            raise S23PaperPositionStateError(
                "Persisted paper position state must be a JSON object."
            )
        return payload

    def _write_json(self, path: Path, payload: Any) -> None:
        rendered = json.dumps(self._normalize(payload), indent=2, sort_keys=True) + "\n"
        self._atomic_write_text(path, rendered)

    def _write_jsonl(self, path: Path, rows: tuple[Any, ...]) -> None:
        rendered = "".join(
            json.dumps(self._normalize(row), sort_keys=True) + "\n" for row in rows
        )
        self._atomic_write_text(path, rendered)

    def _atomic_write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.parent / f".{path.name}.tmp"
        try:
            with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
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

    def _merge_provenance(
        self,
        existing: tuple[str, ...],
        new_items: tuple[str, ...],
    ) -> tuple[str, ...]:
        merged: list[str] = []
        for item in existing + new_items:
            text = str(item).strip()
            if text and text not in merged:
                merged.append(text)
        return tuple(merged)

    def _parse_text(self, value: Any, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise S23PaperPositionStateError(f"{field_name} must be a non-empty string")
        return value.strip()

    def _parse_optional_text(self, value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(value).strip() or None

    def _parse_optional_text_tuple(self, value: Any) -> tuple[str, ...]:
        if value in (None, ()):
            return ()
        if not isinstance(value, list | tuple):
            raise S23PaperPositionStateError(
                "provenance_source_ids must be a JSON array when present"
            )
        normalized: list[str] = []
        for item in value:
            text = self._parse_text(item, "provenance_source_ids[]")
            normalized.append(text)
        return tuple(normalized)

    def _parse_bool(self, value: Any, field_name: str) -> bool:
        if not isinstance(value, bool):
            raise S23PaperPositionStateError(f"{field_name} must be a bool")
        return value

    def _parse_int(self, value: Any, field_name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise S23PaperPositionStateError(f"{field_name} must be an integer")
        return value

    def _parse_float(self, value: Any, field_name: str) -> float:
        if value is None:
            raise S23PaperPositionStateError(f"{field_name} is required")
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise S23PaperPositionStateError(f"{field_name} must be numeric") from exc

    def _parse_optional_float(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise S23PaperPositionStateError("optional price fields must be numeric") from exc

    def _parse_date(self, value: Any, field_name: str) -> date:
        if value is None:
            raise S23PaperPositionStateError(f"{field_name} is required")
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        try:
            return date.fromisoformat(str(value))
        except ValueError as exc:
            raise S23PaperPositionStateError(
                f"{field_name} must be an ISO date"
            ) from exc

    def _parse_optional_date(self, value: Any) -> date | None:
        if value in (None, ""):
            return None
        return self._parse_date(value, "session_date")

    def _parse_datetime(self, value: Any, field_name: str) -> datetime:
        if value is None:
            raise S23PaperPositionStateError(f"{field_name} is required")
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except ValueError as exc:
            raise S23PaperPositionStateError(
                f"{field_name} must be an ISO datetime"
            ) from exc

    def _parse_optional_time(self, value: Any) -> time | None:
        if value in (None, ""):
            return None
        if isinstance(value, time):
            return value
        try:
            return time.fromisoformat(str(value))
        except ValueError as exc:
            raise S23PaperPositionStateError(
                "forced_close_time must be an ISO time"
            ) from exc

    def _parse_option_type(self, value: Any) -> OptionType:
        try:
            return OptionType(str(value))
        except ValueError as exc:
            raise S23PaperPositionStateError(
                "option_type must be a valid OptionType value"
            ) from exc

    def _parse_lifecycle_status(self, value: Any) -> S23PaperPositionStateStatus:
        try:
            return S23PaperPositionStateStatus(str(value))
        except ValueError as exc:
            raise S23PaperPositionStateError(
                "lifecycle_status must be a valid S23PaperPositionStateStatus value"
            ) from exc

    def _parse_optional_lifecycle_status(
        self,
        value: Any,
    ) -> S23PaperPositionStateStatus | None:
        if value in (None, ""):
            return None
        return self._parse_lifecycle_status(value)

    def _parse_event_type(self, value: Any) -> S23PaperPositionStateEventType:
        try:
            return S23PaperPositionStateEventType(str(value))
        except ValueError as exc:
            raise S23PaperPositionStateError(
                "event_type must be a valid S23PaperPositionStateEventType value"
            ) from exc

    def _state_payload(self, state: S23PaperPositionState) -> dict[str, Any]:
        return {
            "artifact_version": state.artifact_version,
            "strategy_code": state.strategy_code,
            "unique_code": state.unique_code,
            "symbol": state.symbol,
            "option_type": state.option_type,
            "selected_contract_symbol": state.selected_contract_symbol,
            "expiry_date": state.expiry_date,
            "expiry_type": state.expiry_policy.expiry_type,
            "rollover_policy": state.expiry_policy.rollover_policy,
            "forced_close_time": state.expiry_policy.forced_close_time,
            "entry_date": state.entry_date,
            "entry_timestamp": state.entry_timestamp,
            "entry_price": state.entry_price,
            "lots": state.lots,
            "quantity": state.quantity,
            "side": state.side,
            "target_price": state.target_price,
            "stoploss_price": state.stoploss_price,
            "fsl_price": state.fsl_price,
            "trp_price": state.trp_price,
            "carry_forward_allowed": state.carry_forward_allowed,
            "no_carry_past_expiry": state.no_carry_past_expiry,
            "lifecycle_status": state.lifecycle_status,
            "last_updated_timestamp": state.last_updated_timestamp,
            "provenance_source_ids": state.provenance_source_ids,
        }

    def _parse_expiry_type(self, value: Any) -> ExpiryType:
        try:
            return ExpiryType(str(value))
        except ValueError as exc:
            raise S23PaperPositionStateError(
                "expiry_type must be a valid ExpiryType value"
            ) from exc

    def _parse_rollover_policy(self, value: Any) -> RolloverPolicy:
        try:
            return RolloverPolicy(str(value))
        except ValueError as exc:
            raise S23PaperPositionStateError(
                "rollover_policy must be a valid RolloverPolicy value"
            ) from exc
