from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Protocol

from tfis.domain import ExpiryType, RolloverPolicy, StrategyExpiryPolicy, StrategyRule

from .position_state import (
    S23PaperPositionState,
    S23PaperPositionStateEvent,
    S23PaperPositionStateEventType,
    S23PaperPositionStateStatus,
)


class ExpiryCalendar(Protocol):
    def is_trading_day(self, value: date) -> bool: ...

    def previous_trading_day(self, value: date) -> date: ...

    def resolve_expiry(self, expiry_type: ExpiryType, session_date: date) -> date: ...

    def trading_days_until(self, session_date: date, expiry_date: date) -> int: ...


class DeterministicExpiryCalendar:
    def __init__(
        self,
        *,
        holidays: tuple[date, ...] = (),
        explicit_expiries: dict[tuple[ExpiryType, date], date] | None = None,
    ) -> None:
        self._holidays = frozenset(holidays)
        self._explicit_expiries = dict(explicit_expiries or {})

    def is_trading_day(self, value: date) -> bool:
        return value.weekday() < 5 and value not in self._holidays

    def previous_trading_day(self, value: date) -> date:
        cursor = value - timedelta(days=1)
        while not self.is_trading_day(cursor):
            cursor -= timedelta(days=1)
        return cursor

    def resolve_expiry(self, expiry_type: ExpiryType, session_date: date) -> date:
        explicit = self._explicit_expiries.get((expiry_type, session_date))
        if explicit is not None:
            return explicit
        if expiry_type is ExpiryType.WEEKLY:
            return self._resolve_weekly_expiry(session_date)
        raise ValueError(f"Unsupported expiry_type: {expiry_type.value}")

    def trading_days_until(self, session_date: date, expiry_date: date) -> int:
        if session_date > expiry_date:
            return -1
        days = 0
        cursor = session_date + timedelta(days=1)
        while cursor <= expiry_date:
            if self.is_trading_day(cursor):
                days += 1
            cursor += timedelta(days=1)
        return days

    def _resolve_weekly_expiry(self, session_date: date) -> date:
        cursor = session_date
        while True:
            if cursor.weekday() == 3 and self.is_trading_day(cursor):
                return cursor
            cursor += timedelta(days=1)


@dataclass(frozen=True, slots=True)
class S23PaperExpiryGovernanceDecision:
    can_carry_forward: bool
    must_force_close: bool
    should_select_next_expiry: bool
    event_types: tuple[S23PaperPositionStateEventType, ...]
    message: str


