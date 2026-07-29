from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from tfis.domain.business_engine import BusinessEngineCapability, BusinessEngineStatus
from tfis.domain.gap_missed_entry import (
    ComparisonOperator,
    CompetingRuleBehavior,
    GapClassification,
    GapClassificationResult,
    GapDirection,
    GapMeasurement,
    GapMissedEntryEngine,
    GapMissedEntryEngineInput,
    GapMissedEntryEvidence,
    GapMissedEntryFailure,
    GapMissedEntryPolicyOutcome,
    GapMissedEntryQuality,
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
    RuleExecutionPermission,
    RuleIssueClassification,
    SessionTimingEvidence,
    TimingObservationRequirement,
    TimingWindowState,
    UnresolvedRuleIssue,
    gap_missed_entry_result_json,
    validate_gap_missed_entry_input,
)
from tfis.domain import TFISProductType, business_engine_catalog_json, load_business_engine_registry


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "config" / "business_engines" / "catalog.yaml"


class FixedPolicy:
    policy_key = "fixture.policy"

    def __init__(self, outcome: GapMissedEntryPolicyOutcome) -> None:
        self.outcome = outcome

    def evaluate(self, engine_input: GapMissedEntryEngineInput) -> GapMissedEntryPolicyOutcome:
        assert engine_input.policy_key == self.policy_key
        return self.outcome


def test_contracts_are_immutable_and_mapping_fields_are_frozen() -> None:
    value = ObservationValue(
        MissedEntryObservationSource.OPTION_HIGH,
        Decimal("0"),
        _dt(9, 25),
        {"source": "fixture"},
    )

    with pytest.raises(FrozenInstanceError):
        value.value = Decimal("1")
    with pytest.raises(TypeError):
        value.provenance["new"] = "blocked"


def test_result_serialization_is_deterministic_and_keeps_null_distinct_from_zero() -> None:
    zero = ObservationValue(MissedEntryObservationSource.OPTION_LOW, Decimal("0"), _dt(9, 25))
    missing = ObservationValue(MissedEntryObservationSource.OPTION_LOW, None, None)
    result = _engine_result(_outcome(MissedEntryObservationSource.OPTION_LOW), _engine_input())

    assert gap_missed_entry_result_json(result) == gap_missed_entry_result_json(result)
    assert '"observed_value":"0"' in gap_missed_entry_result_json(_result_with_observation(zero))
    assert '"observed_value":null' in gap_missed_entry_result_json(_result_with_observation(missing))


def test_gap_and_missed_entry_outputs_are_independent() -> None:
    result = _engine_result(_outcome(MissedEntryObservationSource.OPTION_HIGH), _engine_input())

    assert result.gap.classification is GapClassification.GAP_UP
    assert result.missed_entry.status is MissedEntryState.MISSED
    assert result.gap is not result.missed_entry


def test_orpt_and_rc_can_be_not_applicable() -> None:
    validation = validate_gap_missed_entry_input(_engine_input())

    assert validation.passed is True


def test_required_orpt_or_rc_missing_fails_validation() -> None:
    timing = _timing(
        orpt_requirement=TimingObservationRequirement.REQUIRED,
        rc_requirement=TimingObservationRequirement.REQUIRED,
    )

    result = _engine_result(_outcome(MissedEntryObservationSource.OPTION_LOW), _engine_input(timing=timing))

    assert result.status is BusinessEngineStatus.BLOCKED
    assert GapMissedEntryFailure.REQUIRED_OBSERVATION_MISSING in result.failures


def test_invalid_chronology_fails_closed() -> None:
    timing = _timing(orpt_timestamp=_dt(9, 30), rc_timestamp=_dt(9, 25))

    result = _engine_result(_outcome(MissedEntryObservationSource.OPTION_LOW), _engine_input(timing=timing))

    assert result.status is BusinessEngineStatus.BLOCKED
    assert GapMissedEntryFailure.INVALID_TIMING_ORDER in result.failures


def test_comparison_source_operator_and_reference_are_explicit() -> None:
    result = _engine_result(_outcome(MissedEntryObservationSource.OPTION_HIGH), _engine_input())
    rule = result.missed_entry.comparison_rule

    assert rule is not None
    assert rule.observed_source is MissedEntryObservationSource.OPTION_HIGH
    assert rule.operator is ComparisonOperator.LESS_THAN
    assert rule.reference_key == "entry_price"


def test_option_low_and_option_high_semantics_are_both_representable() -> None:
    low_result = _engine_result(_outcome(MissedEntryObservationSource.OPTION_LOW), _engine_input())
    high_result = _engine_result(_outcome(MissedEntryObservationSource.OPTION_HIGH), _engine_input())

    assert low_result.missed_entry.comparison_rule is not None
    assert high_result.missed_entry.comparison_rule is not None
    assert low_result.missed_entry.comparison_rule.observed_source is MissedEntryObservationSource.OPTION_LOW
    assert high_result.missed_entry.comparison_rule.observed_source is MissedEntryObservationSource.OPTION_HIGH


