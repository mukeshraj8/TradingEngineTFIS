from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from tfis.execution_intent import IntentValidationDecision, RiskValidationResult
from tfis.execution_intent.models import ExecutionIntent
from tfis.persistence import canonical_hash

from .models import (
    AccountCoordinatorEnvironment,
    AccountCoordinatorIdentity,
    ClientOrder,
    DeterministicExecutionScenarioDefinition,
    InternalPaperAdapterResult,
    InternalPaperAuthorityGrant,
    InternalPaperExecutionScenario,
    InternalPaperOrderEvent,
    InternalPaperOrderEventType,
    InternalPaperOrderState,
    PositionCycleUpdateCandidate,
    SimulatedPaperAccountSnapshot,
)


class AccountCoordinatorError(RuntimeError):
    pass


class AccountCoordinator:
    def __init__(self, identity: AccountCoordinatorIdentity, account_snapshot: SimulatedPaperAccountSnapshot) -> None:
        if identity.environment is not AccountCoordinatorEnvironment.INTERNAL_PAPER_ONLY:
            raise AccountCoordinatorError("Only INTERNAL_PAPER_ONLY coordinators are active in Phase 4F.")
        if identity.broker_account_id != account_snapshot.broker_account_id:
            raise AccountCoordinatorError("Account snapshot does not match coordinator account.")
        self.identity = identity
        self.account_snapshot = account_snapshot
        self._orders: dict[str, ClientOrder] = {}
        self._intent_to_order: dict[str, str] = {}
        self._states: dict[str, InternalPaperOrderState] = {}
        self._event_hashes: dict[str, str] = {}

    @classmethod
    def build_identity(
        cls,
        *,
        broker_account_id: str,
        trading_session_id: str,
        environment: AccountCoordinatorEnvironment = AccountCoordinatorEnvironment.INTERNAL_PAPER_ONLY,
        logical_account_reference: str = "INTERNAL_PAPER_ACCOUNT",
        configuration_hash: str = "phase4f-account-config",
        coordinator_version: str = "phase4f.account_coordinator.v1",
    ) -> AccountCoordinatorIdentity:
        account_coordinator_id = "acct-coord:" + canonical_hash(
            {
                "broker_account_id": broker_account_id,
                "trading_session_id": trading_session_id,
                "environment": environment.value,
                "configuration_hash": configuration_hash,
            }
        )[:24]
        return AccountCoordinatorIdentity(
            account_coordinator_id=account_coordinator_id,
            broker_account_id=broker_account_id,
            logical_account_reference=logical_account_reference,
            trading_session_id=trading_session_id,
            environment=environment,
            configuration_hash=configuration_hash,
            coordinator_version=coordinator_version,
        )

    def create_client_order(
        self,
        *,
        intent: ExecutionIntent,
        validation_result: RiskValidationResult,
        grant: InternalPaperAuthorityGrant | None,
        evaluated_at: datetime,
        existing_committed_intent_reservation: bool = True,
    ) -> ClientOrder:
        self._validate_creation_gate(intent, validation_result, grant, evaluated_at, existing_committed_intent_reservation)
        if intent.execution_intent_id in self._intent_to_order:
            return self._orders[self._intent_to_order[intent.execution_intent_id]]
        payload = {
            "account_coordinator_id": self.identity.account_coordinator_id,
            "execution_intent_id": intent.execution_intent_id,
            "broker_account_id": intent.broker_account_id,
            "purpose": intent.action.purpose.value,
            "protection_generation": intent.action.protection_generation,
            "intent_hash": intent.intent_hash,
        }
        client_order_id = "client-order:" + canonical_hash(payload)[:24]
        client_order = ClientOrder(
            client_order_id=client_order_id,
            execution_intent_id=intent.execution_intent_id,
            account_coordinator_id=self.identity.account_coordinator_id,
            broker_account_id=intent.broker_account_id,
            strategy_instance_id=intent.strategy_instance_id,
            trading_session_id=intent.trading_session_id,
            position_cycle_id=intent.position_cycle_id,
            idempotency_key="client-order:" + canonical_hash(payload),
            normalized_contract=intent.instrument.contract,
            side=intent.action.side,
            quantity=intent.action.requested_quantity,
            order_purpose=intent.action.purpose.value,
            order_type=intent.action.order_type,
            limit_price=intent.action.limit_price,
            trigger_price=intent.action.trigger_price,
            time_in_force=intent.action.time_in_force,
            authorized_time=intent.action.authorized_not_before,
            protection_generation=intent.action.protection_generation,
            source_intent_hash=intent.intent_hash,
        )
        self._orders[client_order_id] = client_order
        self._intent_to_order[intent.execution_intent_id] = client_order_id
        self._states[client_order_id] = InternalPaperOrderState.CREATED
        return client_order

    def record_event(self, event: InternalPaperOrderEvent) -> InternalPaperOrderEvent:
        existing = self._event_hashes.get(event.event_id)
        if existing is not None:
            if existing == event.event_hash:
                return event
            raise AccountCoordinatorError(f"Conflicting internal paper event: {event.event_id}")
        current = self._states.get(event.client_order_id)
        if current != event.previous_state:
            raise AccountCoordinatorError("Invalid internal paper order transition.")
        order = self._orders[event.client_order_id]
        if event.cumulative_filled_quantity > order.quantity:
            raise AccountCoordinatorError("Internal fill exceeds requested quantity.")
        self._event_hashes[event.event_id] = event.event_hash
        self._states[event.client_order_id] = event.new_state
        return event

    def apply_result(self, result: InternalPaperAdapterResult) -> InternalPaperAdapterResult:
        for event in result.events:
            self.record_event(event)
        self.account_snapshot = result.account_snapshot
        return result

    def _validate_creation_gate(
        self,
        intent: ExecutionIntent,
        validation_result: RiskValidationResult,
        grant: InternalPaperAuthorityGrant | None,
        evaluated_at: datetime,
        existing_committed_intent_reservation: bool,
    ) -> None:
        if validation_result.decision is not IntentValidationDecision.VALIDATED_NOT_SUBMITTABLE:
            raise AccountCoordinatorError("Only VALIDATED_NOT_SUBMITTABLE intents can create internal paper client orders.")
        if validation_result.intent_hash != intent.intent_hash:
            raise AccountCoordinatorError("Intent hash mismatch.")
        if grant is None:
            raise AccountCoordinatorError("Internal paper authority grant is required.")
        if grant.authority.value != "INTERNAL_PAPER_ORDER_SIMULATION_ONLY":
            raise AccountCoordinatorError("Unsupported internal paper authority.")
        if grant.broker_account_id != intent.broker_account_id or intent.broker_account_id != self.identity.broker_account_id:
            raise AccountCoordinatorError("Account mismatch.")
        if grant.strategy_instance_id != intent.strategy_instance_id:
            raise AccountCoordinatorError("Strategy instance mismatch.")
        if grant.trading_session_id != intent.trading_session_id or intent.trading_session_id != self.identity.trading_session_id:
            raise AccountCoordinatorError("Trading session mismatch.")
        if intent.action.purpose.value not in grant.allowed_intent_purposes:
            raise AccountCoordinatorError("Intent purpose is not granted for internal paper.")
        if intent.action.requested_quantity > grant.maximum_quantity:
            raise AccountCoordinatorError("Intent quantity exceeds grant.")
        if evaluated_at < intent.action.authorized_not_before:
            raise AccountCoordinatorError("Authorized time has not been reached.")
        if intent.action.authorized_not_after is not None and evaluated_at > intent.action.authorized_not_after:
            raise AccountCoordinatorError("Intent has expired.")
        if not self.account_snapshot.account_enabled or self.account_snapshot.account_blocked:
            raise AccountCoordinatorError("Account is disabled or blocked.")
        if self.account_snapshot.active_order_count >= self.account_snapshot.max_active_order_count:
            raise AccountCoordinatorError("Active order count limit reached.")
        if not existing_committed_intent_reservation:
            raise AccountCoordinatorError("Committed intent reservation is required.")


