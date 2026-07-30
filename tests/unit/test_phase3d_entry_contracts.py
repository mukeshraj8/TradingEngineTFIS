from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from tfis.domain import (
    EntryBaseCandidate,
    EntryDownstreamPermission,
    EntryEffectiveTrigger,
    EntryEngineInput,
    EntryFailure,
    EntryFormulaComponent,
    EntryFormulaDescriptor,
    EntryFormulaOperandRole,
    EntryFormulaOperator,
    EntryInstrumentType,
    EntryMarketBias,
    EntryOptionRight,
    EntryPositionIntent,
    EntryQuality,
    EntryReference,
    EntryReferenceRequirement,
    EntryReferenceSource,
    EntryReferenceValueType,
    EntryResolvedBranch,
    EntryRoundingRule,
    EntrySource,
    EntryStatus,
    EntryTriggerCondition,
    EntryTriggerDirection,
    EntryValidation,
    EntryWarning,
    PositionCycleIdentity,
    StrategyEvaluationIdentity,
    TFISContractIdentity,
    TFISExecutionSide,
    TFISProductType,
    entry_engine_result_json,
)
from tfis.domain.business_engine import BusinessEngineStatus
from tfis.domain.gap_missed_entry import (
    ComparisonOperator,
    GapClassification,
    GapClassificationResult,
    GapDirection,
    GapMeasurement,
    GapMissedEntryEngineResult,
    GapMissedEntryEvidence,
    GapMissedEntryQuality,
    GapMissedEntryValidation,
    GapObservation,
    GapReference,
    MissedEntryClassificationResult,
    MissedEntryComparisonRule,
    MissedEntryObservationSource,
    MissedEntryState,
    ObservationValue,
    RecalculationDownstreamAction,
    RecalculationInstruction,
    RecalculationStatus,
    SessionTimingEvidence,
    TimingWindowState,
)
from tfis.entry import EntryEngine


class FixtureEntryPolicy:
    policy_key = "fixture.entry"

    def __init__(self, *, recalculated: Decimal | None = None) -> None:
        self.recalculated = recalculated

    def evaluate_base(self, engine_input: EntryEngineInput):
        return _outcome(base_candidate=_base_candidate(engine_input, Decimal("100.25")))

    def finalize_effective(
        self,
        engine_input: EntryEngineInput,
        base_candidate: EntryBaseCandidate,
        gap_missed_entry_result: GapMissedEntryEngineResult | None,
    ):
        if self.recalculated is not None:
            trigger = EntryEffectiveTrigger(
                value=self.recalculated,
                status=EntryStatus.EFFECTIVE_ENTRY_RECALCULATED,
                source=EntrySource.GAP_MISSED_ENTRY_RECALCULATION,
                trigger_condition=base_candidate.trigger_condition,
                base_candidate=base_candidate,
                gap_missed_entry_status=MissedEntryState.MISSED.value,
                recalculation_status=RecalculationStatus.COMPLETED_BY_COMPATIBILITY_POLICY.value,
                quality=EntryQuality.VALID,
                validation=EntryValidation(),
                downstream_permission=EntryDownstreamPermission.PERMITTED,
            )
            return _outcome(base_candidate=base_candidate, effective_trigger=trigger)
        return _outcome(base_candidate=base_candidate)


def test_entry_contracts_are_immutable_and_reference_mappings_are_frozen() -> None:
    ref = _reference("selected_3dll", EntryReferenceSource.SELECTED_OPTION_CONTRACT, Decimal("100"))

    with pytest.raises(FrozenInstanceError):
        ref.reference_id = "changed"
    with pytest.raises(TypeError):
        ref.provenance["new"] = "blocked"


def test_deterministic_serialization_preserves_decimal_and_null_vs_zero() -> None:
    result = _engine().execute(_input(references=(_reference("zero", EntryReferenceSource.ENTRY_VALUE, Decimal("0")),)))
    missing = _engine().execute(
        _input(references=(_reference("missing", EntryReferenceSource.ENTRY_VALUE, None, EntryReferenceRequirement.OPTIONAL),))
    )

    assert entry_engine_result_json(result) == entry_engine_result_json(result)
    assert '"value":"0"' in entry_engine_result_json(result)
    assert '"value":null' in entry_engine_result_json(missing)
    assert result.base_entry is not None
    assert result.base_entry.value == Decimal("100.25")


