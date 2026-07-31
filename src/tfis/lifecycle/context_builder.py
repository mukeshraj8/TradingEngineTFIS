from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from time import perf_counter
from typing import Any, Mapping

from tfis.domain.position_lifecycle import (
    LifecycleActionRequirement,
    LifecycleContextFailure,
    LifecycleGapDirection,
    LifecycleGapObservation,
    LifecycleEconomicGapEffect,
    LifecycleLevelObservation,
    LifecycleOpeningEvidence,
    LifecycleOpeningStatus,
    LifecycleProtectionState,
    LifecycleQuoteFreshness,
    PositionLifecycleContext,
    PositionReconciliationStatus,
    ProtectiveOrderVisibilityStatus,
    ReconciledPositionSnapshot,
)
from tfis.domain.runtime_contracts import TFISExecutionSide


@dataclass(frozen=True, slots=True)
class PositionLifecycleBuildInput:
    context_id: str
    trading_date: date
    strategy_family: str
    strategy_definition: str
    strategy_version: str
    strategy_instance_id: str
    configuration_hash: str
    position_snapshot: ReconciledPositionSnapshot | None
    protection_state: LifecycleProtectionState | None
    opening_evidence: LifecycleOpeningEvidence | None
    policy_identities: Mapping[str, str]
    checkpoint_hash: str | None = None
    expected_checkpoint_hash: str | None = None


