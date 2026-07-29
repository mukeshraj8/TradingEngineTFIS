from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from tfis.adapters.legacy_policies.gap_missed_entry import (
    GapMissedEntryPolicyResolutionError,
    LegacyGapMissedEntryEvaluationInput,
    S21_COMPATIBILITY_POLICY_KEY,
    S21_UNRESOLVED_TIMING_POLICY_KEY,
    S23_BACKTEST_LOW_POLICY_KEY,
    S23_BEAR_CALL_BRANCH,
    S23_BEAR_PUT_BRANCH,
    S23_BULL_CALL_BRANCH,
    S23_BULL_PUT_BRANCH,
    S23_PAPER_LIVE_HIGH_POLICY_KEY,
    S23_UNRESOLVED_POLICY_KEY,
    evaluate_legacy_gap_missed_entry,
    gap_missed_entry_engine_input_from_legacy,
    load_legacy_gap_missed_entry_composition_config,
    resolve_legacy_gap_missed_entry_policy,
)
from tfis.backtest import EntryMissedInput, S23EntryMissedDetector
from tfis.domain import (
    MonthlyStatus,
    OptionType,
    TFISProductType,
    TradePlan,
)
from tfis.domain.gap_missed_entry import (
    GapClassification,
    GapMissedEntryFailure,
    MissedEntryObservationSource,
    MissedEntryState,
    ObservationValue,
    RecalculationDownstreamAction,
    RecalculationStatus,
    RuleExecutionPermission,
    SessionTimingEvidence,
    TimingObservationRequirement,
    TimingWindowState,
)
from tfis.domain.market_levels import MarketLevels
from tfis.strategy.s23_recalculation import (
    IntradaySnapshot,
    RecalculationInput,
    S23RecalculationEngine,
)


ROOT = Path(__file__).resolve().parents[2]
COMPOSITION = ROOT / "config" / "strategy_policy_composition.yaml"


@pytest.mark.parametrize("policy_key", (S21_COMPATIBILITY_POLICY_KEY, S21_UNRESOLVED_TIMING_POLICY_KEY))
def test_s21_profiles_declare_timing_applicability_without_inference(policy_key: str) -> None:
    result = evaluate_legacy_gap_missed_entry(_s21_input(), policy_key=policy_key)

    assert result.gap.classification is (
        GapClassification.NOT_APPLICABLE
        if policy_key == S21_COMPATIBILITY_POLICY_KEY
        else GapClassification.INVALID
    )
    assert result.evidence.timing.orpt_requirement is TimingObservationRequirement.NOT_APPLICABLE
    if policy_key == S21_UNRESOLVED_TIMING_POLICY_KEY:
        assert result.validation.passed is False
        assert result.evidence.unresolved_issues[0].execution_permission is RuleExecutionPermission.FAIL_CLOSED
    else:
        assert result.validation.passed is True
        assert result.missed_entry.status is MissedEntryState.NOT_APPLICABLE


@pytest.mark.parametrize(
    ("branch", "option_type", "monthly_status"),
    (
        (S23_BULL_CALL_BRANCH, OptionType.CALL, MonthlyStatus.BULL),
        (S23_BEAR_CALL_BRANCH, OptionType.CALL, MonthlyStatus.BEAR),
        (S23_BULL_PUT_BRANCH, OptionType.PUT, MonthlyStatus.BULL_CF),
        (S23_BEAR_PUT_BRANCH, OptionType.PUT, MonthlyStatus.BEAR_CF),
    ),
)
def test_s23_supported_branches_represent_normal_not_missed_path(
    branch: str,
    option_type: OptionType,
    monthly_status: MonthlyStatus,
) -> None:
    result = evaluate_legacy_gap_missed_entry(
        _s23_input(branch, option_type, monthly_status, orpt_option_low=214, orpt_option_high=228, entry=203.5),
        policy_key=S23_BACKTEST_LOW_POLICY_KEY,
    )

    assert result.validation.passed is True
    assert result.missed_entry.status is MissedEntryState.NOT_MISSED
    assert result.recalculation.status is RecalculationStatus.NOT_REQUIRED
    assert result.evidence.provenance["policy_key"] == S23_BACKTEST_LOW_POLICY_KEY