def test_reference_identity_distinguishes_underlying_and_selected_option_references() -> None:
    underlying = _reference("previous_2dhh", EntryReferenceSource.UNDERLYING_SPOT, Decimal("100"))
    selected = _reference("previous_2dhh", EntryReferenceSource.SELECTED_OPTION_CONTRACT, Decimal("10"))

    result = _engine().execute(_input(references=(underlying, selected)))

    assert result.status is BusinessEngineStatus.BLOCKED
    assert EntryFailure.AMBIGUOUS_REFERENCE_IDENTITY in result.failures


def test_percentage_base_is_explicit_per_component() -> None:
    descriptor = _formula(
        components=(
            EntryFormulaComponent(
                "left",
                EntryFormulaOperandRole.LEFT_OPERAND,
                EntryReferenceSource.SELECTED_OPTION_CONTRACT,
                EntryFormulaOperator.ADD,
                reference_id="selected_2dhh",
            ),
            EntryFormulaComponent(
                "pct",
                EntryFormulaOperandRole.PERCENTAGE_BASE,
                EntryReferenceSource.FINAL_STRIKE_VALUE,
                EntryFormulaOperator.ADD,
                percentage_value=Decimal("5"),
                percentage_base_reference_id="final_strike",
                rounding_rule=EntryRoundingRule.NONE,
            ),
        )
    )

    result = _engine().execute(_input(formula_descriptor=descriptor))

    assert result.status is BusinessEngineStatus.PASSED
    assert result.evidence.formula_descriptor is not None
    assert result.evidence.formula_descriptor.components[1].percentage_base_reference_id == "final_strike"


def test_base_entry_success_and_effective_entry_equals_base_without_gap() -> None:
    result = _engine().execute(_input())

    assert result.status is BusinessEngineStatus.PASSED
    assert result.entry_status is EntryStatus.EFFECTIVE_ENTRY_EQUALS_BASE
    assert result.effective_entry is not None
    assert result.effective_entry.value == Decimal("100.25")
    assert result.downstream_permission is EntryDownstreamPermission.PERMITTED


def test_base_entry_fails_closed_for_unknown_policy() -> None:
    result = EntryEngine({}).execute(_input())

    assert result.status is BusinessEngineStatus.BLOCKED
    assert result.entry_status is EntryStatus.BLOCKED
    assert EntryFailure.UNKNOWN_ENTRY_POLICY in result.failures


def test_effective_entry_recalculated_from_supplied_policy_output() -> None:
    result = _engine(recalculated=Decimal("104.50")).execute(_input(gap_missed_entry_result=_gme(MissedEntryState.MISSED)))

    assert result.status is BusinessEngineStatus.PASSED
    assert result.entry_status is EntryStatus.EFFECTIVE_ENTRY_RECALCULATED
    assert result.effective_entry is not None
    assert result.effective_entry.value == Decimal("104.50")


def test_recalculation_required_but_missing_fails_closed() -> None:
    result = _engine().execute(_input(gap_missed_entry_result=_gme(MissedEntryState.MISSED, recalc_required=True)))

    assert result.status is BusinessEngineStatus.BLOCKED
    assert EntryFailure.RECALCULATION_REQUIRED_BUT_MISSING in result.failures


def test_gap_missed_entry_blocked_fails_closed() -> None:
    blocked = replace(_gme(MissedEntryState.NOT_MISSED), status=BusinessEngineStatus.BLOCKED)

    result = _engine().execute(_input(gap_missed_entry_result=blocked, gap_required=True))

    assert result.status is BusinessEngineStatus.BLOCKED
    assert EntryFailure.GAP_MISSED_ENTRY_BLOCKED in result.failures


def test_not_applicable_gap_missed_entry_is_supported() -> None:
    result = _engine().execute(_input(gap_missed_entry_result=_gme(MissedEntryState.NOT_APPLICABLE)))

    assert result.status is BusinessEngineStatus.PASSED
    assert result.evidence.gap_missed_entry_dependency["missed_entry"] == "NOT_APPLICABLE"


def test_missing_selected_contract_for_options_fails_closed() -> None:
    result = _engine().execute(_input(resolved_instrument=TFISContractIdentity(symbol="NIFTY")))

    assert result.status is BusinessEngineStatus.BLOCKED
    assert EntryFailure.MISSING_SELECTED_OPTION_CONTRACT in result.failures


def test_resolved_future_instrument_is_valid_without_selected_option_contract() -> None:
    branch = EntryResolvedBranch(
        market_bias=EntryMarketBias.BULLISH,
        strategy_branch="long_future",
        product=TFISProductType.FUTURES,
        instrument_type=EntryInstrumentType.UNDERLYING_FUTURE,
        option_right=EntryOptionRight.NOT_APPLICABLE,
        position_intent=EntryPositionIntent.LONG_FUTURE,
        order_side=TFISExecutionSide.BUY,
        trigger_direction=EntryTriggerDirection.PRICE_AT_OR_ABOVE,
    )
    result = _engine().execute(
        _input(
            product=TFISProductType.FUTURES,
            branch=branch,
            resolved_instrument=TFISContractIdentity(symbol="NIFTY_FUT", product_type=TFISProductType.FUTURES),
            references=(_reference("future_1dhh", EntryReferenceSource.UNDERLYING_FUTURE, Decimal("100")),),
        )
    )

    assert result.status is BusinessEngineStatus.PASSED


