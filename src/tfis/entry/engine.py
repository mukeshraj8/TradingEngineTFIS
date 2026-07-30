from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from time import perf_counter
from types import MappingProxyType
from typing import Mapping

from tfis.domain.business_engine import BusinessEngineStatus
from tfis.domain.entry import (
    EntryBaseCandidate,
    EntryDownstreamPermission,
    EntryEffectiveTrigger,
    EntryEngineInput,
    EntryEngineResult,
    EntryEvidence,
    EntryFailure,
    EntryMetrics,
    EntryPolicy,
    EntryQuality,
    EntryReferenceRequirement,
    EntryReferenceSource,
    EntrySource,
    EntryStatus,
    EntryTriggerDirection,
    EntryUnresolvedSemantics,
    EntryValidation,
    EntryValidationIssue,
    EntryWarning,
    entry_hash,
)
from tfis.domain.gap_missed_entry import (
    MissedEntryState,
    RecalculationDownstreamAction,
    RecalculationStatus,
)
from tfis.domain.runtime_contracts import TFISProductType


class EntryEngine:
    engine_id = "entry"

    def __init__(self, policies: Mapping[str, EntryPolicy]) -> None:
        self._policies = MappingProxyType({str(key): value for key, value in sorted(policies.items())})

    def execute(self, engine_input: EntryEngineInput) -> EntryEngineResult:
        started = perf_counter()
        validation = validate_entry_input(engine_input)
        validation_seconds = perf_counter() - started

        policy_started = perf_counter()
        policy = self._policies.get(engine_input.entry_policy_key)
        policy_resolution_seconds = perf_counter() - policy_started
        if policy is None:
            validation = _append_issue(
                validation,
                EntryFailure.UNKNOWN_ENTRY_POLICY,
                "entry_policy_key",
                "entry policy key is not registered",
            )

        eval_started = perf_counter()
        base_candidate: EntryBaseCandidate | None = None
        effective_trigger: EntryEffectiveTrigger | None = None
        policy_failures: tuple[EntryFailure, ...] = ()
        policy_warnings: tuple[EntryWarning, ...] = ()
        if validation.passed and policy is not None:
            base_outcome = policy.evaluate_base(engine_input)
            base_candidate = base_outcome.base_candidate
            policy_failures += tuple(base_outcome.failures)
            policy_warnings += tuple(base_outcome.warnings)
            if base_candidate is None:
                policy_failures += (EntryFailure.FORMULA_EVALUATION_ERROR,)
            else:
                validation = _merge_validation(validation, base_candidate.validation)
        if validation.passed and policy is not None and base_candidate is not None:
            effective_validation = validate_effective_entry_inputs(engine_input, base_candidate)
            validation = _merge_validation(validation, effective_validation)
            if validation.passed:
                effective_outcome = policy.finalize_effective(
                    engine_input,
                    base_candidate,
                    engine_input.gap_missed_entry_result,
                )
                effective_trigger = effective_outcome.effective_trigger
                policy_failures += tuple(effective_outcome.failures)
                policy_warnings += tuple(effective_outcome.warnings)
                if effective_trigger is None:
                    effective_trigger = _default_effective_trigger(engine_input, base_candidate)
                validation = _merge_validation(validation, effective_trigger.validation)
        formula_policy_seconds = perf_counter() - eval_started

        result_started = perf_counter()
        failures = tuple(issue.failure for issue in validation.issues) + policy_failures
        warnings = tuple(dict.fromkeys(policy_warnings + _warnings_for_input(engine_input)))
        entry_status = _entry_status(validation, base_candidate, effective_trigger)
        downstream_permission = _downstream_permission(validation, base_candidate, effective_trigger)
        quality = _quality(validation, base_candidate, effective_trigger)
        status = _business_status(validation, downstream_permission)
        evidence_without_hash = EntryEvidence(
            strategy_identity={
                "evaluation_id": engine_input.evaluation_identity.evaluation_id,
                "strategy_instance_id": engine_input.evaluation_identity.strategy_instance_id,
                "strategy_definition_id": engine_input.evaluation_identity.strategy_definition_id,
                "strategy_version": engine_input.evaluation_identity.strategy_version,
                "position_cycle_id": engine_input.position_cycle_identity.position_cycle_id,
                "configuration_hash": engine_input.resolved_configuration_hash,
            },
            policy_key=engine_input.entry_policy_key,
            product=engine_input.product,
            branch=engine_input.resolved_branch,
            resolved_instrument=engine_input.resolved_instrument,
            formula_descriptor=engine_input.formula_descriptor,
            input_references=engine_input.references,
            base_entry=base_candidate,
            gap_missed_entry_dependency=_gap_dependency(engine_input),
            effective_entry=effective_trigger,
            validation=validation,
            warnings=warnings,
            failures=failures,
            quality=quality,
            provenance=engine_input.provenance,
            deterministic_hash="",
        )
        result_construction_seconds = perf_counter() - result_started

        hash_started = perf_counter()
        deterministic_hash = entry_hash(evidence_without_hash)
        hash_seconds = perf_counter() - hash_started
        evidence = replace(evidence_without_hash, deterministic_hash=deterministic_hash)
        serialize_started = perf_counter()
        serialized_size = len(entry_hash(evidence).encode("utf-8")) + len(str(evidence.to_decision_evidence_fragment()).encode("utf-8"))
        serialization_seconds = perf_counter() - serialize_started

        metrics = EntryMetrics(
            validation_seconds=validation_seconds,
            policy_resolution_seconds=policy_resolution_seconds,
            formula_policy_evaluation_seconds=formula_policy_seconds,
            result_construction_seconds=result_construction_seconds,
            evidence_serialization_seconds=serialization_seconds,
            deterministic_hash_seconds=hash_seconds,
            serialized_result_size_bytes=serialized_size,
            input_reference_count=len(engine_input.references),
            missing_reference_count=sum(1 for ref in engine_input.references if ref.value is None and ref.requirement is EntryReferenceRequirement.REQUIRED),
        )
        return EntryEngineResult(
            engine_id=self.engine_id,
            status=status,
            entry_status=entry_status,
            quality=quality,
            validation=validation,
            base_entry=base_candidate,
            effective_entry=effective_trigger,
            downstream_permission=downstream_permission,
            evidence=evidence,
            warnings=warnings,
            failures=failures,
            metrics=metrics,
            deterministic_hash=deterministic_hash,
            provenance=engine_input.provenance,
        )


