from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterable, Mapping

from tfis.execution_intent.models import ExecutionIntent, RiskValidationResult
from tfis.persistence import canonical_hash

from .adapter import DeterministicInternalPaperAdapter
from .coordinator import AccountCoordinator, create_creation_event, release_margin_after_resolution
from .models import (
    DeterministicExecutionScenarioDefinition,
    InternalPaperAdapterResult,
    InternalPaperAuthorityGrant,
    InternalPaperOrderState,
    SimulatedPaperAccountSnapshot,
)


WARNING_DECISION = "ORDER_NOT_SUBMITTED_INSUFFICIENT_MARGIN"
HALT_DECISION = "ACCOUNT_HALT_BLOCKED"
PROCESSED_DECISION = "PROCESSED_INTERNAL_PAPER"
IDEMPOTENT_DUPLICATE_DECISION = "DUPLICATE_IDEMPOTENT_SKIPPED"
CONFLICTING_DUPLICATE_DECISION = "DUPLICATE_CONFLICT_FAIL_CLOSED"

_RESERVATION_RELEASE_STATES = frozenset(
    {
        InternalPaperOrderState.REJECTED_INTERNAL,
        InternalPaperOrderState.CANCELLED_INTERNAL,
        InternalPaperOrderState.EXPIRED_INTERNAL,
        InternalPaperOrderState.TERMINAL_ERROR,
        InternalPaperOrderState.UNKNOWN_INTERNAL_REVIEW_REQUIRED,
    }
)


@dataclass(frozen=True, slots=True)
class SequentialAccountIntentCandidate:
    intent: ExecutionIntent
    validation_result: RiskValidationResult
    grant: InternalPaperAuthorityGrant
    scenario: DeterministicExecutionScenarioDefinition
    qualification_timestamp: datetime
    intent_creation_sequence: int

    def ordering_key(self) -> tuple[datetime, int, str]:
        return (
            self.qualification_timestamp,
            self.intent_creation_sequence,
            self.intent.strategy_instance_id,
        )


@dataclass(frozen=True, slots=True)
class SequentialAccountWarning:
    severity: str
    account: str
    strategy_instance_id: str
    instrument: str
    execution_intent_id: str
    required_margin: Decimal
    available_margin: Decimal
    effective_available_margin: Decimal
    shortfall: Decimal
    reason: str
    operator_guidance: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "account": self.account,
            "strategy_instance_id": self.strategy_instance_id,
            "instrument": self.instrument,
            "execution_intent_id": self.execution_intent_id,
            "required_margin": str(self.required_margin),
            "available_margin": str(self.available_margin),
            "effective_available_margin": str(self.effective_available_margin),
            "shortfall": str(self.shortfall),
            "reason": self.reason,
            "operator_guidance": self.operator_guidance,
        }


@dataclass(frozen=True, slots=True)
class SequentialAccountIntentOutcome:
    execution_intent_id: str
    strategy_instance_id: str
    broker_account_id: str
    instrument: str
    queue_position: int
    qualification_timestamp: datetime
    intent_creation_sequence: int
    decision: str
    required_margin: Decimal
    available_margin: Decimal
    effective_available_margin: Decimal
    shortfall: Decimal | None
    reservation_created: bool
    reservation_released: bool
    reservation_reconciled: bool
    client_order_id: str | None = None
    final_state: str | None = None
    result_hash: str | None = None
    warning: SequentialAccountWarning | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_intent_id": self.execution_intent_id,
            "strategy_instance_id": self.strategy_instance_id,
            "broker_account_id": self.broker_account_id,
            "instrument": self.instrument,
            "queue_position": self.queue_position,
            "qualification_timestamp": self.qualification_timestamp.isoformat(),
            "intent_creation_sequence": self.intent_creation_sequence,
            "decision": self.decision,
            "required_margin": str(self.required_margin),
            "available_margin": str(self.available_margin),
            "effective_available_margin": str(self.effective_available_margin),
            "shortfall": None if self.shortfall is None else str(self.shortfall),
            "reservation_created": self.reservation_created,
            "reservation_released": self.reservation_released,
            "reservation_reconciled": self.reservation_reconciled,
            "client_order_id": self.client_order_id,
            "final_state": self.final_state,
            "result_hash": self.result_hash,
            "warning": None if self.warning is None else self.warning.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SequentialAccountProcessingResult:
    broker_account_id: str
    ordered_intent_ids: tuple[str, ...]
    outcomes: tuple[SequentialAccountIntentOutcome, ...]
    final_account_snapshot: SimulatedPaperAccountSnapshot
    external_broker_order_authority: str = "NONE"
    lifecycle_protection_preserved: bool = True
    result_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "result_hash",
            canonical_hash(
                {
                    "broker_account_id": self.broker_account_id,
                    "ordered_intent_ids": list(self.ordered_intent_ids),
                    "outcomes": [item.to_dict() for item in self.outcomes],
                    "final_account_snapshot": self.final_account_snapshot.to_dict(),
                    "external_broker_order_authority": self.external_broker_order_authority,
                    "lifecycle_protection_preserved": self.lifecycle_protection_preserved,
                }
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "broker_account_id": self.broker_account_id,
            "ordered_intent_ids": list(self.ordered_intent_ids),
            "outcomes": [item.to_dict() for item in self.outcomes],
            "final_account_snapshot": self.final_account_snapshot.to_dict(),
            "external_broker_order_authority": self.external_broker_order_authority,
            "lifecycle_protection_preserved": self.lifecycle_protection_preserved,
            "result_hash": self.result_hash,
        }