class PositionLifecycleContextBuilder:
    def build(self, request: PositionLifecycleBuildInput) -> PositionLifecycleContext:
        started = perf_counter()
        failures: list[LifecycleContextFailure] = []
        missing_fields: list[str] = []
        stale_fields: list[str] = []
        unresolved: list[str] = []

        self._validate_snapshot(request, failures, missing_fields)
        self._validate_protection(request, failures, missing_fields, unresolved)
        self._validate_opening_evidence(request, failures, missing_fields, stale_fields)
        if request.expected_checkpoint_hash is not None and request.checkpoint_hash != request.expected_checkpoint_hash:
            failures.append(LifecycleContextFailure("CHECKPOINT_HASH_MISMATCH", "checkpoint_hash", "Lifecycle checkpoint does not match expected resume hash."))

        quote = request.opening_evidence.carried_contract_quote if request.opening_evidence else None
        gap = _gap_observation(request.position_snapshot, quote.ltp if quote else None, quote.prior_reference_price if quote else None)
        levels = _level_observation(request.position_snapshot, request.protection_state, quote.ltp if quote else None)

        status, action = self._classify(request, failures, stale_fields, gap, levels, unresolved)
        elapsed_ms = round((perf_counter() - started) * 1000.0, 3)
        return PositionLifecycleContext(
            context_id=request.context_id,
            schema_version="phase3d.position_lifecycle_context.v1",
            trading_date=request.trading_date,
            strategy_family=request.strategy_family,
            strategy_definition=request.strategy_definition,
            strategy_version=request.strategy_version,
            strategy_instance_id=request.strategy_instance_id,
            configuration_hash=request.configuration_hash,
            position_snapshot=request.position_snapshot,
            protection_state=request.protection_state,
            opening_evidence=request.opening_evidence,
            opening_status=status,
            action_requirement=action,
            gap_observation=gap,
            level_observation=levels,
            missing_fields=tuple(missing_fields),
            stale_fields=tuple(stale_fields),
            unresolved_rule_authorities=tuple(unresolved),
            failures=tuple(failures),
            policy_identities=request.policy_identities,
            evidence={"builder": type(self).__name__, "classification_scope": "observation_only"},
            performance={"build_ms": elapsed_ms},
        )

    def _validate_snapshot(
        self,
        request: PositionLifecycleBuildInput,
        failures: list[LifecycleContextFailure],
        missing_fields: list[str],
    ) -> None:
        snapshot = request.position_snapshot
        if snapshot is None:
            missing_fields.append("position_snapshot")
            failures.append(LifecycleContextFailure("MISSING_POSITION_SNAPSHOT", "position_snapshot", "Carried-position lifecycle requires a reconciled position snapshot."))
            return
        if snapshot.trading_date != request.trading_date:
            failures.append(LifecycleContextFailure("POSITION_DATE_MISMATCH", "position_snapshot.trading_date", "Position snapshot is not for the lifecycle trading date."))
        if snapshot.strategy_instance_id != request.strategy_instance_id:
            failures.append(LifecycleContextFailure("POSITION_STRATEGY_INSTANCE_MISMATCH", "position_snapshot.strategy_instance_id", "Position snapshot belongs to another strategy instance."))
        if snapshot.configuration_hash != request.configuration_hash:
            failures.append(LifecycleContextFailure("POSITION_CONFIGURATION_MISMATCH", "position_snapshot.configuration_hash", "Position snapshot configuration hash differs from lifecycle request."))
        if snapshot.reconciliation_status is not PositionReconciliationStatus.MATCHED:
            failures.append(LifecycleContextFailure("POSITION_RECONCILIATION_NOT_MATCHED", "position_snapshot.reconciliation_status", "Position quantities are not fully reconciled."))
        if snapshot.local_quantity != snapshot.external_quantity or snapshot.reconciled_quantity != snapshot.local_quantity:
            failures.append(LifecycleContextFailure("POSITION_QUANTITY_MISMATCH", "position_snapshot.reconciled_quantity", "Local, external, and reconciled quantities must match for offline observation."))
        if snapshot.contract is None:
            missing_fields.append("position_snapshot.contract")

    def _validate_protection(
        self,
        request: PositionLifecycleBuildInput,
        failures: list[LifecycleContextFailure],
        missing_fields: list[str],
        unresolved: list[str],
    ) -> None:
        protection = request.protection_state
        if protection is None:
            missing_fields.append("protection_state")
            failures.append(LifecycleContextFailure("MISSING_PROTECTION_STATE", "protection_state", "Carried position requires carried target/protection state."))
            return
        unresolved.extend(protection.unresolved_fields)
        if not protection.target_levels:
            missing_fields.append("protection_state.target_levels")
        if not protection.protective_levels:
            missing_fields.append("protection_state.protective_levels")
            failures.append(LifecycleContextFailure("MISSING_PROTECTIVE_LEVELS", "protection_state.protective_levels", "Protective levels are required before carried-position opening observation."))
        if protection.protective_order_status is not ProtectiveOrderVisibilityStatus.MATCHED:
            failures.append(LifecycleContextFailure("PROTECTIVE_ORDER_NOT_MATCHED", "protection_state.protective_order_status", "Protective order visibility is not confirmed as matched."))

    def _validate_opening_evidence(
        self,
        request: PositionLifecycleBuildInput,
        failures: list[LifecycleContextFailure],
        missing_fields: list[str],
        stale_fields: list[str],
    ) -> None:
        evidence = request.opening_evidence
        if evidence is None:
            missing_fields.append("opening_evidence")
            failures.append(LifecycleContextFailure("MISSING_OPENING_EVIDENCE", "opening_evidence", "Opening evidence is required for carried-position lifecycle context."))
            return
        quote = evidence.carried_contract_quote
        if quote is None:
            missing_fields.append("opening_evidence.carried_contract_quote")
            failures.append(LifecycleContextFailure("OPENING_QUOTE_UNAVAILABLE", "opening_evidence.carried_contract_quote", "Carried contract quote is unavailable."))
            return
        snapshot = request.position_snapshot
        if snapshot is not None and quote.contract != snapshot.contract:
            failures.append(LifecycleContextFailure("CARRIED_CONTRACT_MISMATCH", "opening_evidence.carried_contract_quote.contract", "Opening quote contract differs from reconciled position contract."))
        if quote.ltp is None:
            missing_fields.append("opening_evidence.carried_contract_quote.ltp")
            failures.append(LifecycleContextFailure("OPENING_QUOTE_PRICE_UNAVAILABLE", "opening_evidence.carried_contract_quote.ltp", "Carried contract quote has no observed price."))
        if quote.freshness is LifecycleQuoteFreshness.STALE:
            stale_fields.append("opening_evidence.carried_contract_quote")
            failures.append(LifecycleContextFailure("OPENING_QUOTE_STALE", "opening_evidence.carried_contract_quote", "Carried contract quote is stale."))
        if quote.freshness is LifecycleQuoteFreshness.MISSING:
            missing_fields.append("opening_evidence.carried_contract_quote")
            failures.append(LifecycleContextFailure("OPENING_QUOTE_MISSING", "opening_evidence.carried_contract_quote", "Carried contract quote freshness is missing."))

    def _classify(
        self,
        request: PositionLifecycleBuildInput,
        failures: list[LifecycleContextFailure],
        stale_fields: list[str],
        gap: LifecycleGapObservation,
        levels: LifecycleLevelObservation,
        unresolved: list[str],
    ) -> tuple[LifecycleOpeningStatus, LifecycleActionRequirement]:
        failure_codes = {failure.code for failure in failures}
        if "OPENING_QUOTE_UNAVAILABLE" in failure_codes or "OPENING_QUOTE_PRICE_UNAVAILABLE" in failure_codes or "OPENING_QUOTE_MISSING" in failure_codes:
            return LifecycleOpeningStatus.OPENING_QUOTE_UNAVAILABLE, LifecycleActionRequirement.BLOCKED_INSUFFICIENT_EVIDENCE
        if "OPENING_QUOTE_STALE" in failure_codes or stale_fields:
            return LifecycleOpeningStatus.OPENING_QUOTE_STALE, LifecycleActionRequirement.WAIT_FOR_AUTHORIZED_OBSERVATION
        if failures:
            return LifecycleOpeningStatus.BLOCKED_LIFECYCLE_CONTEXT, LifecycleActionRequirement.BLOCKED_INSUFFICIENT_EVIDENCE
        if levels.target_crossed:
            return LifecycleOpeningStatus.TARGET_CROSSED_AT_OPEN, LifecycleActionRequirement.EXIT_REQUIRED
        if len(levels.crossed_targets) + len(levels.crossed_protective_levels) > 1:
            unresolved.append("OPENING_MULTIPLE_LEVEL_PRIORITY")
            return LifecycleOpeningStatus.MULTIPLE_LEVELS_CROSSED, LifecycleActionRequirement.RULE_AUTHORITY_UNRESOLVED
        sl_path = self._classify_orpt_original_sl_path(request, unresolved)
        if sl_path is not None:
            return sl_path
        if gap.direction is LifecycleGapDirection.UP:
            return LifecycleOpeningStatus.GAP_UP_OBSERVED, LifecycleActionRequirement.OPENING_REASSESSMENT_REQUIRED
        if gap.direction is LifecycleGapDirection.DOWN:
            return LifecycleOpeningStatus.GAP_DOWN_OBSERVED, LifecycleActionRequirement.OPENING_REASSESSMENT_REQUIRED
        return LifecycleOpeningStatus.NORMAL_OPENING_CONTINUATION, LifecycleActionRequirement.CONTINUE_NORMAL_MONITORING

    def _classify_orpt_original_sl_path(
        self,
        request: PositionLifecycleBuildInput,
        unresolved: list[str],
    ) -> tuple[LifecycleOpeningStatus, LifecycleActionRequirement] | None:
        evidence = request.opening_evidence
        protection = request.protection_state
        if evidence is None or protection is None or not protection.protective_levels:
            return None
        original_sl = next(iter(protection.protective_levels.values()))
        orpt = evidence.orpt_contract_observation
        if orpt is None or orpt.high is None:
            unresolved.append("CARRIED_POSITION_ORPT_ORIGINAL_SL_OBSERVATION_MISSING")
            return LifecycleOpeningStatus.PARTIAL_CONTEXT, LifecycleActionRequirement.WAIT_FOR_AUTHORIZED_OBSERVATION
        if float(orpt.high) <= float(original_sl):
            return LifecycleOpeningStatus.NORMAL_OPENING_CONTINUATION, LifecycleActionRequirement.NORMAL_SL_PLACEMENT_REQUIRED
        if evidence.rc_contract_observation is None:
            unresolved.append("CARRIED_POSITION_RC_OBSERVATION_MISSING")
            return LifecycleOpeningStatus.PARTIAL_CONTEXT, LifecycleActionRequirement.WAIT_FOR_AUTHORIZED_OBSERVATION
        if self._has_revised_protection_policy(protection, unresolved):
            return LifecycleOpeningStatus.PROTECTIVE_LEVEL_CROSSED_AT_OPEN, LifecycleActionRequirement.REVISED_SL_PLACEMENT_REQUIRED
        return LifecycleOpeningStatus.PROTECTIVE_LEVEL_CROSSED_AT_OPEN, LifecycleActionRequirement.RULE_AUTHORITY_UNRESOLVED

    def _has_revised_protection_policy(self, protection: LifecycleProtectionState | None, unresolved: list[str]) -> bool:
        if protection is None:
            unresolved.append("CARRIED_POSITION_REVISED_SL_POLICY_MISSING")
            return False
        has_time = protection.lifecycle_recalculation_time is not None
        has_formula = bool(protection.revised_protective_formula_policy_id)
        if not has_time:
            unresolved.append("CARRIED_POSITION_RECALCULATION_TIME_MISSING")
        if not has_formula:
            unresolved.append("CARRIED_POSITION_REVISED_SL_FORMULA_MISSING")
        return has_time and has_formula