def validate_entry_input(engine_input: EntryEngineInput) -> EntryValidation:
    issues: list[EntryValidationIssue] = []
    if not engine_input.evaluation_identity.evaluation_id.strip():
        issues.append(_issue(EntryFailure.MISSING_STRATEGY_IDENTITY, "evaluation_identity", "strategy evaluation identity is required"))
    if not engine_input.position_cycle_identity.position_cycle_id.strip():
        issues.append(_issue(EntryFailure.MISSING_POSITION_CYCLE_IDENTITY, "position_cycle_identity", "position cycle identity is required"))
    if not engine_input.resolved_configuration_hash.strip():
        issues.append(_issue(EntryFailure.MISSING_RESOLVED_CONFIGURATION_HASH, "resolved_configuration_hash", "resolved configuration hash is required"))
    if not engine_input.entry_policy_key.strip():
        issues.append(_issue(EntryFailure.MISSING_ENTRY_POLICY, "entry_policy_key", "entry policy key is required"))
    if engine_input.product not in set(TFISProductType):
        issues.append(_issue(EntryFailure.UNSUPPORTED_PRODUCT, "product", "unsupported product"))
    if engine_input.resolved_branch.product is not engine_input.product:
        issues.append(_issue(EntryFailure.POLICY_COMPOSITION_MISMATCH, "resolved_branch.product", "branch product must match input product"))
    if engine_input.resolved_instrument is None:
        issues.append(_issue(EntryFailure.MISSING_RESOLVED_INSTRUMENT, "resolved_instrument", "resolved instrument or selected contract is required"))
    if engine_input.product in {TFISProductType.OPTION_BUYING, TFISProductType.OPTION_SELLING}:
        if engine_input.resolved_instrument is None or engine_input.resolved_instrument.strike is None or not engine_input.resolved_instrument.option_type:
            issues.append(_issue(EntryFailure.MISSING_SELECTED_OPTION_CONTRACT, "resolved_instrument", "option products require a selected option contract before base entry"))
    if engine_input.formula_descriptor is None:
        issues.append(_issue(EntryFailure.MISSING_FORMULA_DESCRIPTOR, "formula_descriptor", "formula descriptor is required"))
    if engine_input.evaluation_timestamp.tzinfo is None or engine_input.evaluation_timestamp.utcoffset() is None:
        issues.append(_issue(EntryFailure.TIMESTAMP_CHRONOLOGY_INVALID, "evaluation_timestamp", "evaluation timestamp must be timezone-aware"))
    if engine_input.evaluation_identity.evaluation_timestamp.tzinfo is None or engine_input.evaluation_identity.evaluation_timestamp.utcoffset() is None:
        issues.append(_issue(EntryFailure.TIMESTAMP_CHRONOLOGY_INVALID, "evaluation_identity.evaluation_timestamp", "identity evaluation timestamp must be timezone-aware"))
    if engine_input.evaluation_identity.evaluation_timestamp > engine_input.evaluation_timestamp:
        issues.append(_issue(EntryFailure.TIMESTAMP_CHRONOLOGY_INVALID, "evaluation_timestamp", "engine evaluation timestamp cannot precede identity timestamp"))
    if engine_input.resolved_branch.trigger_direction in {EntryTriggerDirection.UNKNOWN, EntryTriggerDirection.NOT_APPLICABLE}:
        issues.append(_issue(EntryFailure.INVALID_TRIGGER_DIRECTION, "resolved_branch.trigger_direction", "trigger direction must be explicit"))
    if engine_input.resolved_branch.order_side is None:
        issues.append(_issue(EntryFailure.INVALID_ORDER_SIDE, "resolved_branch.order_side", "order side must be explicit"))
    issues.extend(_reference_issues(engine_input))
    return EntryValidation(tuple(issues), engine_input.unresolved_semantics)