class SequentialAccountIntentProcessor:
    def __init__(self, *, adapter: DeterministicInternalPaperAdapter | None = None) -> None:
        self.adapter = adapter or DeterministicInternalPaperAdapter()

    def process(
        self,
        candidates: Iterable[SequentialAccountIntentCandidate],
        *,
        account_snapshots: Mapping[str, SimulatedPaperAccountSnapshot],
    ) -> dict[str, SequentialAccountProcessingResult]:
        grouped: dict[str, list[SequentialAccountIntentCandidate]] = {}
        for candidate in candidates:
            grouped.setdefault(candidate.intent.broker_account_id, []).append(candidate)
        results: dict[str, SequentialAccountProcessingResult] = {}
        for broker_account_id, items in grouped.items():
            snapshot = account_snapshots[broker_account_id]
            ordered = sorted(items, key=lambda item: item.ordering_key())
            coordinator = AccountCoordinator(
                AccountCoordinator.build_identity(
                    broker_account_id=broker_account_id,
                    trading_session_id=ordered[0].intent.trading_session_id,
                ),
                snapshot,
            )
            outcomes: list[SequentialAccountIntentOutcome] = []
            seen_intents: dict[str, str] = {}
            for position, candidate in enumerate(ordered, start=1):
                outcome = self._process_candidate(
                    coordinator=coordinator,
                    candidate=candidate,
                    queue_position=position,
                    seen_intents=seen_intents,
                )
                outcomes.append(outcome)
            results[broker_account_id] = SequentialAccountProcessingResult(
                broker_account_id=broker_account_id,
                ordered_intent_ids=tuple(item.intent.execution_intent_id for item in ordered),
                outcomes=tuple(outcomes),
                final_account_snapshot=coordinator.account_snapshot,
            )
        return results

    def _process_candidate(
        self,
        *,
        coordinator: AccountCoordinator,
        candidate: SequentialAccountIntentCandidate,
        queue_position: int,
        seen_intents: dict[str, str],
    ) -> SequentialAccountIntentOutcome:
        intent = candidate.intent
        snapshot = coordinator.account_snapshot
        required_margin = snapshot.margin_per_quantity * Decimal(intent.action.requested_quantity)
        available_margin = snapshot.available_paper_margin + snapshot.active_order_reservation
        effective_available_margin = available_margin - snapshot.active_order_reservation

        prior_hash = seen_intents.get(intent.execution_intent_id)
        if prior_hash is not None:
            if prior_hash == intent.intent_hash:
                return SequentialAccountIntentOutcome(
                    execution_intent_id=intent.execution_intent_id,
                    strategy_instance_id=intent.strategy_instance_id,
                    broker_account_id=intent.broker_account_id,
                    instrument=intent.instrument.contract,
                    queue_position=queue_position,
                    qualification_timestamp=candidate.qualification_timestamp,
                    intent_creation_sequence=candidate.intent_creation_sequence,
                    decision=IDEMPOTENT_DUPLICATE_DECISION,
                    required_margin=required_margin,
                    available_margin=available_margin,
                    effective_available_margin=effective_available_margin,
                    shortfall=None,
                    reservation_created=False,
                    reservation_released=False,
                    reservation_reconciled=False,
                )
            return SequentialAccountIntentOutcome(
                execution_intent_id=intent.execution_intent_id,
                strategy_instance_id=intent.strategy_instance_id,
                broker_account_id=intent.broker_account_id,
                instrument=intent.instrument.contract,
                queue_position=queue_position,
                qualification_timestamp=candidate.qualification_timestamp,
                intent_creation_sequence=candidate.intent_creation_sequence,
                decision=CONFLICTING_DUPLICATE_DECISION,
                required_margin=required_margin,
                available_margin=available_margin,
                effective_available_margin=effective_available_margin,
                shortfall=None,
                reservation_created=False,
                reservation_released=False,
                reservation_reconciled=False,
            )

        seen_intents[intent.execution_intent_id] = intent.intent_hash

        if not snapshot.account_enabled or snapshot.account_blocked:
            warning = SequentialAccountWarning(
                severity="WARNING",
                account=intent.broker_account_id,
                strategy_instance_id=intent.strategy_instance_id,
                instrument=intent.instrument.contract,
                execution_intent_id=intent.execution_intent_id,
                required_margin=required_margin,
                available_margin=available_margin,
                effective_available_margin=effective_available_margin,
                shortfall=Decimal("0"),
                reason="ACCOUNT_HALT_ACTIVE",
                operator_guidance="Do not submit new intents for this account until the halt is removed. Existing lifecycle and protection work must remain active.",
            )
            return SequentialAccountIntentOutcome(
                execution_intent_id=intent.execution_intent_id,
                strategy_instance_id=intent.strategy_instance_id,
                broker_account_id=intent.broker_account_id,
                instrument=intent.instrument.contract,
                queue_position=queue_position,
                qualification_timestamp=candidate.qualification_timestamp,
                intent_creation_sequence=candidate.intent_creation_sequence,
                decision=HALT_DECISION,
                required_margin=required_margin,
                available_margin=available_margin,
                effective_available_margin=effective_available_margin,
                shortfall=Decimal("0"),
                reservation_created=False,
                reservation_released=False,
                reservation_reconciled=False,
                warning=warning,
            )

        if effective_available_margin < required_margin:
            shortfall = required_margin - effective_available_margin
            warning = SequentialAccountWarning(
                severity="WARNING",
                account=intent.broker_account_id,
                strategy_instance_id=intent.strategy_instance_id,
                instrument=intent.instrument.contract,
                execution_intent_id=intent.execution_intent_id,
                required_margin=required_margin,
                available_margin=available_margin,
                effective_available_margin=effective_available_margin,
                shortfall=shortfall,
                reason="INSUFFICIENT_MARGIN",
                operator_guidance="Do not submit this intent. Review effective available margin, active reservations, and account exposure before retrying in a future cycle.",
            )
            return SequentialAccountIntentOutcome(
                execution_intent_id=intent.execution_intent_id,
                strategy_instance_id=intent.strategy_instance_id,
                broker_account_id=intent.broker_account_id,
                instrument=intent.instrument.contract,
                queue_position=queue_position,
                qualification_timestamp=candidate.qualification_timestamp,
                intent_creation_sequence=candidate.intent_creation_sequence,
                decision=WARNING_DECISION,
                required_margin=required_margin,
                available_margin=available_margin,
                effective_available_margin=effective_available_margin,
                shortfall=shortfall,
                reservation_created=False,
                reservation_released=False,
                reservation_reconciled=False,
                warning=warning,
            )

        client_order = coordinator.create_client_order(
            intent=intent,
            validation_result=candidate.validation_result,
            grant=candidate.grant,
            evaluated_at=max(candidate.qualification_timestamp, intent.action.authorized_not_before),
        )
        reserved_snapshot = self.adapter.reserve_margin(client_order, coordinator.account_snapshot)
        result = self.adapter.execute(client_order, candidate.scenario, reserved_snapshot)
        result = replace(result, events=(create_creation_event(client_order, intent.action.authorized_not_before), *result.events))
        reconciled_result = self._reconcile_result(result, quantity=client_order.quantity)
        coordinator.apply_result(reconciled_result)
        return SequentialAccountIntentOutcome(
            execution_intent_id=intent.execution_intent_id,
            strategy_instance_id=intent.strategy_instance_id,
            broker_account_id=intent.broker_account_id,
            instrument=intent.instrument.contract,
            queue_position=queue_position,
            qualification_timestamp=candidate.qualification_timestamp,
            intent_creation_sequence=candidate.intent_creation_sequence,
            decision=PROCESSED_DECISION,
            required_margin=required_margin,
            available_margin=available_margin,
            effective_available_margin=effective_available_margin,
            shortfall=None,
            reservation_created=True,
            reservation_released=reconciled_result.final_state in _RESERVATION_RELEASE_STATES
            or reconciled_result.final_state is InternalPaperOrderState.FILLED_INTERNAL,
            reservation_reconciled=True,
            client_order_id=client_order.client_order_id,
            final_state=reconciled_result.final_state.value,
            result_hash=reconciled_result.result_hash,
        )

    def _reconcile_result(
        self,
        result: InternalPaperAdapterResult,
        *,
        quantity: int,
    ) -> InternalPaperAdapterResult:
        if result.final_state not in _RESERVATION_RELEASE_STATES:
            return result
        released_snapshot = release_margin_after_resolution(result.account_snapshot, quantity)
        return replace(result, account_snapshot=released_snapshot)
