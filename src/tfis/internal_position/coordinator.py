from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from tfis.persistence import canonical_hash

from .models import (
    CarriedPositionRecoveryStatus,
    InternalPaperCarriedRecoveryAssessment,
    InternalPaperPositionConsistencyAssessment,
    InternalPaperPositionConsistencyStatus,
    InternalPaperPositionCycleIdentity,
    InternalPaperPositionCycleProjection,
    InternalPaperPositionEvent,
    InternalPaperPositionEventType,
    InternalPaperPositionState,
    InternalPaperPositionTransition,
    LifecycleRequirement,
    LifecycleRequirementType,
    PnlInputFacts,
    ProtectionModel,
    ProtectionOrderReference,
)


class PositionCycleCoordinatorError(RuntimeError):
    pass


TERMINAL_STATES = {
    InternalPaperPositionState.CLOSED,
    InternalPaperPositionState.CANCELLED_BEFORE_ENTRY,
    InternalPaperPositionState.TERMINAL_ERROR,
}
EXIT_PURPOSES = {"TARGET", "ORIGINAL_SL", "REVISED_SL", "EOD_EXIT", "RISK_EXIT", "OPERATOR_EXIT"}


class PositionCycleCoordinator:
    def build_identity(
        self,
        *,
        trading_session_id: str,
        originating_trading_date: date,
        broker_account_id: str,
        logical_account_reference: str,
        strategy_family_id: str,
        strategy_definition_id: str,
        strategy_version: str,
        strategy_instance_id: str,
        originating_execution_plan_id: str,
        originating_entry_execution_intent_id: str,
        normalized_contract: str,
        direction: str,
        side: str,
    ) -> InternalPaperPositionCycleIdentity:
        payload = {
            "trading_session_id": trading_session_id,
            "originating_trading_date": originating_trading_date.isoformat(),
            "broker_account_id": broker_account_id,
            "strategy_instance_id": strategy_instance_id,
            "originating_execution_plan_id": originating_execution_plan_id,
            "originating_entry_execution_intent_id": originating_entry_execution_intent_id,
            "normalized_contract": normalized_contract,
            "side": side,
        }
        return InternalPaperPositionCycleIdentity(
            position_cycle_id="ipc:" + canonical_hash(payload)[:24],
            trading_session_id=trading_session_id,
            originating_trading_date=originating_trading_date,
            broker_account_id=broker_account_id,
            logical_account_reference=logical_account_reference,
            strategy_family_id=strategy_family_id,
            strategy_definition_id=strategy_definition_id,
            strategy_version=strategy_version,
            strategy_instance_id=strategy_instance_id,
            originating_execution_plan_id=originating_execution_plan_id,
            originating_entry_execution_intent_id=originating_entry_execution_intent_id,
            normalized_contract=normalized_contract,
            direction=direction,
            side=side,
        )

    def reserve_cycle(self, identity: InternalPaperPositionCycleIdentity, *, timestamp: datetime) -> InternalPaperPositionTransition:
        projection = InternalPaperPositionCycleProjection.planned(identity)
        event = self._event(
            projection=projection,
            event_type=InternalPaperPositionEventType.POSITION_CYCLE_RESERVED,
            prior_state=None,
            new_state=InternalPaperPositionState.PLANNED,
            quantity_before=0,
            quantity_after=0,
            timestamp=timestamp,
        )
        return self._transition(projection, event)

    def cancel_before_entry(self, projection: InternalPaperPositionCycleProjection, *, timestamp: datetime, rule_ids: tuple[str, ...] = ()) -> InternalPaperPositionTransition:
        self._ensure_not_terminal(projection)
        if projection.confirmed_entry_quantity:
            raise PositionCycleCoordinatorError("Cannot cancel a cycle after entry fill.")
        updated = replace(
            projection,
            lifecycle_state=InternalPaperPositionState.CANCELLED_BEFORE_ENTRY,
            terminal_status="ENTRY_ORDER_TERMINAL_WITHOUT_FILL",
            projection_version=projection.projection_version + 1,
        )
        event = self._event(
            projection=updated,
            event_type=InternalPaperPositionEventType.POSITION_CLOSED,
            prior_state=projection.lifecycle_state,
            new_state=updated.lifecycle_state,
            quantity_before=0,
            quantity_after=0,
            timestamp=timestamp,
            rule_ids=rule_ids,
        )
        return self._transition(updated, event)

    def apply_entry_fill(
        self,
        projection: InternalPaperPositionCycleProjection | None,
        *,
        identity: InternalPaperPositionCycleIdentity,
        client_order: Mapping[str, Any],
        fill: Mapping[str, Any],
        requested_quantity: int,
        source_rule_ids: tuple[str, ...],
        lifecycle_prices: Mapping[str, Decimal | str | None] | None = None,
    ) -> InternalPaperPositionTransition:
        projection = projection or InternalPaperPositionCycleProjection.planned(identity)
        self._ensure_not_terminal(projection)
        self._validate_entry_fill(projection, client_order, fill, requested_quantity)
        fill_id = str(fill["internal_fill_id"])
        if fill_id in projection.entry_fill_ids:
            if str(fill.get("fill_hash")) in str(projection.to_dict()):
                event = self._event(
                    projection=projection,
                    event_type=InternalPaperPositionEventType.ENTRY_PARTIAL_FILL_APPLIED,
                    prior_state=projection.lifecycle_state,
                    new_state=projection.lifecycle_state,
                    quantity_before=projection.remaining_quantity,
                    quantity_after=projection.remaining_quantity,
                    timestamp=_dt(fill["recorded_timestamp"]),
                    source_fill_id=fill_id,
                    source_client_order_id=str(fill["client_order_id"]),
                    rule_ids=source_rule_ids,
                )
                return self._transition(projection, event)
            raise PositionCycleCoordinatorError("Conflicting duplicate entry fill.")
        fill_qty = int(fill["fill_quantity"])
        new_confirmed = projection.confirmed_entry_quantity + fill_qty
        if new_confirmed > requested_quantity:
            raise PositionCycleCoordinatorError("Entry fill exceeds requested quantity.")
        fill_price = _decimal(fill["fill_price"])
        average_entry = _weighted_average(
            prior_average=projection.average_entry_price,
            prior_quantity=projection.confirmed_entry_quantity,
            new_price=fill_price,
            new_quantity=fill_qty,
        )
        state = InternalPaperPositionState.OPEN_UNPROTECTED if new_confirmed == requested_quantity else InternalPaperPositionState.ENTRY_PARTIALLY_FILLED
        updated = replace(
            projection,
            lifecycle_state=state,
            confirmed_entry_quantity=new_confirmed,
            remaining_quantity=projection.remaining_quantity + fill_qty,
            average_entry_price=average_entry,
            entry_fill_ids=(*projection.entry_fill_ids, fill_id),
            multiplier=_decimal(client_order.get("multiplier", "1")),
            lot_size=int(client_order.get("lot_size", 1)),
            currency=str(client_order.get("currency", "INR")),
            projection_version=projection.projection_version + 1,
        )
        requirements = self._entry_requirements(updated, source_rule_ids, fill, lifecycle_prices or {}, full=new_confirmed == requested_quantity)
        event = self._event(
            projection=updated,
            event_type=InternalPaperPositionEventType.ENTRY_FULL_FILL_APPLIED if new_confirmed == requested_quantity else InternalPaperPositionEventType.ENTRY_PARTIAL_FILL_APPLIED,
            prior_state=projection.lifecycle_state,
            new_state=updated.lifecycle_state,
            quantity_before=projection.remaining_quantity,
            quantity_after=updated.remaining_quantity,
            timestamp=_dt(fill["recorded_timestamp"]),
            source_fill_id=fill_id,
            source_client_order_id=str(fill["client_order_id"]),
            rule_ids=source_rule_ids,
            price_evidence={"fill_price": fill_price},
        )
        return self._transition(updated, event, requirements)

    def link_protection_order(
        self,
        projection: InternalPaperPositionCycleProjection,
        *,
        requirement: LifecycleRequirement,
        client_order: Mapping[str, Any],
    ) -> InternalPaperPositionTransition:
        self._ensure_not_terminal(projection)
        if requirement.position_cycle_id != projection.identity.position_cycle_id:
            raise PositionCycleCoordinatorError("Requirement position does not match.")
        if requirement.quantity > projection.remaining_quantity:
            raise PositionCycleCoordinatorError("Protection cannot cover unfilled or exited quantity.")
        purpose = str(client_order["order_purpose"])
        generation = int(requirement.protection_generation or 1)
        if generation < projection.protection_generation:
            raise PositionCycleCoordinatorError("Stale protection generation.")
        reference = ProtectionOrderReference(
            position_cycle_id=projection.identity.position_cycle_id,
            order_purpose=purpose,
            protection_generation=generation,
            client_order_id=str(client_order["client_order_id"]),
            requirement_id=requirement.requirement_id,
            quantity=requirement.quantity,
        )
        updated = self._with_reference(projection, reference)
        event_type = InternalPaperPositionEventType.PROTECTION_RESIZE_REQUIRED if requirement.quantity != projection.remaining_quantity else InternalPaperPositionEventType.PROTECTION_ORDER_LINKED
        event = self._event(
            projection=updated,
            event_type=event_type,
            prior_state=projection.lifecycle_state,
            new_state=updated.lifecycle_state,
            quantity_before=projection.remaining_quantity,
            quantity_after=updated.remaining_quantity,
            timestamp=_dt(client_order["authorized_time"]),
            source_client_order_id=str(client_order["client_order_id"]),
            source_requirement_id=requirement.requirement_id,
            rule_ids=requirement.source_rule_ids,
        )
        return self._transition(updated, event)

    def apply_exit_fill(
        self,
        projection: InternalPaperPositionCycleProjection,
        *,
        client_order: Mapping[str, Any],
        fill: Mapping[str, Any],
        source_rule_ids: tuple[str, ...],
    ) -> InternalPaperPositionTransition:
        self._ensure_not_terminal(projection)
        purpose = str(client_order["order_purpose"])
        if purpose not in EXIT_PURPOSES:
            raise PositionCycleCoordinatorError("Exit fill must come from an exit ClientOrder.")
        self._validate_exit_fill(projection, client_order, fill)
        fill_id = str(fill["internal_fill_id"])
        if fill_id in projection.exit_fill_ids:
            return self._transition(
                projection,
                self._event(
                    projection=projection,
                    event_type=InternalPaperPositionEventType.PARTIAL_EXIT_APPLIED,
                    prior_state=projection.lifecycle_state,
                    new_state=projection.lifecycle_state,
                    quantity_before=projection.remaining_quantity,
                    quantity_after=projection.remaining_quantity,
                    timestamp=_dt(fill["recorded_timestamp"]),
                    source_fill_id=fill_id,
                    source_client_order_id=str(fill["client_order_id"]),
                    rule_ids=source_rule_ids,
                ),
            )
        fill_qty = int(fill["fill_quantity"])
        if fill_qty > projection.remaining_quantity:
            raise PositionCycleCoordinatorError("Exit fill exceeds remaining quantity.")
        average_exit = _weighted_average(
            prior_average=projection.average_exit_price,
            prior_quantity=projection.realized_quantity,
            new_price=_decimal(fill["fill_price"]),
            new_quantity=fill_qty,
        )
        remaining = projection.remaining_quantity - fill_qty
        realized = projection.realized_quantity + fill_qty
        state = InternalPaperPositionState.CLOSED if remaining == 0 else InternalPaperPositionState.PARTIALLY_EXITED
        active_target, active_original_sl, active_revised_sl, superseded = self._after_exit_protections(projection, purpose)
        updated = replace(
            projection,
            lifecycle_state=state,
            remaining_quantity=remaining,
            realized_quantity=realized,
            average_exit_price=average_exit,
            exit_fill_ids=(*projection.exit_fill_ids, fill_id),
            active_target=active_target,
            active_original_sl=active_original_sl,
            active_revised_sl=active_revised_sl,
            superseded_protections=superseded,
            filled_exit_order_id=str(client_order["client_order_id"]),
            terminal_status="CLOSED_BY_CONFIRMED_EXIT_FILL" if remaining == 0 else None,
            projection_version=projection.projection_version + 1,
        )
        event_type = {
            "TARGET": InternalPaperPositionEventType.TARGET_EXIT_APPLIED,
            "ORIGINAL_SL": InternalPaperPositionEventType.SL_EXIT_APPLIED,
            "REVISED_SL": InternalPaperPositionEventType.SL_EXIT_APPLIED,
            "EOD_EXIT": InternalPaperPositionEventType.EOD_EXIT_APPLIED,
        }.get(purpose, InternalPaperPositionEventType.PARTIAL_EXIT_APPLIED)
        event = self._event(
            projection=updated,
            event_type=event_type,
            prior_state=projection.lifecycle_state,
            new_state=updated.lifecycle_state,
            quantity_before=projection.remaining_quantity,
            quantity_after=remaining,
            timestamp=_dt(fill["recorded_timestamp"]),
            source_fill_id=fill_id,
            source_client_order_id=str(fill["client_order_id"]),
            rule_ids=source_rule_ids,
            price_evidence={"fill_price": _decimal(fill["fill_price"]), "purpose": purpose},
        )
        return self._transition(updated, event)

    def mark_exit_pending(self, projection: InternalPaperPositionCycleProjection, *, requirement: LifecycleRequirement) -> InternalPaperPositionTransition:
        if projection.remaining_quantity <= 0:
            raise PositionCycleCoordinatorError("Exit pending requires open quantity.")
        updated = replace(projection, lifecycle_state=InternalPaperPositionState.EXIT_PENDING, projection_version=projection.projection_version + 1)
        event = self._event(
            projection=updated,
            event_type=InternalPaperPositionEventType.PROTECTION_REQUIRED,
            prior_state=projection.lifecycle_state,
            new_state=updated.lifecycle_state,
            quantity_before=projection.remaining_quantity,
            quantity_after=projection.remaining_quantity,
            timestamp=requirement.created_at,
            source_requirement_id=requirement.requirement_id,
            rule_ids=requirement.source_rule_ids,
        )
        return self._transition(updated, event, (requirement,))

    def record_carry_forward(
        self,
        projection: InternalPaperPositionCycleProjection,
        *,
        next_trading_session_id: str,
        source_rule_id: str,
        observed_price: Decimal,
        original_sl: Decimal,
        timestamp: datetime,
    ) -> InternalPaperPositionTransition:
        self._ensure_not_terminal(projection)
        if projection.remaining_quantity <= 0:
            raise PositionCycleCoordinatorError("Cannot carry a zero-quantity position.")
        updated = replace(
            projection,
            lifecycle_state=InternalPaperPositionState.CARRIED_FORWARD,
            carry_forward_status="EOD_EQUAL_OR_BELOW_ORIGINAL_SL_CARRY_FORWARD",
            next_trading_session_id=next_trading_session_id,
            active_original_sl=None,
            active_revised_sl=None,
            projection_version=projection.projection_version + 1,
        )
        event = self._event(
            projection=updated,
            event_type=InternalPaperPositionEventType.CARRY_FORWARD_RECORDED,
            prior_state=projection.lifecycle_state,
            new_state=updated.lifecycle_state,
            quantity_before=projection.remaining_quantity,
            quantity_after=projection.remaining_quantity,
            timestamp=timestamp,
            rule_ids=(source_rule_id,),
            price_evidence={"observed_price": observed_price, "original_sl": original_sl, "equality_behavior": "CARRY_FORWARD"},
        )
        return self._transition(updated, event)

    def assess_recovery(
        self,
        projection: InternalPaperPositionCycleProjection,
        *,
        expected_account_id: str,
        expected_contract: str,
        expected_rule_version: str,
        observed_rule_version: str,
    ) -> InternalPaperCarriedRecoveryAssessment:
        findings: list[str] = []
        if projection.identity.broker_account_id != expected_account_id:
            findings.append("account mismatch")
        if projection.identity.normalized_contract != expected_contract:
            findings.append("contract mismatch")
        if expected_rule_version != observed_rule_version:
            findings.append("next-day rule/config version mismatch")
        if projection.remaining_quantity <= 0:
            findings.append("no remaining quantity")
        if projection.lifecycle_state is not InternalPaperPositionState.CARRIED_FORWARD:
            findings.append("position is not carried")
        status = CarriedPositionRecoveryStatus.CARRIED_POSITION_RECOVERABLE if not findings else CarriedPositionRecoveryStatus.CARRIED_POSITION_REVIEW_REQUIRED
        return InternalPaperCarriedRecoveryAssessment(
            assessment_id="carried-recovery:" + canonical_hash({"position_cycle_id": projection.identity.position_cycle_id, "findings": findings})[:24],
            status=status,
            position_cycle_id=projection.identity.position_cycle_id,
            findings=tuple(findings),
        )

    def assess_consistency(self, projection: InternalPaperPositionCycleProjection, *, order_fill_totals: Mapping[str, int] | None = None) -> InternalPaperPositionConsistencyAssessment:
        findings: list[str] = []
        if projection.realized_quantity + projection.remaining_quantity != projection.confirmed_entry_quantity:
            findings.append("quantity arithmetic mismatch")
        if len(set(projection.entry_fill_ids)) != len(projection.entry_fill_ids) or len(set(projection.exit_fill_ids)) != len(projection.exit_fill_ids):
            findings.append("duplicate applied fill id")
        active_exit_qty = sum(ref.quantity for ref in projection.active_order_references if ref.status == "ACTIVE")
        if active_exit_qty > projection.remaining_quantity * 2:
            findings.append("active protection exceeds application-managed linked model allowance")
        if projection.lifecycle_state is InternalPaperPositionState.CLOSED and projection.remaining_quantity != 0:
            findings.append("closed state has remaining quantity")
        if order_fill_totals:
            applied = len(projection.entry_fill_ids) + len(projection.exit_fill_ids)
            if sum(order_fill_totals.values()) < applied:
                findings.append("order fill totals do not cover applied fills")
        status = InternalPaperPositionConsistencyStatus.MATCHED if not findings else InternalPaperPositionConsistencyStatus.REVIEW_REQUIRED
        return InternalPaperPositionConsistencyAssessment(
            assessment_id="position-consistency:" + canonical_hash({"position_cycle_id": projection.identity.position_cycle_id, "findings": findings})[:24],
            status=status,
            findings=tuple(findings),
            projection_hash=projection.projection_hash,
        )

    def pnl_input_facts(self, projection: InternalPaperPositionCycleProjection, *, exit_reason: str | None = None) -> PnlInputFacts:
        return PnlInputFacts(
            position_cycle_id=projection.identity.position_cycle_id,
            side=projection.identity.side,
            multiplier=projection.multiplier,
            lot_size=projection.lot_size,
            currency=projection.currency,
            entry_fill_ids=projection.entry_fill_ids,
            exit_fill_ids=projection.exit_fill_ids,
            average_entry_price=projection.average_entry_price,
            average_exit_price=projection.average_exit_price,
            realized_quantity=projection.realized_quantity,
            remaining_quantity=projection.remaining_quantity,
            exit_reason=exit_reason,
        )

    def _validate_entry_fill(self, projection: InternalPaperPositionCycleProjection, client_order: Mapping[str, Any], fill: Mapping[str, Any], requested_quantity: int) -> None:
        if str(client_order["order_purpose"]) != "ENTRY":
            raise PositionCycleCoordinatorError("Only ENTRY ClientOrders can open a position.")
        if str(fill["client_order_id"]) != str(client_order["client_order_id"]):
            raise PositionCycleCoordinatorError("Fill does not belong to ClientOrder.")
        if str(fill["broker_account_id"]) != projection.identity.broker_account_id:
            raise PositionCycleCoordinatorError("Fill account mismatch.")
        if str(fill["strategy_instance_id"]) != projection.identity.strategy_instance_id:
            raise PositionCycleCoordinatorError("Fill strategy mismatch.")
        if str(fill["contract"]) != projection.identity.normalized_contract:
            raise PositionCycleCoordinatorError("Fill contract mismatch.")
        if str(fill["side"]) != projection.identity.side:
            raise PositionCycleCoordinatorError("Fill side mismatch.")
        if int(fill["fill_quantity"]) <= 0 or requested_quantity <= 0:
            raise PositionCycleCoordinatorError("Fill/request quantity must be positive.")
        _decimal(fill["fill_price"])

    def _validate_exit_fill(self, projection: InternalPaperPositionCycleProjection, client_order: Mapping[str, Any], fill: Mapping[str, Any]) -> None:
        if str(client_order.get("position_cycle_id")) != projection.identity.position_cycle_id or str(fill.get("position_cycle_id")) != projection.identity.position_cycle_id:
            raise PositionCycleCoordinatorError("Exit fill must reference the PositionCycle.")
        if str(fill["broker_account_id"]) != projection.identity.broker_account_id:
            raise PositionCycleCoordinatorError("Exit fill account mismatch.")
        if str(fill["strategy_instance_id"]) != projection.identity.strategy_instance_id:
            raise PositionCycleCoordinatorError("Exit fill strategy mismatch.")
        if str(fill["contract"]) != projection.identity.normalized_contract:
            raise PositionCycleCoordinatorError("Exit fill contract mismatch.")
        if str(fill["side"]) == projection.identity.side:
            raise PositionCycleCoordinatorError("Exit side must reduce the position.")
        if int(fill["fill_quantity"]) <= 0:
            raise PositionCycleCoordinatorError("Exit fill quantity must be positive.")
        _decimal(fill["fill_price"])

    def _entry_requirements(self, projection: InternalPaperPositionCycleProjection, source_rule_ids: tuple[str, ...], fill: Mapping[str, Any], prices: Mapping[str, Decimal | str | None], *, full: bool) -> tuple[LifecycleRequirement, ...]:
        target_price = prices.get("target")
        original_sl_price = prices.get("original_sl")
        requirements = [
            self._requirement(projection, LifecycleRequirementType.TARGET_EXIT_REQUIRED, _decimal(target_price or "1"), source_rule_ids, fill, 1),
            self._requirement(projection, LifecycleRequirementType.NORMAL_SL_PLACEMENT_REQUIRED, _decimal(original_sl_price or "1"), source_rule_ids, fill, 1),
        ]
        if not full:
            resize = self._requirement(projection, LifecycleRequirementType.TARGET_EXIT_REQUIRED, _decimal(target_price or "1"), source_rule_ids + ("PROTECTION_RESIZE_REQUIRED",), fill, 1)
            return (*requirements, replace(resize, status="RESIZE_REQUIRED"))
        return tuple(requirements)

    def _requirement(self, projection: InternalPaperPositionCycleProjection, requirement_type: LifecycleRequirementType, price: Decimal, source_rule_ids: tuple[str, ...], fill: Mapping[str, Any], generation: int) -> LifecycleRequirement:
        payload = {
            "position_cycle_id": projection.identity.position_cycle_id,
            "requirement_type": requirement_type.value,
            "quantity": projection.remaining_quantity,
            "generation": generation,
            "fill": fill["internal_fill_id"],
        }
        return LifecycleRequirement(
            requirement_id="lifecycle-req:" + canonical_hash(payload)[:24],
            position_cycle_id=projection.identity.position_cycle_id,
            requirement_type=requirement_type,
            quantity=projection.remaining_quantity,
            side=_opposite_side(projection.identity.side),
            price=price,
            source_rule_ids=source_rule_ids,
            source_artifact_id=str(fill["scenario_id"]),
            source_artifact_hash=str(fill.get("fill_hash", "")),
            protection_generation=generation,
            created_at=_dt(fill["recorded_timestamp"]),
            protection_model=ProtectionModel.APPLICATION_MANAGED_LINKED_PROTECTION,
        )

    def _with_reference(self, projection: InternalPaperPositionCycleProjection, reference: ProtectionOrderReference) -> InternalPaperPositionCycleProjection:
        active_target = projection.active_target
        active_original_sl = projection.active_original_sl
        active_revised_sl = projection.active_revised_sl
        superseded = list(projection.superseded_protections)
        state = InternalPaperPositionState.OPEN_PROTECTION_PENDING
        generation = max(projection.protection_generation, reference.protection_generation)
        if reference.order_purpose == "TARGET":
            active_target = reference
        elif reference.order_purpose == "ORIGINAL_SL":
            active_original_sl = reference
        elif reference.order_purpose == "REVISED_SL":
            if projection.active_original_sl is not None:
                superseded.append(replace(projection.active_original_sl, status="SUPERSEDED"))
            if projection.active_revised_sl is not None:
                superseded.append(replace(projection.active_revised_sl, status="SUPERSEDED"))
            active_original_sl = None
            active_revised_sl = reference
        else:
            raise PositionCycleCoordinatorError("Unsupported protection purpose.")
        if active_target is not None and (active_original_sl is not None or active_revised_sl is not None):
            state = InternalPaperPositionState.OPEN_PROTECTED
        refs = tuple(ref for ref in (active_target, active_original_sl, active_revised_sl) if ref is not None)
        return replace(
            projection,
            lifecycle_state=state,
            active_target=active_target,
            active_original_sl=active_original_sl,
            active_revised_sl=active_revised_sl,
            active_order_references=refs,
            superseded_protections=tuple(superseded),
            protection_generation=generation,
            projection_version=projection.projection_version + 1,
        )

    def _after_exit_protections(self, projection: InternalPaperPositionCycleProjection, purpose: str) -> tuple[ProtectionOrderReference | None, ProtectionOrderReference | None, ProtectionOrderReference | None, tuple[ProtectionOrderReference, ...]]:
        superseded = list(projection.superseded_protections)
        for ref in (projection.active_target, projection.active_original_sl, projection.active_revised_sl):
            if ref is not None:
                superseded.append(replace(ref, status="SUPERSEDED_BY_EXIT_FILL"))
        return None, None, None, tuple(superseded)

    def _event(
        self,
        *,
        projection: InternalPaperPositionCycleProjection,
        event_type: InternalPaperPositionEventType,
        prior_state: InternalPaperPositionState | None,
        new_state: InternalPaperPositionState,
        quantity_before: int,
        quantity_after: int,
        timestamp: datetime,
        price_evidence: Mapping[str, Any] | None = None,
        source_fill_id: str | None = None,
        source_client_order_id: str | None = None,
        source_requirement_id: str | None = None,
        rule_ids: tuple[str, ...] = (),
    ) -> InternalPaperPositionEvent:
        sequence = projection.projection_version
        payload = {
            "position_cycle_id": projection.identity.position_cycle_id,
            "event_type": event_type.value,
            "sequence": sequence,
            "source_fill_id": source_fill_id,
            "source_client_order_id": source_client_order_id,
            "source_requirement_id": source_requirement_id,
        }
        return InternalPaperPositionEvent(
            event_id="position-event:" + canonical_hash(payload)[:24],
            position_cycle_id=projection.identity.position_cycle_id,
            event_sequence=sequence,
            event_type=event_type,
            prior_state=prior_state,
            new_state=new_state,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            price_evidence=price_evidence or {},
            source_fill_id=source_fill_id,
            source_client_order_id=source_client_order_id,
            source_requirement_id=source_requirement_id,
            rule_ids=rule_ids,
            event_timestamp=timestamp,
        )

    def _transition(self, projection: InternalPaperPositionCycleProjection, event: InternalPaperPositionEvent, requirements: tuple[LifecycleRequirement, ...] = ()) -> InternalPaperPositionTransition:
        return InternalPaperPositionTransition(
            transition_id="position-transition:" + canonical_hash({"event_id": event.event_id, "projection_hash": projection.projection_hash})[:24],
            projection=projection,
            event=event,
            requirements=requirements,
        )

    def _ensure_not_terminal(self, projection: InternalPaperPositionCycleProjection) -> None:
        if projection.lifecycle_state in TERMINAL_STATES:
            raise PositionCycleCoordinatorError("Closed or terminal cycle cannot be mutated.")


def _weighted_average(*, prior_average: Decimal | None, prior_quantity: int, new_price: Decimal, new_quantity: int) -> Decimal:
    if new_quantity <= 0 or new_price <= 0:
        raise PositionCycleCoordinatorError("Weighted average inputs must be positive.")
    if prior_average is None or prior_quantity == 0:
        return new_price
    return ((prior_average * Decimal(prior_quantity)) + (new_price * Decimal(new_quantity))) / Decimal(prior_quantity + new_quantity)


def _decimal(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise PositionCycleCoordinatorError("Invalid Decimal value.") from exc
    if result <= 0:
        raise PositionCycleCoordinatorError("Decimal value must be positive.")
    return result


def _dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _opposite_side(side: str) -> str:
    return "BUY" if side == "SELL" else "SELL"