def _gap_observation(snapshot: ReconciledPositionSnapshot | None, observed: float | None, reference: float | None) -> LifecycleGapObservation:
    if observed is None or reference is None or reference == 0:
        return LifecycleGapObservation(LifecycleGapDirection.UNKNOWN, LifecycleEconomicGapEffect.UNKNOWN, None, None, reference, observed, {"reason": "missing_comparison_reference"})
    amount = round(float(observed) - float(reference), 4)
    percentage = round((amount / float(reference)) * 100.0, 4)
    if amount > 0:
        direction = LifecycleGapDirection.UP
    elif amount < 0:
        direction = LifecycleGapDirection.DOWN
    else:
        direction = LifecycleGapDirection.NONE
    effect = _economic_gap_effect(snapshot, amount)
    return LifecycleGapObservation(
        direction,
        effect,
        amount,
        percentage,
        reference,
        observed,
        {
            "comparison": "opening_ltp_vs_prior_reference_price",
            "economic_basis": "position_side_and_carried_contract_premium",
            "option_type": snapshot.contract.option_type if snapshot and snapshot.contract else None,
            "position_side": snapshot.side.value if snapshot else None,
        },
    )


def _economic_gap_effect(snapshot: ReconciledPositionSnapshot | None, amount: float) -> LifecycleEconomicGapEffect:
    if amount == 0:
        return LifecycleEconomicGapEffect.NEUTRAL
    if snapshot is None:
        return LifecycleEconomicGapEffect.UNKNOWN
    if snapshot.side is TFISExecutionSide.SELL:
        return LifecycleEconomicGapEffect.ADVERSE if amount > 0 else LifecycleEconomicGapEffect.FAVORABLE
    if snapshot.side is TFISExecutionSide.BUY:
        return LifecycleEconomicGapEffect.FAVORABLE if amount > 0 else LifecycleEconomicGapEffect.ADVERSE
    return LifecycleEconomicGapEffect.UNKNOWN