def test_generic_engine_uses_policy_result_without_selecting_between_competing_rules() -> None:
    low_outcome = _outcome(MissedEntryObservationSource.OPTION_LOW)
    high_outcome = _outcome(MissedEntryObservationSource.OPTION_HIGH)

    assert GapMissedEntryEngine(FixedPolicy(low_outcome)).execute(_engine_input()).missed_entry == low_outcome.missed_entry
    assert GapMissedEntryEngine(FixedPolicy(high_outcome)).execute(_engine_input()).missed_entry == high_outcome.missed_entry


def test_unresolved_s23_put_semantics_fail_closed_and_retain_ambiguity() -> None:
    unresolved = UnresolvedRuleIssue(
        issue_code="S23_PUT_MISSED_ENTRY_COMPARISON_UNRESOLVED",
        classification=RuleIssueClassification.USER_CLARIFICATION_REQUIRED,
        affected_strategy_definition_id="s23-weekly-option-selling",
        affected_strategy_version="1.0.0",
        affected_branch="PUT",
        competing_observed_behaviors=(
            CompetingRuleBehavior(
                "legacy_backtest_put_low_comparison",
                MissedEntryObservationSource.OPTION_LOW,
                ComparisonOperator.LESS_THAN,
                "backtest",
            ),
            CompetingRuleBehavior(
                "legacy_paper_live_put_high_comparison",
                MissedEntryObservationSource.OPTION_HIGH,
                ComparisonOperator.LESS_THAN,
                "paper_live_timing_audit",
            ),
        ),
        authoritative_source_status=RuleIssueClassification.WORKBOOK_VERIFICATION_REQUIRED,
        execution_permission=RuleExecutionPermission.FAIL_CLOSED,
        fail_closed_reason="authoritative comparison source is unresolved",
    )

    result = _engine_result(
        _outcome(MissedEntryObservationSource.OPTION_LOW),
        _engine_input(unresolved_issues=(unresolved,)),
    )

    assert result.status is BusinessEngineStatus.BLOCKED
    assert result.validation.passed is False
    assert result.evidence.unresolved_issues[0].competing_observed_behaviors[0].observed_source is MissedEntryObservationSource.OPTION_LOW
    assert result.evidence.unresolved_issues[0].competing_observed_behaviors[1].observed_source is MissedEntryObservationSource.OPTION_HIGH


def test_recalculation_is_downstream_instruction_and_target_stop_fields_are_outside_engine() -> None:
    recalc = _outcome(MissedEntryObservationSource.OPTION_LOW).recalculation
    field_names = {field.name for field in fields(RecalculationInstruction)}

    assert recalc.status is RecalculationStatus.REQUIRED
    assert recalc.downstream_action is RecalculationDownstreamAction.DEFER_TO_ENTRY_ENGINE
    assert {"target", "fsl", "trp", "msl", "tsl", "aps"}.isdisjoint(field_names)


def test_catalog_dependencies_validate_with_gap_providing_missed_entry_capability() -> None:
    registry = load_business_engine_registry(CATALOG)
    gap = registry.get("gap")
    entry = registry.get("entry")

    assert BusinessEngineCapability.GAP in gap.provided_capabilities
    assert BusinessEngineCapability.MISSED_ENTRY in gap.provided_capabilities
    assert BusinessEngineCapability.MISSED_ENTRY in entry.required_capabilities
    assert business_engine_catalog_json(registry) == business_engine_catalog_json(load_business_engine_registry(CATALOG))


def test_evidence_fragment_retains_timing_gap_missed_recalc_policy_and_unresolved_metadata() -> None:
    result = _engine_result(_outcome(MissedEntryObservationSource.OPTION_HIGH), _engine_input())
    fragment = result.evidence.to_decision_evidence_fragment()

    assert fragment["engine_id"] == "gap"
    assert fragment["evidence"]["timing"]["timezone"] == "Asia/Kolkata"
    assert fragment["evidence"]["gap"]["classification"] == "GAP_UP"
    assert fragment["evidence"]["missed_entry"]["comparison_rule"]["observed_source"] == "OPTION_HIGH"
    assert fragment["evidence"]["recalculation"]["downstream_action"] == "DEFER_TO_ENTRY_ENGINE"
    assert fragment["evidence"]["formula_references"] == ["workbook.gap.fixture", "workbook.recalc.fixture"]


def _engine_result(
    outcome: GapMissedEntryPolicyOutcome,
    engine_input: GapMissedEntryEngineInput,
):
    return GapMissedEntryEngine(FixedPolicy(outcome)).execute(engine_input)


