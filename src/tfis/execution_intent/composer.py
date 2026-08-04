from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from tfis.persistence import canonical_hash

from .models import (
    ExecutionAuthorityMode,
    ExecutionInstrument,
    ExecutionIntent,
    ExecutionIntentEvidence,
    ExecutionIntentPurpose,
    RequestedExecutionAction,
    SCHEMA_VERSION,
)
from .pricing import normalize_executable_price


@dataclass(frozen=True, slots=True)
class IntentCompositionRequest:
    trading_session_id: str
    trading_date: Any
    strategy_family_id: str
    strategy_definition_id: str
    strategy_version: str
    strategy_instance_id: str
    broker_account_id: str
    position_cycle_id: str | None
    source_artifact_type: str
    source_artifact_id: str
    source_artifact_hash: str
    instrument: ExecutionInstrument
    purpose: ExecutionIntentPurpose
    side: str
    requested_quantity: int
    quantity_unit: str
    order_type: str
    limit_price: Decimal | None
    trigger_price: Decimal | None
    time_in_force: str
    authorized_not_before: datetime
    authorized_not_after: datetime | None
    maximum_allowed_slippage: Decimal | None
    protection_generation: int | None
    source_rule_ids: tuple[str, ...]
    configuration_hash: str
    rule_matrix_version: str
    market_snapshot_hash: str
    reconciliation_result_id: str
    reconciliation_result_hash: str
    recovery_assessment_id: str
    recovery_assessment_hash: str
    evidence_packet_hash: str
    provenance: Mapping[str, Any]
    authority_mode: ExecutionAuthorityMode = ExecutionAuthorityMode.OFFLINE_ONLY


class ExecutionIntentComposer:
    def compose(self, request: IntentCompositionRequest) -> ExecutionIntent:
        normalized_limit_price = normalize_executable_price(request.limit_price, request.instrument.tick_size)
        normalized_trigger_price = normalize_executable_price(request.trigger_price, request.instrument.tick_size)
        idempotency_key = _idempotency_key(request)
        execution_intent_id = f"exec-intent:{canonical_hash({'idempotency_key': idempotency_key})[:24]}"
        evidence = ExecutionIntentEvidence(
            source_rule_ids=request.source_rule_ids,
            configuration_hash=request.configuration_hash,
            rule_matrix_version=request.rule_matrix_version,
            market_snapshot_hash=request.market_snapshot_hash,
            reconciliation_result_id=request.reconciliation_result_id,
            reconciliation_result_hash=request.reconciliation_result_hash,
            recovery_assessment_id=request.recovery_assessment_id,
            recovery_assessment_hash=request.recovery_assessment_hash,
            evidence_packet_hash=request.evidence_packet_hash,
            provenance=request.provenance,
            authority_mode=request.authority_mode,
        )
        action = RequestedExecutionAction(
            purpose=request.purpose,
            side=request.side,
            requested_quantity=request.requested_quantity,
            quantity_unit=request.quantity_unit,
            order_type=request.order_type,
            limit_price=normalized_limit_price,
            trigger_price=normalized_trigger_price,
            time_in_force=request.time_in_force,
            authorized_not_before=request.authorized_not_before,
            authorized_not_after=request.authorized_not_after,
            maximum_allowed_slippage=request.maximum_allowed_slippage,
            protection_generation=request.protection_generation,
        )
        return ExecutionIntent(
            execution_intent_id=execution_intent_id,
            schema_version=SCHEMA_VERSION,
            trading_session_id=request.trading_session_id,
            trading_date=request.trading_date,
            strategy_family_id=request.strategy_family_id,
            strategy_definition_id=request.strategy_definition_id,
            strategy_version=request.strategy_version,
            strategy_instance_id=request.strategy_instance_id,
            broker_account_id=request.broker_account_id,
            position_cycle_id=request.position_cycle_id,
            source_artifact_type=request.source_artifact_type,
            source_artifact_id=request.source_artifact_id,
            source_artifact_hash=request.source_artifact_hash,
            idempotency_key=idempotency_key,
            instrument=request.instrument,
            action=action,
            evidence=evidence,
        )


def _idempotency_key(request: IntentCompositionRequest) -> str:
    normalized_limit_price = normalize_executable_price(request.limit_price, request.instrument.tick_size)
    normalized_trigger_price = normalize_executable_price(request.trigger_price, request.instrument.tick_size)
    payload = {
        "broker_account_id": request.broker_account_id,
        "strategy_instance_id": request.strategy_instance_id,
        "position_cycle_id": request.position_cycle_id,
        "source_artifact_id": request.source_artifact_id,
        "purpose": request.purpose.value,
        "protection_generation": request.protection_generation,
        "authorized_not_before": request.authorized_not_before.isoformat(),
        "authorized_not_after": request.authorized_not_after.isoformat() if request.authorized_not_after else None,
        "quantity": request.requested_quantity,
        "limit_price": str(normalized_limit_price) if normalized_limit_price is not None else None,
        "trigger_price": str(normalized_trigger_price) if normalized_trigger_price is not None else None,
    }
    return f"phase4e:{canonical_hash(payload)}"