def _level_observation(
    snapshot: ReconciledPositionSnapshot | None,
    protection: LifecycleProtectionState | None,
    price: float | None,
) -> LifecycleLevelObservation:
    if snapshot is None or protection is None or price is None:
        return LifecycleLevelObservation(False, False, comparison_price=price, comparison_basis="carried_contract_opening_ltp", evidence={"reason": "missing_level_comparison_input"})
    crossed_targets: list[str] = []
    crossed_protective: list[str] = []
    if snapshot.side is TFISExecutionSide.SELL:
        crossed_targets = [label for label, level in protection.target_levels.items() if price <= float(level)]
        crossed_protective = [label for label, level in protection.protective_levels.items() if price >= float(level)]
    else:
        crossed_targets = [label for label, level in protection.target_levels.items() if price >= float(level)]
        crossed_protective = [label for label, level in protection.protective_levels.items() if price <= float(level)]
    return LifecycleLevelObservation(
        target_crossed=bool(crossed_targets),
        protective_level_crossed=bool(crossed_protective),
        crossed_targets=tuple(crossed_targets),
        crossed_protective_levels=tuple(crossed_protective),
        comparison_price=price,
        comparison_basis="carried_contract_opening_ltp",
        evidence={"comparison_rule": "side_aware_target_and_protection_threshold_observation"},
    )