def test_timezone_validation_requires_aware_timestamp() -> None:
    result = _engine().execute(_input(evaluation_timestamp=datetime(2026, 7, 30, 9, 20)))

    assert result.status is BusinessEngineStatus.BLOCKED
    assert EntryFailure.TIMESTAMP_CHRONOLOGY_INVALID in result.failures


def test_deterministic_output_hash_is_stable() -> None:
    first = _engine().execute(_input())
    second = _engine().execute(_input())

    assert first.deterministic_hash == second.deterministic_hash
    assert first.evidence.deterministic_hash == first.deterministic_hash


def _outcome(
    *,
    base_candidate: EntryBaseCandidate | None,
    effective_trigger: EntryEffectiveTrigger | None = None,
):
    from tfis.domain import EntryPolicyOutcome

    return EntryPolicyOutcome(
        status=effective_trigger.status if effective_trigger is not None else EntryStatus.BASE_ENTRY_READY,
        base_candidate=base_candidate,
        effective_trigger=effective_trigger,
    )


def _engine(*, recalculated: Decimal | None = None) -> EntryEngine:
    policy = FixtureEntryPolicy(recalculated=recalculated)
    return EntryEngine({policy.policy_key: policy})


def _input(
    *,
    product: TFISProductType = TFISProductType.OPTION_SELLING,
    branch: EntryResolvedBranch | None = None,
    resolved_instrument: TFISContractIdentity | None = None,
    formula_descriptor: EntryFormulaDescriptor | None = None,
    references: tuple[EntryReference, ...] | None = None,
    gap_missed_entry_result: GapMissedEntryEngineResult | None = None,
    gap_required: bool = False,
    evaluation_timestamp: datetime | None = None,
) -> EntryEngineInput:
    timestamp = evaluation_timestamp or datetime(2026, 7, 30, 9, 20, tzinfo=timezone.utc)
    identity = StrategyEvaluationIdentity.deterministic(
        strategy_instance_id="instance-A",
        strategy_definition_id="definition-A",
        strategy_version="1.0.0",
        trading_date=date(2026, 7, 30),
        evaluation_timestamp=timestamp,
        evaluation_sequence=1,
        trigger_type="fixture",
        configuration_hash="hash-A",
    )
    cycle = PositionCycleIdentity.deterministic(
        strategy_instance_id="instance-A",
        trading_date=date(2026, 7, 30),
        cycle_sequence=1,
        entry_evaluation_id=identity.evaluation_id,
        product_instrument_identity="instrument-A",
    )
    return EntryEngineInput(
        evaluation_identity=identity,
        position_cycle_identity=cycle,
        resolved_configuration_hash="hash-A",
        product=product,
        resolved_branch=branch or _branch(product),
        resolved_instrument=resolved_instrument or TFISContractIdentity(
            symbol="NIFTY_OPT",
            product_type=product,
            strike=22000.0,
            option_type="PE",
        ),
        entry_policy_key="fixture.entry",
        formula_descriptor=formula_descriptor or _formula(),
        references=references if references is not None else (_reference("selected_3dll", EntryReferenceSource.SELECTED_OPTION_CONTRACT, Decimal("100")),),
        strategy_parameters={"entry_discount_pct": "7.5"},
        evaluation_timestamp=timestamp,
        gap_missed_entry_result=gap_missed_entry_result,
        gap_missed_entry_required=gap_required,
        provenance={"source": "synthetic"},
    )


def _branch(product: TFISProductType) -> EntryResolvedBranch:
    return EntryResolvedBranch(
        market_bias=EntryMarketBias.BEARISH,
        strategy_branch="fixture_branch",
        product=product,
        instrument_type=EntryInstrumentType.SELECTED_OPTION_CONTRACT,
        option_right=EntryOptionRight.PUT,
        position_intent=EntryPositionIntent.SHORT_OPTION,
        order_side=TFISExecutionSide.SELL,
        trigger_direction=EntryTriggerDirection.PRICE_AT_OR_BELOW,
    )


