from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from tfis.domain.effective_execution_plan import EffectiveExecutionPlan
from tfis.domain.runtime_contracts import TFISContractIdentity
from tfis.execution_intent import ExecutionIntentComposer, ExecutionIntentPurpose, IntentCompositionRequest
from tfis.execution_intent.models import ExecutionAuthorityMode, ExecutionInstrument, ExecutionIntent
from tfis.persistence import canonical_hash


DEFAULT_ACCOUNT_ID = "S23_ACCOUNT_A_SHADOW"
DEFAULT_TRADING_SESSION_PREFIX = "NSE"
DEFAULT_RULE_MATRIX_VERSION = "s23_authoritative_matrix_phase3d_m13b"
DEFAULT_CONFIG_HASH = "s23-first-slice-config-hash"
DEFAULT_RECOVERY_ID = "phase4e-recovery-fixture"
DEFAULT_RECOVERY_HASH = "phase4e-recovery-hash"
DEFAULT_RECONCILIATION_ID = "phase4d-s23-ready"
DEFAULT_RECONCILIATION_HASH = "phase4d-s23-ready-hash"
DEFAULT_EVIDENCE_PACKET_HASH = "phase4e-s23-fixture-evidence"


class S23ExecutionIntentAdapter:
    def __init__(self, composer: ExecutionIntentComposer | None = None) -> None:
        self.composer = composer or ExecutionIntentComposer()

    def entry_from_effective_plan(
        self,
        plan: EffectiveExecutionPlan,
        *,
        broker_account_id: str = DEFAULT_ACCOUNT_ID,
        trading_session_id: str | None = None,
        source_artifact_id: str | None = None,
        source_artifact_hash: str | None = None,
        market_snapshot_hash: str = "phase4e-market-snapshot-fixture",
        reconciliation_result_id: str = DEFAULT_RECONCILIATION_ID,
        reconciliation_result_hash: str = DEFAULT_RECONCILIATION_HASH,
        recovery_assessment_id: str = DEFAULT_RECOVERY_ID,
        recovery_assessment_hash: str = DEFAULT_RECOVERY_HASH,
    ) -> ExecutionIntent:
        if plan.selected_contract is None or plan.order_side is None or plan.quantity is None or plan.values.effective_entry is None:
            raise ValueError("EffectiveExecutionPlan is missing required ENTRY intent fields.")
        auth_time = datetime.combine(plan.trading_date, plan.values.revised_authorized_time or plan.values.normal_orpt or time(9, 15), tzinfo=ZoneInfo("Asia/Kolkata"))
        source_id = source_artifact_id or plan.execution_plan_id
        source_hash = source_artifact_hash or plan.execution_plan_hash
        return self.composer.compose(
            IntentCompositionRequest(
                trading_session_id=trading_session_id or f"{DEFAULT_TRADING_SESSION_PREFIX}:{plan.trading_date.isoformat()}",
                trading_date=plan.trading_date,
                strategy_family_id=plan.strategy_family,
                strategy_definition_id=plan.strategy_definition,
                strategy_version=plan.strategy_version,
                strategy_instance_id=plan.strategy_instance_id,
                broker_account_id=broker_account_id,
                position_cycle_id=None,
                source_artifact_type="EffectiveExecutionPlan",
                source_artifact_id=source_id,
                source_artifact_hash=source_hash,
                instrument=_instrument(plan.selected_contract, plan.product.value if plan.product else "OPTION_SELLING"),
                purpose=ExecutionIntentPurpose.ENTRY,
                side=plan.order_side.value,
                requested_quantity=plan.quantity,
                quantity_unit="LOTS",
                order_type=plan.values.order_type or "LIMIT",
                limit_price=Decimal(str(plan.values.effective_entry)),
                trigger_price=None,
                time_in_force="DAY",
                authorized_not_before=auth_time,
                authorized_not_after=None,
                maximum_allowed_slippage=Decimal("0.05"),
                protection_generation=None,
                source_rule_ids=_source_rules(plan, "S23_ENTRY_INTENT"),
                configuration_hash=plan.policy_identities.get("configuration_hash", DEFAULT_CONFIG_HASH),
                rule_matrix_version=plan.policy_identities.get("rule_matrix_version", DEFAULT_RULE_MATRIX_VERSION),
                market_snapshot_hash=market_snapshot_hash,
                reconciliation_result_id=reconciliation_result_id,
                reconciliation_result_hash=reconciliation_result_hash,
                recovery_assessment_id=recovery_assessment_id,
                recovery_assessment_hash=recovery_assessment_hash,
                evidence_packet_hash=DEFAULT_EVIDENCE_PACKET_HASH,
                provenance={"adapter": type(self).__name__, "source_plan": source_id, "path": plan.path_classification.value},
                authority_mode=ExecutionAuthorityMode.OFFLINE_ONLY,
            )
        )

    def lifecycle_intent(
        self,
        *,
        purpose: ExecutionIntentPurpose,
        trading_date,
        strategy_family_id: str,
        strategy_definition_id: str,
        strategy_version: str,
        strategy_instance_id: str,
        broker_account_id: str,
        position_cycle_id: str,
        contract: TFISContractIdentity,
        quantity: int,
        side: str,
        price: Decimal | None,
        source_artifact_type: str,
        source_artifact_id: str,
        source_artifact_hash: str,
        authorized_not_before: datetime,
        protection_generation: int | None,
        rule_id: str,
        superseded_requirement_id: str | None = None,
    ) -> ExecutionIntent:
        order_type = "LIMIT" if purpose in {ExecutionIntentPurpose.TARGET, ExecutionIntentPurpose.EOD_EXIT, ExecutionIntentPurpose.RISK_EXIT, ExecutionIntentPurpose.OPERATOR_EXIT} else "SL"
        return self.composer.compose(
            IntentCompositionRequest(
                trading_session_id=f"{DEFAULT_TRADING_SESSION_PREFIX}:{trading_date.isoformat()}",
                trading_date=trading_date,
                strategy_family_id=strategy_family_id,
                strategy_definition_id=strategy_definition_id,
                strategy_version=strategy_version,
                strategy_instance_id=strategy_instance_id,
                broker_account_id=broker_account_id,
                position_cycle_id=position_cycle_id,
                source_artifact_type=source_artifact_type,
                source_artifact_id=source_artifact_id,
                source_artifact_hash=source_artifact_hash,
                instrument=_instrument(contract, "OPTION_SELLING"),
                purpose=purpose,
                side=side,
                requested_quantity=quantity,
                quantity_unit="LOTS",
                order_type=order_type,
                limit_price=price if order_type == "LIMIT" else None,
                trigger_price=price if order_type == "SL" else None,
                time_in_force="DAY",
                authorized_not_before=authorized_not_before,
                authorized_not_after=None,
                maximum_allowed_slippage=Decimal("0.05"),
                protection_generation=protection_generation,
                source_rule_ids=(rule_id,),
                configuration_hash=DEFAULT_CONFIG_HASH,
                rule_matrix_version=DEFAULT_RULE_MATRIX_VERSION,
                market_snapshot_hash=f"market:{source_artifact_id}",
                reconciliation_result_id=DEFAULT_RECONCILIATION_ID,
                reconciliation_result_hash=DEFAULT_RECONCILIATION_HASH,
                recovery_assessment_id=DEFAULT_RECOVERY_ID,
                recovery_assessment_hash=DEFAULT_RECOVERY_HASH,
                evidence_packet_hash=canonical_hash({"source_artifact_id": source_artifact_id, "purpose": purpose.value}),
                provenance={
                    "adapter": type(self).__name__,
                    "source_artifact_type": source_artifact_type,
                    "superseded_requirement_id": superseded_requirement_id,
                },
                authority_mode=ExecutionAuthorityMode.OFFLINE_ONLY,
            )
        )


def _instrument(contract: TFISContractIdentity, product: str) -> ExecutionInstrument:
    return ExecutionInstrument(
        exchange=contract.exchange or "NSE",
        segment=contract.segment.value if contract.segment is not None else "OPTIONS_SELL",
        product=product,
        underlying=(contract.metadata.get("underlying") if contract.metadata else None) or "NIFTY",
        contract=contract.symbol or "UNKNOWN_CONTRACT",
        expiry=contract.expiry,
        strike=Decimal(str(contract.strike)) if contract.strike is not None else None,
        option_type=contract.option_type,
        lot_size=int(contract.metadata.get("lot_size", 75)) if contract.metadata else 75,
        tick_size=Decimal(str(contract.metadata.get("tick_size", "0.05"))) if contract.metadata else Decimal("0.05"),
        multiplier=Decimal(str(contract.metadata.get("multiplier", "1"))) if contract.metadata else Decimal("1"),
        currency=str(contract.metadata.get("currency", "INR")) if contract.metadata else "INR",
    )


def _source_rules(plan: EffectiveExecutionPlan, fallback: str) -> tuple[str, ...]:
    rules = tuple(str(value) for value in plan.policy_identities.values() if "S23" in str(value) or "s23" in str(value))
    return rules or (fallback,)