def _result_with_observation(observation: ObservationValue):
    outcome = _outcome(observation.source)
    outcome = GapMissedEntryPolicyOutcome(
        gap=outcome.gap,
        missed_entry=MissedEntryClassificationResult(
            applicable=True,
            status=MissedEntryState.MISSED,
            comparison_rule=outcome.missed_entry.comparison_rule,
            observed_value=observation.value,
            entry_reference_value=Decimal("100"),
            branch_key="fixture_branch",
            direction=GapDirection.DOWN,
        ),
        recalculation=outcome.recalculation,
    )
    return _engine_result(outcome, _engine_input())


def _outcome(source: MissedEntryObservationSource) -> GapMissedEntryPolicyOutcome:
    gap_reference = GapReference("previous_close", Decimal("100"), MissedEntryObservationSource.UNDERLYING_CLOSE)
    gap_observation = GapObservation(
        applicable=True,
        opening_price=ObservationValue(MissedEntryObservationSource.UNDERLYING_OPEN, Decimal("103"), _dt(9, 15)),
        reference=gap_reference,
        policy_key="fixture.policy",
    )
    rule = MissedEntryComparisonRule(
        rule_id="fixture_missed_entry_rule",
        observed_source=source,
        operator=ComparisonOperator.LESS_THAN,
        reference_key="entry_price",
        branch_key="fixture_branch",
        policy_key="fixture.policy",
    )
    return GapMissedEntryPolicyOutcome(
        gap=GapClassificationResult(
            applicable=True,
            classification=GapClassification.GAP_UP,
            direction=GapDirection.UP,
            observation=gap_observation,
            measurement=GapMeasurement(Decimal("3"), Decimal("3"), ComparisonOperator.GREATER_THAN, Decimal("1")),
            formula_reference="workbook.gap.fixture",
            requirement_reference="REQ.GAP",
            quality=GapMissedEntryQuality.VALID,
        ),
        missed_entry=MissedEntryClassificationResult(
            applicable=True,
            status=MissedEntryState.MISSED,
            comparison_rule=rule,
            observed_value=Decimal("95"),
            entry_reference_value=Decimal("100"),
            branch_key="fixture_branch",
            direction=GapDirection.DOWN,
        ),
        recalculation=RecalculationInstruction(
            applicable=True,
            status=RecalculationStatus.REQUIRED,
            branch_key="fixture_branch",
            required_input_refs=("current_day_high", "current_day_low"),
            supplied_values={"current_day_high": Decimal("110"), "current_day_low": Decimal("94")},
            policy_key="fixture.policy",
            formula_reference="workbook.recalc.fixture",
            requirement_reference="REQ.RECALC",
            downstream_action=RecalculationDownstreamAction.DEFER_TO_ENTRY_ENGINE,
        ),
        provenance={"policy": "fixture.policy"},
    )


def _engine_input(
    *,
    timing: SessionTimingEvidence | None = None,
    unresolved_issues: tuple[UnresolvedRuleIssue, ...] = (),
) -> GapMissedEntryEngineInput:
    return GapMissedEntryEngineInput(
        strategy_family_id="option_selling",
        strategy_definition_id="fixture-strategy",
        strategy_version="1.0.0",
        strategy_instance_id="fixture-instance",
        product_type=TFISProductType.OPTION_SELLING,
        resolved_configuration_hash="hash",
        policy_key="fixture.policy",
        timing=timing or _timing(),
        monthly_status="BULLISH",
        market_structure_refs={"prv_2d_hh": "ms.prv_2d_hh"},
        entry_reference_value=Decimal("100"),
        policy_configuration={
            "required_market_structure_refs": ("prv_2d_hh",),
            "supported_monthly_statuses": ("BULLISH", "BEARISH"),
        },
        unresolved_issues=unresolved_issues,
    )


def _timing(
    *,
    orpt_requirement: TimingObservationRequirement = TimingObservationRequirement.NOT_APPLICABLE,
    rc_requirement: TimingObservationRequirement = TimingObservationRequirement.NOT_APPLICABLE,
    orpt_timestamp: datetime | None = None,
    rc_timestamp: datetime | None = None,
) -> SessionTimingEvidence:
    return SessionTimingEvidence(
        timezone="Asia/Kolkata",
        market_open_timestamp=_dt(9, 15),
        orpt_timestamp=orpt_timestamp,
        rc_timestamp=rc_timestamp,
        evaluation_timestamp=_dt(9, 31),
        source_event_timestamp=_dt(9, 30),
        processing_timestamp=_dt(9, 31, 1),
        timing_window_state=TimingWindowState.AVAILABLE,
        orpt_requirement=orpt_requirement,
        rc_requirement=rc_requirement,
    )


def _dt(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 7, 29, hour, minute, second, tzinfo=timezone.utc)