def test_s23_gap_up_and_gap_down_are_represented_from_supplied_current_day_refs() -> None:
    gap_up = evaluate_legacy_gap_missed_entry(
        _s23_input(S23_BULL_CALL_BRANCH, OptionType.CALL, MonthlyStatus.BULL, current_day_high=225, current_day_low=205, entry=203.5),
        policy_key=S23_BACKTEST_LOW_POLICY_KEY,
    )
    gap_down = evaluate_legacy_gap_missed_entry(
        _s23_input(S23_BEAR_CALL_BRANCH, OptionType.CALL, MonthlyStatus.BEAR, current_day_high=195, current_day_low=180, entry=203.5),
        policy_key=S23_BACKTEST_LOW_POLICY_KEY,
    )

    assert gap_up.gap.classification is GapClassification.GAP_UP
    assert gap_down.gap.classification is GapClassification.GAP_DOWN


def test_s23_missed_entry_recalculation_matches_existing_legacy_engine() -> None:
    compatibility_input = _s23_input(
        S23_BEAR_PUT_BRANCH,
        OptionType.PUT,
        MonthlyStatus.BEAR_CF,
        orpt_option_low=190,
        orpt_option_high=200,
        rc_option_low=206,
        rc_option_high=232,
        entry=203.5,
    )
    result = evaluate_legacy_gap_missed_entry(
        compatibility_input,
        policy_key=S23_BACKTEST_LOW_POLICY_KEY,
    )
    legacy = S23RecalculationEngine().recalculate(
        RecalculationInput(
            branch_unique_code=S23_BEAR_PUT_BRANCH,
            option_type=OptionType.PUT,
            monthly_status=MonthlyStatus.BEAR_CF,
            base_trade_plan=_trade_plan(OptionType.PUT, 203.5),
            market_levels=compatibility_input.market_levels,
            option_levels=dict(compatibility_input.option_levels),
            parameters=dict(compatibility_input.strategy_parameters),
            intraday_snapshot_at_orpt=compatibility_input.orpt_snapshot,
            intraday_snapshot_at_recalc=compatibility_input.rc_snapshot,
            entry_missed=True,
        )
    )

    assert result.missed_entry.status is MissedEntryState.MISSED
    assert result.recalculation.status is RecalculationStatus.COMPLETED_BY_COMPATIBILITY_POLICY
    assert result.recalculation.downstream_action is RecalculationDownstreamAction.USE_COMPATIBILITY_OUTPUT
    assert result.recalculation.compatibility_outputs["recalculated_entry_price"] == Decimal(str(legacy.recalculated_entry_price))
    assert result.recalculation.compatibility_outputs["recalculated_start_strike"] == Decimal(str(legacy.recalculated_start_strike))


@pytest.mark.parametrize(
    "override",
    (
        {"orpt": None},
        {"rc": None},
        {"chronology": "invalid"},
        {"entry": None},
        {"monthly_status": MonthlyStatus.UNKNOWN},
        {"branch": "UNSUPPORTED_BRANCH"},
    ),
)
def test_s23_fail_closed_for_missing_or_invalid_evidence(override: dict[str, object]) -> None:
    compatibility_input = _s23_input(
        str(override.get("branch") or S23_BULL_CALL_BRANCH),
        OptionType.CALL,
        override.get("monthly_status") or MonthlyStatus.BULL,
        entry=override.get("entry", 203.5),
        include_orpt=override.get("orpt", "present") is not None,
        include_rc=override.get("rc", "present") is not None,
        invalid_chronology=override.get("chronology") == "invalid",
    )

    result = evaluate_legacy_gap_missed_entry(compatibility_input, policy_key=S23_BACKTEST_LOW_POLICY_KEY)

    assert result.validation.passed is False
    assert result.failures