def validate_effective_entry_inputs(
    engine_input: EntryEngineInput,
    base_candidate: EntryBaseCandidate,
) -> EntryValidation:
    issues: list[EntryValidationIssue] = []
    gme = engine_input.gap_missed_entry_result
    if engine_input.gap_missed_entry_required and gme is None:
        issues.append(_issue(EntryFailure.GAP_MISSED_ENTRY_REQUIRED_BUT_MISSING, "gap_missed_entry_result", "Gap/Missed-Entry result is required"))
    if gme is not None and gme.status is not BusinessEngineStatus.PASSED:
        issues.append(_issue(EntryFailure.GAP_MISSED_ENTRY_BLOCKED, "gap_missed_entry_result.status", "Gap/Missed-Entry result is blocked"))
    if gme is not None and gme.recalculation.status is RecalculationStatus.REQUIRED and gme.recalculation.downstream_action is RecalculationDownstreamAction.DEFER_TO_ENTRY_ENGINE:
        if not gme.recalculation.compatibility_outputs:
            issues.append(_issue(EntryFailure.RECALCULATION_REQUIRED_BUT_MISSING, "gap_missed_entry_result.recalculation", "required recalculation output is missing"))
    if base_candidate.value is None or base_candidate.value <= Decimal("0"):
        issues.append(_issue(EntryFailure.INVALID_ENTRY_VALUE, "base_candidate.value", "base entry value must be positive"))
    return EntryValidation(tuple(issues), ())


def _reference_issues(engine_input: EntryEngineInput) -> tuple[EntryValidationIssue, ...]:
    issues: list[EntryValidationIssue] = []
    seen: dict[str, EntryReferenceSource] = {}
    for ref in engine_input.references:
        if ref.reference_id in seen and seen[ref.reference_id] is not ref.source:
            issues.append(_issue(EntryFailure.AMBIGUOUS_REFERENCE_IDENTITY, "references", "reference id maps to multiple sources"))
        seen[ref.reference_id] = ref.source
        if ref.requirement is EntryReferenceRequirement.REQUIRED and ref.value is None:
            issues.append(_issue(EntryFailure.MISSING_REFERENCE, ref.reference_id, "required entry reference is missing"))
        if ref.quality is EntryQuality.INVALID:
            issues.append(_issue(EntryFailure.STALE_REFERENCE_EVIDENCE, ref.reference_id, "reference quality is invalid"))
    return tuple(issues)