def create_creation_event(client_order: ClientOrder, timestamp: datetime, scenario_id: str = "CLIENT_ORDER_CREATION") -> InternalPaperOrderEvent:
    return InternalPaperOrderEvent(
        event_id="event:" + canonical_hash({"client_order_id": client_order.client_order_id, "type": "CLIENT_ORDER_CREATED"})[:24],
        client_order_id=client_order.client_order_id,
        broker_account_id=client_order.broker_account_id,
        sequence=1,
        previous_state=InternalPaperOrderState.CREATED,
        new_state=InternalPaperOrderState.READY_FOR_INTERNAL_PAPER,
        event_type=InternalPaperOrderEventType.CLIENT_ORDER_CREATED,
        event_timestamp=timestamp,
        simulated_exchange_timestamp=timestamp,
        quantity_delta=0,
        cumulative_filled_quantity=0,
        fill_price=None,
        reason="Client order created for internal paper simulation.",
        scenario_id=scenario_id,
        provenance={"source": "AccountCoordinator"},
    )


def margin_after_reservation(snapshot: SimulatedPaperAccountSnapshot, quantity: int) -> SimulatedPaperAccountSnapshot:
    reservation = snapshot.margin_per_quantity * Decimal(quantity)
    available = snapshot.available_paper_margin - reservation
    if available < 0:
        raise AccountCoordinatorError("Insufficient internal paper margin.")
    return replace(
        snapshot,
        reserved_margin=snapshot.reserved_margin + reservation,
        available_paper_margin=available,
        active_order_reservation=snapshot.active_order_reservation + reservation,
        active_order_count=snapshot.active_order_count + 1,
    )


def position_candidate_from_fill(fill_id: str, position_cycle_id: str | None, quantity_delta: int, fill_price: Decimal) -> PositionCycleUpdateCandidate:
    return PositionCycleUpdateCandidate(
        candidate_id="pc-update-candidate:" + canonical_hash({"fill_id": fill_id})[:24],
        source_fill_id=fill_id,
        position_cycle_id=position_cycle_id,
        quantity_delta=quantity_delta,
        fill_price=fill_price,
        suggested_state_impact="INTERNAL_PAPER_FILL_OBSERVED_NO_POSITION_MUTATION",
    )