def test_s23_missing_option_observation_fails_closed() -> None:
    compatibility_input = _s23_input(
        S23_BULL_CALL_BRANCH,
        OptionType.CALL,
        MonthlyStatus.BULL,
        orpt_option_low=None,
    )

    result = evaluate_legacy_gap_missed_entry(compatibility_input, policy_key=S23_BACKTEST_LOW_POLICY_KEY)

    assert result.validation.passed is False
    assert GapMissedEntryFailure.REQUIRED_OBSERVATION_MISSING in result.failures


def test_s23_put_profiles_remain_separate_and_can_differ_on_same_candle() -> None:
    compatibility_input = _s23_input(
        S23_BEAR_PUT_BRANCH,
        OptionType.PUT,
        MonthlyStatus.BEAR_CF,
        orpt_option_low=190,
        orpt_option_high=210,
        entry=203.5,
    )

    low = evaluate_legacy_gap_missed_entry(compatibility_input, policy_key=S23_BACKTEST_LOW_POLICY_KEY)
    high = evaluate_legacy_gap_missed_entry(compatibility_input, policy_key=S23_PAPER_LIVE_HIGH_POLICY_KEY)

    assert low.missed_entry.comparison_rule.observed_source is MissedEntryObservationSource.OPTION_LOW
    assert high.missed_entry.comparison_rule.observed_source is MissedEntryObservationSource.OPTION_HIGH
    assert low.missed_entry.status is MissedEntryState.MISSED
    assert high.missed_entry.status is MissedEntryState.NOT_MISSED
    assert low.missed_entry.comparison_rule.operator.value == "LESS_THAN"
    assert high.missed_entry.comparison_rule.operator.value == "LESS_THAN"


def test_unresolved_s23_put_profile_fails_closed_and_records_both_observed_behaviors() -> None:
    result = evaluate_legacy_gap_missed_entry(
        _s23_input(S23_BEAR_PUT_BRANCH, OptionType.PUT, MonthlyStatus.BEAR_CF),
        policy_key=S23_UNRESOLVED_POLICY_KEY,
    )

    assert result.validation.passed is False
    assert GapMissedEntryFailure.UNRESOLVED_COMPARISON_POLICY in result.failures
    sources = {
        behavior.observed_source
        for behavior in result.evidence.unresolved_issues[0].competing_observed_behaviors
    }
    assert sources == {MissedEntryObservationSource.OPTION_LOW, MissedEntryObservationSource.OPTION_HIGH}


def test_backtest_low_profile_matches_existing_entry_missed_detector() -> None:
    compatibility_input = _s23_input(
        S23_BULL_PUT_BRANCH,
        OptionType.PUT,
        MonthlyStatus.BULL_CF,
        orpt_option_low=190,
        orpt_option_high=210,
        entry=203.5,
    )
    result = evaluate_legacy_gap_missed_entry(compatibility_input, policy_key=S23_BACKTEST_LOW_POLICY_KEY)
    legacy = S23EntryMissedDetector().detect(
        EntryMissedInput(
            option_type=OptionType.PUT,
            entry_price=203.5,
            orpt_snapshot=compatibility_input.orpt_snapshot,
        )
    )

    assert result.missed_entry.status is MissedEntryState.MISSED
    assert legacy.entry_missed is True
    assert result.missed_entry.observed_value == Decimal(str(legacy.compared_value))