def _default_effective_trigger(
    engine_input: EntryEngineInput,
    base_candidate: EntryBaseCandidate,
) -> EntryEffectiveTrigger:
    gme = engine_input.gap_missed_entry_result
    if gme is None:
        status = EntryStatus.EFFECTIVE_ENTRY_EQUALS_BASE
        gap_status = "NOT_APPLICABLE"
        recalc_status = None
        warnings = (EntryWarning.GAP_MISSED_ENTRY_NOT_APPLICABLE,)
    elif gme.missed_entry.status is MissedEntryState.NOT_MISSED:
        status = EntryStatus.ENTRY_NOT_MISSED
        gap_status = gme.missed_entry.status.value
        recalc_status = gme.recalculation.status.value
        warnings = ()
    elif gme.missed_entry.status is MissedEntryState.MISSED:
        status = EntryStatus.ENTRY_MISSED
        gap_status = gme.missed_entry.status.value
        recalc_status = gme.recalculation.status.value
        warnings = ()
    else:
        status = EntryStatus.EFFECTIVE_ENTRY_EQUALS_BASE
        gap_status = gme.missed_entry.status.value
        recalc_status = gme.recalculation.status.value
        warnings = ()
    return EntryEffectiveTrigger(
        value=base_candidate.value,
        status=status,
        source=EntrySource.BASE_POLICY,
        trigger_condition=base_candidate.trigger_condition,
        base_candidate=base_candidate,
        gap_missed_entry_status=gap_status,
        recalculation_status=recalc_status,
        quality=base_candidate.quality,
        validation=EntryValidation(),
        downstream_permission=base_candidate.downstream_permission,
        warnings=warnings,
        failures=(),
        provenance=base_candidate.provenance,
    )


def _entry_status(
    validation: EntryValidation,
    base_candidate: EntryBaseCandidate | None,
    effective_trigger: EntryEffectiveTrigger | None,
) -> EntryStatus:
    if not validation.passed:
        return EntryStatus.BLOCKED
    if effective_trigger is not None:
        return effective_trigger.status
    if base_candidate is not None:
        return EntryStatus.BASE_ENTRY_READY
    return EntryStatus.UNAVAILABLE


def _downstream_permission(
    validation: EntryValidation,
    base_candidate: EntryBaseCandidate | None,
    effective_trigger: EntryEffectiveTrigger | None,
) -> EntryDownstreamPermission:
    if not validation.passed:
        return EntryDownstreamPermission.BLOCKED
    if effective_trigger is not None:
        return effective_trigger.downstream_permission
    if base_candidate is not None:
        return base_candidate.downstream_permission
    return EntryDownstreamPermission.BLOCKED


def _quality(
    validation: EntryValidation,
    base_candidate: EntryBaseCandidate | None,
    effective_trigger: EntryEffectiveTrigger | None,
) -> EntryQuality:
    if not validation.passed:
        return EntryQuality.INVALID
    if effective_trigger is not None:
        return effective_trigger.quality
    if base_candidate is not None:
        return base_candidate.quality
    return EntryQuality.INVALID


def _business_status(
    validation: EntryValidation,
    downstream_permission: EntryDownstreamPermission,
) -> BusinessEngineStatus:
    if not validation.passed or downstream_permission is EntryDownstreamPermission.BLOCKED:
        return BusinessEngineStatus.BLOCKED
    if downstream_permission is EntryDownstreamPermission.NOT_APPLICABLE:
        return BusinessEngineStatus.NOT_APPLICABLE
    return BusinessEngineStatus.PASSED


def _gap_dependency(engine_input: EntryEngineInput) -> Mapping[str, object]:
    gme = engine_input.gap_missed_entry_result
    if gme is None:
        return MappingProxyType({"required": engine_input.gap_missed_entry_required, "status": "NOT_SUPPLIED"})
    return MappingProxyType(
        {
            "required": engine_input.gap_missed_entry_required,
            "status": gme.status.value,
            "missed_entry": gme.missed_entry.status.value,
            "recalculation": gme.recalculation.status.value,
            "downstream_action": gme.recalculation.downstream_action.value,
        }
    )


def _warnings_for_input(engine_input: EntryEngineInput) -> tuple[EntryWarning, ...]:
    warnings: list[EntryWarning] = []
    if engine_input.unresolved_semantics:
        warnings.append(EntryWarning.UNRESOLVED_RULE_PRESENT)
    return tuple(warnings)


def _append_issue(
    validation: EntryValidation,
    failure: EntryFailure,
    field: str,
    message: str,
) -> EntryValidation:
    return EntryValidation(
        validation.issues + (_issue(failure, field, message),),
        validation.unresolved_semantics,
    )


def _merge_validation(left: EntryValidation, right: EntryValidation) -> EntryValidation:
    return EntryValidation(
        left.issues + right.issues,
        left.unresolved_semantics + right.unresolved_semantics,
    )


def _issue(failure: EntryFailure, field: str, message: str) -> EntryValidationIssue:
    return EntryValidationIssue(failure=failure, field=field, message=message)