def _reference(
    reference_id: str,
    source: EntryReferenceSource,
    value: Decimal | None,
    requirement: EntryReferenceRequirement = EntryReferenceRequirement.REQUIRED,
) -> EntryReference:
    return EntryReference(
        reference_id=reference_id,
        source=source,
        instrument_id="instrument-A",
        segment="OPTIONS",
        product=TFISProductType.OPTION_SELLING,
        reference_type="PRV_3DLL",
        lookback="3D",
        value=value,
        value_type=EntryReferenceValueType.PRICE,
        event_timestamp=datetime(2026, 7, 30, 9, 19, tzinfo=timezone.utc),
        effective_date=date(2026, 7, 30),
        provenance={"source": "synthetic"},
        quality=EntryQuality.VALID,
        requirement=requirement,
    )


def _formula(
    *,
    components: tuple[EntryFormulaComponent, ...] | None = None,
) -> EntryFormulaDescriptor:
    return EntryFormulaDescriptor(
        formula_id="fixture_formula",
        formula_reference="fixture:entry",
        formula_family="selected_contract_reference_minus_percentage",
        components=components or (
            EntryFormulaComponent(
                "left",
                EntryFormulaOperandRole.LEFT_OPERAND,
                EntryReferenceSource.SELECTED_OPTION_CONTRACT,
                EntryFormulaOperator.SUBTRACT,
                reference_id="selected_3dll",
                formula_reference="fixture:entry",
            ),
        ),
        requirement_references=("REQ-ENTRY-FIXTURE",),
    )


def _base_candidate(engine_input: EntryEngineInput, value: Decimal) -> EntryBaseCandidate:
    return EntryBaseCandidate(
        value=value,
        source=EntrySource.BASE_POLICY,
        trigger_condition=EntryTriggerCondition(
            trigger_direction=engine_input.resolved_branch.trigger_direction,
            comparison_value=value,
            order_side=engine_input.resolved_branch.order_side,
            position_intent=engine_input.resolved_branch.position_intent,
            reference_id="selected_3dll",
        ),
        formula_descriptor=engine_input.formula_descriptor,
        component_evidence=engine_input.formula_descriptor.components,
        quality=EntryQuality.VALID,
        validation=EntryValidation(),
        downstream_permission=EntryDownstreamPermission.PERMITTED,
        warnings=(EntryWarning.COMPATIBILITY_ONLY,),
        provenance={"policy": "fixture"},
    )


def _gme(
    status: MissedEntryState,
    *,
    recalc_required: bool = False,
) -> GapMissedEntryEngineResult:
    timing = SessionTimingEvidence(
        timezone="UTC",
        market_open_timestamp=None,
        evaluation_timestamp=datetime(2026, 7, 30, 9, 20, tzinfo=timezone.utc),
        source_event_timestamp=datetime(2026, 7, 30, 9, 19, tzinfo=timezone.utc),
        processing_timestamp=datetime(2026, 7, 30, 9, 21, tzinfo=timezone.utc),
        timing_window_state=TimingWindowState.AVAILABLE,
    )
    gap = GapClassificationResult(
        applicable=False,
        classification=GapClassification.NOT_APPLICABLE,
        direction=GapDirection.NOT_APPLICABLE,
        observation=GapObservation(False, None, None, "fixture.gap"),
        measurement=GapMeasurement(None, None, ComparisonOperator.NOT_APPLICABLE),
        quality=GapMissedEntryQuality.NOT_APPLICABLE,
    )
    missed = MissedEntryClassificationResult(
        applicable=status is not MissedEntryState.NOT_APPLICABLE,
        status=status,
        comparison_rule=MissedEntryComparisonRule(
            "fixture",
            MissedEntryObservationSource.OPTION_LOW,
            ComparisonOperator.LESS_THAN,
            "entry",
            "fixture_branch",
            "fixture.gap",
        ),
        observed_value=Decimal("95"),
        entry_reference_value=Decimal("100.25"),
        branch_key="fixture_branch",
        direction=GapDirection.DOWN,
    )
    recalc = RecalculationInstruction(
        applicable=recalc_required,
        status=RecalculationStatus.REQUIRED if recalc_required else RecalculationStatus.NOT_REQUIRED,
        downstream_action=RecalculationDownstreamAction.DEFER_TO_ENTRY_ENGINE if recalc_required else RecalculationDownstreamAction.NONE,
    )
    evidence = GapMissedEntryEvidence(timing, gap, missed, recalc)
    return GapMissedEntryEngineResult(
        engine_id="gap",
        status=BusinessEngineStatus.PASSED,
        quality=GapMissedEntryQuality.VALID,
        validation=GapMissedEntryValidation(),
        gap=gap,
        missed_entry=missed,
        recalculation=recalc,
        evidence=evidence,
    )