class S23PaperExpiryGovernance:
    def __init__(self, calendar: ExpiryCalendar) -> None:
        self._calendar = calendar

    def resolve_expiry_date(
        self,
        strategy: StrategyRule | StrategyExpiryPolicy | S23PaperPositionState,
        session_date: date,
    ) -> date:
        if isinstance(strategy, S23PaperPositionState):
            return strategy.expiry_date
        policy = self._extract_policy(strategy)
        return self._calendar.resolve_expiry(policy.expiry_type, session_date)

    def can_carry_forward(
        self,
        position: S23PaperPositionState,
        session_date: date,
    ) -> bool:
        if not position.carry_forward_allowed:
            return False
        if position.no_carry_past_expiry and session_date >= position.expiry_date:
            return False
        if self._should_select_next_expiry_for_policy(
            position.expiry_policy,
            session_date,
            current_expiry=position.expiry_date,
        ):
            return False
        return True

    def must_force_close(
        self,
        position: S23PaperPositionState,
        session_date: date,
        current_time: time,
    ) -> bool:
        if position.no_carry_past_expiry and session_date > position.expiry_date:
            return True
        if session_date == position.expiry_date:
            if position.expiry_policy.forced_close_time is None:
                return True
            return current_time >= position.expiry_policy.forced_close_time
        if self._should_select_next_expiry_for_policy(
            position.expiry_policy,
            session_date,
            current_expiry=position.expiry_date,
        ):
            if position.expiry_policy.forced_close_time is None:
                return True
            return current_time >= position.expiry_policy.forced_close_time
        return False

    def should_select_next_expiry(
        self,
        strategy: StrategyRule | StrategyExpiryPolicy | S23PaperPositionState,
        session_date: date,
    ) -> bool:
        policy = self._extract_policy(strategy)
        current_expiry = self.resolve_expiry_date(strategy, session_date)
        return self._should_select_next_expiry_for_policy(
            policy,
            session_date,
            current_expiry=current_expiry,
        )

    def evaluate_position(
        self,
        position: S23PaperPositionState,
        *,
        session_date: date,
        current_time: time,
    ) -> S23PaperExpiryGovernanceDecision:
        should_next = self.should_select_next_expiry(position, session_date)
        force_close = self.must_force_close(position, session_date, current_time)
        carry_allowed = self.can_carry_forward(position, session_date)
        event_types: list[S23PaperPositionStateEventType] = []
        messages: list[str] = []

        if should_next:
            event_types.append(
                S23PaperPositionStateEventType.PAPER_ROLLOVER_POLICY_APPLIED
            )
            event_types.append(
                S23PaperPositionStateEventType.PAPER_NEXT_EXPIRY_REQUIRED
            )
            messages.append("Current expiry is inside the configured rollover window.")
        if force_close:
            event_types.append(
                S23PaperPositionStateEventType.PAPER_EXPIRY_FORCE_CLOSE_REQUIRED
            )
            messages.append("Current-expiry exposure must be force-closed under expiry governance.")
        if not messages:
            messages.append("Carry-forward remains allowed for the current expiry.")

        return S23PaperExpiryGovernanceDecision(
            can_carry_forward=carry_allowed,
            must_force_close=force_close,
            should_select_next_expiry=should_next,
            event_types=tuple(event_types),
            message=" ".join(messages),
        )

    def build_events(
        self,
        position: S23PaperPositionState,
        *,
        session_date: date,
        event_timestamp: datetime,
        current_time: time,
        provenance_source_ids: tuple[str, ...] = (),
    ) -> tuple[S23PaperPositionStateEvent, ...]:
        decision = self.evaluate_position(
            position,
            session_date=session_date,
            current_time=current_time,
        )
        events: list[S23PaperPositionStateEvent] = []
        for event_type in decision.event_types:
            events.append(
                S23PaperPositionStateEvent(
                    timestamp=event_timestamp,
                    event_type=event_type,
                    strategy_code=position.strategy_code,
                    unique_code=position.unique_code,
                    selected_contract_symbol=position.selected_contract_symbol,
                    lifecycle_status=position.lifecycle_status,
                    session_date=session_date,
                    reason_code=self._reason_code_for_event(event_type),
                    message=decision.message,
                    provenance_source_ids=provenance_source_ids,
                )
            )
        return tuple(events)

    @staticmethod
    def _extract_policy(
        strategy: StrategyRule | StrategyExpiryPolicy | S23PaperPositionState,
    ) -> StrategyExpiryPolicy:
        if isinstance(strategy, StrategyRule):
            return strategy.expiry_policy
        if isinstance(strategy, StrategyExpiryPolicy):
            return strategy
        return strategy.expiry_policy

    def _should_select_next_expiry_for_policy(
        self,
        policy: StrategyExpiryPolicy,
        session_date: date,
        *,
        current_expiry: date,
    ) -> bool:
        if session_date >= current_expiry:
            return True
        trading_days_until_expiry = self._calendar.trading_days_until(
            session_date,
            current_expiry,
        )
        return trading_days_until_expiry <= self._rollover_threshold(policy.rollover_policy)

    @staticmethod
    def _rollover_threshold(policy: RolloverPolicy) -> int:
        if policy is RolloverPolicy.T_MINUS_1:
            return 1
        return 2

    @staticmethod
    def _reason_code_for_event(
        event_type: S23PaperPositionStateEventType,
    ) -> str:
        mapping = {
            S23PaperPositionStateEventType.PAPER_EXPIRY_FORCE_CLOSE_REQUIRED: "expiry_force_close_required",
            S23PaperPositionStateEventType.PAPER_EXPIRY_FORCE_CLOSED: "expiry_force_closed",
            S23PaperPositionStateEventType.PAPER_NEXT_EXPIRY_REQUIRED: "next_expiry_required",
            S23PaperPositionStateEventType.PAPER_ROLLOVER_POLICY_APPLIED: "rollover_policy_applied",
        }
        return mapping[event_type]