def test_policy_resolution_uses_definition_and_version_without_defaults(tmp_path: Path) -> None:
    config = load_legacy_gap_missed_entry_composition_config(COMPOSITION)

    s23 = config.policy_for_definition_version("S23_NIFTY_OP_SELL_WK_DIFF_2D_3D", "1.0.0")
    policy = resolve_legacy_gap_missed_entry_policy(
        config,
        strategy_definition_id="S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
        strategy_version="1.0.0",
        strategy_family_id="option_selling",
    )

    assert s23.policy_key == S23_PAPER_LIVE_HIGH_POLICY_KEY
    assert policy.policy_key == S23_PAPER_LIVE_HIGH_POLICY_KEY
    with pytest.raises(GapMissedEntryPolicyResolutionError):
        resolve_legacy_gap_missed_entry_policy(config, strategy_definition_id="option_selling", strategy_version="1.0.0", strategy_family_id="option_selling")
    with pytest.raises(GapMissedEntryPolicyResolutionError):
        resolve_legacy_gap_missed_entry_policy(config, strategy_definition_id="S23_NIFTY_OP_SELL_WK_DIFF_2D_3D", strategy_version="9.9.9")

    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
version: bad
identity_compositions:
  S23_NIFTY_OP_SELL_WK_DIFF_2D_3D@1.0.0:
    gap_missed_entry_policy: legacy.s23.gap_missed_entry.unresolved_put_v1
