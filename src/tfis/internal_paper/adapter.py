from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from tfis.persistence import canonical_hash

from .coordinator import AccountCoordinatorError, margin_after_reservation, position_candidate_from_fill
from .models import (
    ClientOrder,
    DeterministicExecutionScenarioDefinition,
    InternalPaperAdapterResult,
    InternalPaperFill,
    InternalPaperExecutionScenario,
    InternalPaperOrderEvent,
    InternalPaperOrderEventType,
    InternalPaperOrderState,
    SimulatedPaperAccountSnapshot,
)


class DeterministicInternalPaperAdapter:
    def execute(
        self,
        client_order: ClientOrder,
        scenario: DeterministicExecutionScenarioDefinition,
        account_snapshot: SimulatedPaperAccountSnapshot,
        *,
        starting_state: InternalPaperOrderState = InternalPaperOrderState.READY_FOR_INTERNAL_PAPER,
    ) -> InternalPaperAdapterResult:
        if client_order.broker_account_id != account_snapshot.broker_account_id:
            raise AccountCoordinatorError("Client order account does not match paper account.")
        events: list[InternalPaperOrderEvent] = []
        fills: list[InternalPaperFill] = []
        current_state = starting_state
        cumulative = 0
        snapshot = account_snapshot
        scenario_type = scenario.scenario
        if scenario_type in {InternalPaperExecutionScenario.REJECTED_INSUFFICIENT_PAPER_MARGIN, InternalPaperExecutionScenario.REJECTED_INVALID_PRICE}:
            event = self._event(client_order, scenario, 2, current_state, InternalPaperOrderState.REJECTED_INTERNAL, InternalPaperOrderEventType.INTERNAL_SUBMISSION_REJECTED, 0, 0, None, scenario.rejection_reason or scenario_type.value)
            events.append(event)
            return InternalPaperAdapterResult(client_order, event.new_state, tuple(events), tuple(fills), (), snapshot)
        if scenario_type is InternalPaperExecutionScenario.NO_FILL_BEFORE_EXPIRY:
            ack = self._event(client_order, scenario, 2, current_state, InternalPaperOrderState.ACKNOWLEDGED_INTERNAL, InternalPaperOrderEventType.INTERNAL_SUBMISSION_ACCEPTED, 0, 0, None, "Internal order acknowledged.")
            exp = self._event(client_order, scenario, 3, ack.new_state, InternalPaperOrderState.EXPIRED_INTERNAL, InternalPaperOrderEventType.INTERNAL_EXPIRED, 0, 0, None, "No fill before expiry.")
            events.extend([ack, exp])
            return InternalPaperAdapterResult(client_order, exp.new_state, tuple(events), tuple(fills), (), snapshot)
        if scenario_type is InternalPaperExecutionScenario.CANCEL_BEFORE_FILL:
            ack = self._event(client_order, scenario, 2, current_state, InternalPaperOrderState.ACKNOWLEDGED_INTERNAL, InternalPaperOrderEventType.INTERNAL_SUBMISSION_ACCEPTED, 0, 0, None, "Internal order acknowledged.")
            cancel_req = self._event(client_order, scenario, 3, ack.new_state, InternalPaperOrderState.CANCEL_PENDING_INTERNAL, InternalPaperOrderEventType.INTERNAL_CANCEL_REQUESTED, 0, 0, None, scenario.cancel_reason or "Cancel requested.")
            cancelled = self._event(client_order, scenario, 4, cancel_req.new_state, InternalPaperOrderState.CANCELLED_INTERNAL, InternalPaperOrderEventType.INTERNAL_CANCELLED, 0, 0, None, "Internal cancel acknowledged.")
            events.extend([ack, cancel_req, cancelled])
            return InternalPaperAdapterResult(client_order, cancelled.new_state, tuple(events), tuple(fills), (), snapshot)
        ack = self._event(client_order, scenario, 2, current_state, InternalPaperOrderState.ACKNOWLEDGED_INTERNAL, InternalPaperOrderEventType.INTERNAL_SUBMISSION_ACCEPTED, 0, 0, None, "Internal order acknowledged.")
        events.append(ack)
        current_state = ack.new_state
        if scenario_type in {InternalPaperExecutionScenario.IMMEDIATE_FULL_FILL, InternalPaperExecutionScenario.ACK_THEN_FULL_FILL, InternalPaperExecutionScenario.DUPLICATE_EVENT_REPLAY}:
            qty = client_order.quantity
            fill_price = self._fill_price(client_order, scenario)
            fill = self._fill(client_order, scenario, qty, fill_price, suffix="full")
            fills.append(fill)
            full = self._event(client_order, scenario, 3, current_state, InternalPaperOrderState.FILLED_INTERNAL, InternalPaperOrderEventType.INTERNAL_FULL_FILL, qty, qty, fill_price, "Internal full fill.")
            events.append(full)
            snapshot = _release_after_terminal(snapshot, client_order.quantity)
        elif scenario_type is InternalPaperExecutionScenario.PARTIAL_THEN_FULL_FILL:
            first_qty = scenario.fill_quantity or max(1, client_order.quantity // 2)
            fill_price = self._fill_price(client_order, scenario)
            fills.append(self._fill(client_order, scenario, first_qty, fill_price, suffix="partial"))
            partial = self._event(client_order, scenario, 3, current_state, InternalPaperOrderState.PARTIALLY_FILLED_INTERNAL, InternalPaperOrderEventType.INTERNAL_PARTIAL_FILL, first_qty, first_qty, fill_price, "Internal partial fill.")
            remaining = client_order.quantity - first_qty
            fills.append(self._fill(client_order, scenario, remaining, fill_price, suffix="final"))
            full = self._event(client_order, scenario, 4, partial.new_state, InternalPaperOrderState.FILLED_INTERNAL, InternalPaperOrderEventType.INTERNAL_FULL_FILL, remaining, client_order.quantity, fill_price, "Internal final fill.")
            events.extend([partial, full])
            snapshot = _release_after_terminal(snapshot, client_order.quantity)
        elif scenario_type is InternalPaperExecutionScenario.PARTIAL_REMAINS_OPEN:
            qty = scenario.fill_quantity or max(1, client_order.quantity // 2)
            fill_price = self._fill_price(client_order, scenario)
            fills.append(self._fill(client_order, scenario, qty, fill_price, suffix="partial-open"))
            partial = self._event(client_order, scenario, 3, current_state, InternalPaperOrderState.PARTIALLY_FILLED_INTERNAL, InternalPaperOrderEventType.INTERNAL_PARTIAL_FILL, qty, qty, fill_price, "Internal partial fill remains open.")
            events.append(partial)
        elif scenario_type is InternalPaperExecutionScenario.FILL_BEFORE_CANCEL_CONFIRMATION:
            fill_price = self._fill_price(client_order, scenario)
            cancel_req = self._event(client_order, scenario, 3, current_state, InternalPaperOrderState.CANCEL_PENDING_INTERNAL, InternalPaperOrderEventType.INTERNAL_CANCEL_REQUESTED, 0, 0, None, scenario.cancel_reason or "Cancel requested.")
            fills.append(self._fill(client_order, scenario, client_order.quantity, fill_price, suffix="race"))
            full = self._event(client_order, scenario, 4, cancel_req.new_state, InternalPaperOrderState.FILLED_INTERNAL, InternalPaperOrderEventType.INTERNAL_FULL_FILL, client_order.quantity, client_order.quantity, fill_price, "Internal fill before cancel confirmation.")
            events.extend([cancel_req, full])
            snapshot = _release_after_terminal(snapshot, client_order.quantity)
        final_state = events[-1].new_state
        candidates = tuple(position_candidate_from_fill(fill.internal_fill_id, fill.position_cycle_id, fill.fill_quantity, fill.fill_price) for fill in fills)
        return InternalPaperAdapterResult(client_order, final_state, tuple(events), tuple(fills), candidates, snapshot)

    def reserve_margin(self, client_order: ClientOrder, account_snapshot: SimulatedPaperAccountSnapshot) -> SimulatedPaperAccountSnapshot:
        return margin_after_reservation(account_snapshot, client_order.quantity)

    def _fill_price(self, client_order: ClientOrder, scenario: DeterministicExecutionScenarioDefinition) -> Decimal:
        if scenario.fill_price is not None:
            return scenario.fill_price
        evidence = scenario.market_evidence
        if client_order.order_type == "MARKET":
            price = evidence.ask if client_order.side == "BUY" else evidence.bid
        elif client_order.order_type == "LIMIT":
            if client_order.limit_price is None:
                raise AccountCoordinatorError("Limit order requires limit price.")
            crossed = evidence.low is not None and evidence.high is not None and evidence.low <= client_order.limit_price <= evidence.high
            if not crossed:
                raise AccountCoordinatorError("Limit price was not satisfied by deterministic fixture.")
            price = client_order.limit_price
        elif client_order.order_type in {"SL", "STOP_LIMIT"}:
            if client_order.trigger_price is None:
                raise AccountCoordinatorError("Stop order requires trigger price.")
            price = client_order.trigger_price
        else:
            price = client_order.limit_price or client_order.trigger_price or evidence.ltp
        if price is None:
            raise AccountCoordinatorError("Executable-side evidence missing.")
        if price <= 0:
            raise AccountCoordinatorError("Invalid fill price.")
        return price

    def _event(self, client_order: ClientOrder, scenario: DeterministicExecutionScenarioDefinition, sequence: int, previous: InternalPaperOrderState | None, new: InternalPaperOrderState, event_type: InternalPaperOrderEventType, quantity_delta: int, cumulative: int, fill_price: Decimal | None, reason: str) -> InternalPaperOrderEvent:
        return InternalPaperOrderEvent(
            event_id="event:" + canonical_hash({"client_order_id": client_order.client_order_id, "sequence": sequence, "scenario_id": scenario.scenario_id, "event_type": event_type.value})[:24],
            client_order_id=client_order.client_order_id,
            broker_account_id=client_order.broker_account_id,
            sequence=sequence,
            previous_state=previous,
            new_state=new,
            event_type=event_type,
            event_timestamp=scenario.event_time,
            simulated_exchange_timestamp=scenario.event_time,
            quantity_delta=quantity_delta,
            cumulative_filled_quantity=cumulative,
            fill_price=fill_price,
            reason=reason,
            scenario_id=scenario.scenario_id,
            provenance={"adapter": type(self).__name__, "scenario_hash": scenario.scenario_hash},
        )

    def _fill(self, client_order: ClientOrder, scenario: DeterministicExecutionScenarioDefinition, quantity: int, price: Decimal, *, suffix: str) -> InternalPaperFill:
        return InternalPaperFill(
            internal_fill_id="internal-fill:" + canonical_hash({"client_order_id": client_order.client_order_id, "scenario_id": scenario.scenario_id, "suffix": suffix})[:24],
            client_order_id=client_order.client_order_id,
            broker_account_id=client_order.broker_account_id,
            strategy_instance_id=client_order.strategy_instance_id,
            position_cycle_id=client_order.position_cycle_id,
            contract=client_order.normalized_contract,
            side=client_order.side,
            fill_quantity=quantity,
            fill_price=price,
            simulated_exchange_timestamp=scenario.event_time,
            recorded_timestamp=scenario.event_time,
            scenario_id=scenario.scenario_id,
            provenance={"adapter": type(self).__name__, "scenario_hash": scenario.scenario_hash},
        )


def _release_after_terminal(snapshot: SimulatedPaperAccountSnapshot, quantity: int) -> SimulatedPaperAccountSnapshot:
    amount = snapshot.margin_per_quantity * Decimal(quantity)
    return replace(
        snapshot,
        reserved_margin=max(Decimal("0"), snapshot.reserved_margin - amount),
        released_margin=snapshot.released_margin + amount,
        available_paper_margin=snapshot.available_paper_margin + amount,
        active_order_reservation=max(Decimal("0"), snapshot.active_order_reservation - amount),
        active_order_count=max(0, snapshot.active_order_count - 1),
    )