""",
        encoding="utf-8",
    )
    with pytest.raises(GapMissedEntryPolicyResolutionError, match="unresolved executable"):
        load_legacy_gap_missed_entry_composition_config(bad)


def test_adapter_mapping_preserves_identity_values_and_null_entry() -> None:
    engine_input = gap_missed_entry_engine_input_from_legacy(
        _s23_input(S23_BULL_CALL_BRANCH, OptionType.CALL, MonthlyStatus.BULL, entry=None),
        policy_key=S23_BACKTEST_LOW_POLICY_KEY,
    )

    assert engine_input.strategy_definition_id == "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D"
    assert engine_input.strategy_version == "1.0.0"
    assert engine_input.strategy_instance_id == "S23_NIFTY_ACCOUNT_A_PAPER"
    assert engine_input.entry_reference_value is None


def test_evidence_fragment_serialization_contains_profile_and_comparison_details() -> None:
    result = evaluate_legacy_gap_missed_entry(
        _s23_input(S23_BEAR_PUT_BRANCH, OptionType.PUT, MonthlyStatus.BEAR_CF, orpt_option_low=190, entry=203.5),
        policy_key=S23_BACKTEST_LOW_POLICY_KEY,
    )
    fragment = result.evidence.to_decision_evidence_fragment()

    assert result.to_json() == result.to_json()
    assert fragment["evidence"]["missed_entry"]["comparison_rule"]["observed_source"] == "OPTION_LOW"
    assert fragment["evidence"]["missed_entry"]["comparison_rule"]["operator"] == "LESS_THAN"
    assert fragment["evidence"]["recalculation"]["compatibility_outputs"]["recalculated_entry_price"] is not None
    assert "target" not in fragment["evidence"]["recalculation"]["compatibility_outputs"]
    assert "fsl" not in fragment["evidence"]["recalculation"]["compatibility_outputs"]
    assert "trp" not in fragment["evidence"]["recalculation"]["compatibility_outputs"]


def _s21_input() -> LegacyGapMissedEntryEvaluationInput:
    return LegacyGapMissedEntryEvaluationInput(
        strategy_family_id="option_selling",
        strategy_definition_id="S21_BANKNIFTY_OP_SELL_MONTHLY",
        strategy_version="1.0.0",
        strategy_instance_id="S21_BANKNIFTY_ACCOUNT_A_PAPER",
        product_type=TFISProductType.OPTION_SELLING,
        configuration_hash="s21-hash",
        branch_key="S21_BULL_CALL",
        option_type=OptionType.CALL,
        monthly_status=MonthlyStatus.BULL,
        timing=_timing(TimingObservationRequirement.NOT_APPLICABLE, TimingObservationRequirement.NOT_APPLICABLE),
        base_entry_price=Decimal("100"),
    )


def _s23_input(
    branch: str,
    option_type: OptionType,
    monthly_status: MonthlyStatus | str,
    *,
    orpt_option_low: float | None = 214,
    orpt_option_high: float = 228,
    rc_option_low: float = 210,
    rc_option_high: float = 232,
    current_day_high: float = 22400,
    current_day_low: float = 22100,
    entry: object = 203.5,
    include_orpt: bool = True,
    include_rc: bool = True,
    invalid_chronology: bool = False,
) -> LegacyGapMissedEntryEvaluationInput:
    orpt = IntradaySnapshot(_dt(9, 24, 59), 22120, 22380, orpt_option_low, orpt_option_high)
    rc_time = _dt(9, 20, 0) if invalid_chronology else _dt(9, 29, 59)
    rc = IntradaySnapshot(rc_time, 21850, 22620, rc_option_low, rc_option_high)
    return LegacyGapMissedEntryEvaluationInput(
        strategy_family_id="option_selling",
        strategy_definition_id="S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
        strategy_version="1.0.0",
        strategy_instance_id="S23_NIFTY_ACCOUNT_A_PAPER",
        product_type=TFISProductType.OPTION_SELLING,
        configuration_hash="s23-hash",
        branch_key=branch,
        option_type=option_type,
        monthly_status=monthly_status,
        timing=_timing(
            TimingObservationRequirement.REQUIRED,
            TimingObservationRequirement.REQUIRED,
            orpt_snapshot=orpt if include_orpt else None,
            rc_snapshot=rc if include_rc else None,
            current_day_high=current_day_high,
            current_day_low=current_day_low,
        ),
        base_entry_price=entry,
        market_levels=_market_levels(current_day_high=current_day_high, current_day_low=current_day_low),
        option_levels={"OPT_PRV_2DLL": 208, "OPT_PRV_3DLL": 214},
        strategy_parameters=_parameters(),
        base_trade_plan=_trade_plan(option_type, float(entry) if entry is not None else 203.5),
        orpt_snapshot=orpt if include_orpt else None,
        rc_snapshot=rc if include_rc else None,
        provenance={"fixture": "phase3c"},
    )


def _replace_timing(
    compatibility_input: LegacyGapMissedEntryEvaluationInput,
    *,
    orpt_observation_source: MissedEntryObservationSource,
) -> LegacyGapMissedEntryEvaluationInput:
    timing = SessionTimingEvidence(
        timezone=compatibility_input.timing.timezone,
        market_open_timestamp=compatibility_input.timing.market_open_timestamp,
        evaluation_timestamp=compatibility_input.timing.evaluation_timestamp,
        source_event_timestamp=compatibility_input.timing.source_event_timestamp,
        processing_timestamp=compatibility_input.timing.processing_timestamp,
        timing_window_state=compatibility_input.timing.timing_window_state,
        orpt_requirement=compatibility_input.timing.orpt_requirement,
        rc_requirement=compatibility_input.timing.rc_requirement,
        orpt_timestamp=compatibility_input.timing.orpt_timestamp,
        rc_timestamp=compatibility_input.timing.rc_timestamp,
        orpt_observation=ObservationValue(orpt_observation_source, Decimal("1"), compatibility_input.timing.orpt_timestamp),
        rc_observation=compatibility_input.timing.rc_observation,
        current_day_high=compatibility_input.timing.current_day_high,
        current_day_low=compatibility_input.timing.current_day_low,
    )
    return LegacyGapMissedEntryEvaluationInput(
        strategy_family_id=compatibility_input.strategy_family_id,
        strategy_definition_id=compatibility_input.strategy_definition_id,
        strategy_version=compatibility_input.strategy_version,
        strategy_instance_id=compatibility_input.strategy_instance_id,
        product_type=compatibility_input.product_type,
        configuration_hash=compatibility_input.configuration_hash,
        branch_key=compatibility_input.branch_key,
        option_type=compatibility_input.option_type,
        monthly_status=compatibility_input.monthly_status,
        timing=timing,
        base_entry_price=compatibility_input.base_entry_price,
        market_levels=compatibility_input.market_levels,
        option_levels=compatibility_input.option_levels,
        strategy_parameters=compatibility_input.strategy_parameters,
        base_trade_plan=compatibility_input.base_trade_plan,
        orpt_snapshot=compatibility_input.orpt_snapshot,
        rc_snapshot=compatibility_input.rc_snapshot,
        provenance=compatibility_input.provenance,
    )


def _timing(
    orpt_requirement: TimingObservationRequirement,
    rc_requirement: TimingObservationRequirement,
    *,
    orpt_snapshot: IntradaySnapshot | None = None,
    rc_snapshot: IntradaySnapshot | None = None,
    current_day_high: float | None = None,
    current_day_low: float | None = None,
) -> SessionTimingEvidence:
    return SessionTimingEvidence(
        timezone="Asia/Kolkata",
        market_open_timestamp=_dt(9, 15),
        evaluation_timestamp=_dt(9, 31),
        source_event_timestamp=_dt(9, 30),
        processing_timestamp=_dt(9, 31, 1),
        timing_window_state=TimingWindowState.AVAILABLE,
        orpt_requirement=orpt_requirement,
        rc_requirement=rc_requirement,
        orpt_timestamp=orpt_snapshot.timestamp if orpt_snapshot else None,
        rc_timestamp=rc_snapshot.timestamp if rc_snapshot else None,
        orpt_observation=_snapshot_observation(orpt_snapshot, MissedEntryObservationSource.OPTION_LOW),
        rc_observation=(
            ObservationValue(MissedEntryObservationSource.OPTION_LOW, Decimal(str(rc_snapshot.option_low)), rc_snapshot.timestamp)
            if rc_snapshot
            else None
        ),
        current_day_high=(
            ObservationValue(MissedEntryObservationSource.CURRENT_DAY_HIGH, Decimal(str(current_day_high)), _dt(9, 30))
            if current_day_high is not None
            else None
        ),
        current_day_low=(
            ObservationValue(MissedEntryObservationSource.CURRENT_DAY_LOW, Decimal(str(current_day_low)), _dt(9, 30))
            if current_day_low is not None
            else None
        ),
    )


def _trade_plan(option_type: OptionType, entry: float) -> TradePlan:
    return TradePlan(
        strategy_code="S23",
        symbol="NIFTY",
        option_type=option_type,
        start_strike=23100,
        end_strike=21999,
        ideal_premium=264,
        minimum_premium=198,
        entry_price=entry,
        stoploss_price=320,
        target_price=80,
    )


def _market_levels(*, current_day_high: float = 22400, current_day_low: float = 22100) -> MarketLevels:
    return MarketLevels(
        d2hh=22500,
        d2ll=22100,
        d3hh=22600,
        d3ll=22000,
        current_day_high=current_day_high,
        current_day_low=current_day_low,
    )


def _parameters() -> dict[str, float]:
    return {
        "strike_buffer_pct": 5,
        "ideal_premium_pct": 1.20,
        "minimum_premium_pct": 0.90,
        "entry_discount_pct": 7.5,
    }


def _snapshot_observation(
    snapshot: IntradaySnapshot | None,
    source: MissedEntryObservationSource,
) -> ObservationValue | None:
    if snapshot is None:
        return None
    if source is MissedEntryObservationSource.OPTION_LOW and snapshot.option_low is not None:
        return ObservationValue(source, Decimal(str(snapshot.option_low)), snapshot.timestamp)
    if source is MissedEntryObservationSource.OPTION_HIGH and snapshot.option_high is not None:
        return ObservationValue(source, Decimal(str(snapshot.option_high)), snapshot.timestamp)
    return None


def _dt(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 5, 23, hour, minute, second, tzinfo=timezone.utc)
