from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tfis.adapters.legacy_policies import (
    LegacyPolicyParityCase,
    S23GapPolicyAdapter,
    S23MissedEntryPolicyAdapter,
    load_saved_paper_prelude_evidence,
    load_strategy_policy_composition_config,
    policy_selection_for_strategy,
    run_legacy_policy_parity,
)
from tfis.decision import GapPolicyInput, MissedEntryPolicyInput
from tfis.decision import TFISDecisionEngine
from tfis.domain import (
    MonthlyStatus,
    Segment,
    TFISProductType,
    TFISRuntimeInput,
    TFISTradeResult,
    product_type_from_segment,
)
from tfis.domain.market_levels import MarketLevels
from tfis.importers import load_strategy_rule
from tfis.paper import (
    EventEnvelope,
    OptionChainContract,
    OptionChainSnapshotEvent,
    PaperEventType,
)
from tfis.adapters.legacy_policies.composition import LegacyPolicyRegistryFactory
from tfis.strategy import StrategyEvaluator


ROOT = Path(__file__).resolve().parents[2]
S21_ROOT = ROOT / "config" / "strategies" / "options_sell" / "banknifty"
S23_ROOT = ROOT / "config" / "strategies" / "options_sell" / "nifty"
EVALUATED_AT = datetime(2026, 7, 29, 9, 29, 59, tzinfo=ZoneInfo("Asia/Kolkata"))
EXPIRY = date(2026, 8, 6)


S21_BRANCHES = (
    "S21_BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL",
    "S21_BANKNIFTY_OP_SELL_MONTHLY_BEAR_PUT",
    "S21_BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL",
    "S21_BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT",
)

S23_BRANCHES = (
    "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
    "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
    "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
    "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
)

S23_START_STRIKE_CLASSIFICATION = {
    "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D": "PRE_EXISTING_WORKBOOK_VERIFICATION_PENDING_NOT_PHASE_2B_REGRESSION",
    "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL": "PRE_EXISTING_WORKBOOK_VERIFICATION_PENDING_NOT_PHASE_2B_REGRESSION",
    "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT": "PRE_EXISTING_WORKBOOK_VERIFICATION_PENDING_NOT_PHASE_2B_REGRESSION",
    "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT": "PRE_EXISTING_WORKBOOK_VERIFICATION_PENDING_NOT_PHASE_2B_REGRESSION",
}


@pytest.mark.parametrize("folder_name", S21_BRANCHES)
def test_s21_legacy_policy_adapters_match_legacy_actual_branch_output(
    folder_name: str,
) -> None:
    case = _parity_case(S21_ROOT / folder_name, _s21_market_levels(), _s21_runtime_values())

    result = run_legacy_policy_parity(case)

    assert result.passed, result.mismatches
    assert result.generic_decision.trade_result is TFISTradeResult.TRADE
    assert result.generic_decision.product_type is TFISProductType.OPTION_SELLING
    assert result.generic_decision.direction is not None
    assert result.generic_decision.execution_side is not None
    assert result.generic_decision.gap_result["status"] == "NOT_APPLICABLE"
    assert result.generic_decision.missed_entry_result["status"] == "NOT_APPLICABLE"
    assert result.generic_decision.target_policy is not None
    assert result.generic_decision.msl_policy is not None
    assert result.compared_fields["target"][0] == result.compared_fields["target"][1]
    assert (
        result.compared_fields["msl_stoploss"][0]
        == result.compared_fields["msl_stoploss"][1]
    )


@pytest.mark.parametrize("folder_name", S23_BRANCHES)
def test_s23_legacy_policy_adapters_match_legacy_actual_branch_output(
    folder_name: str,
) -> None:
    case = _parity_case(S23_ROOT / folder_name, _s23_market_levels(), _s23_runtime_values())

    result = run_legacy_policy_parity(case)

    assert result.passed, result.mismatches
    assert result.generic_decision.trade_result is TFISTradeResult.TRADE
    assert result.generic_decision.gap_result["status"] == "NOT_APPLICABLE"
    assert result.generic_decision.missed_entry_result["status"] == "NOT_APPLICABLE"
    assert result.generic_decision.target_policy is not None
    assert result.generic_decision.msl_policy is not None
    assert (
        S23_START_STRIKE_CLASSIFICATION[folder_name]
        == "PRE_EXISTING_WORKBOOK_VERIFICATION_PENDING_NOT_PHASE_2B_REGRESSION"
    )


def test_policy_selection_is_external_to_generic_registry() -> None:
    s23 = policy_selection_for_strategy("S23")

    assert s23.policy_selection.product == "legacy.s23.option_selling.product"
    assert s23.policy_selection.entry == "legacy.s23.option_selling.entry"
    assert s23.policy_selection.contract_selection == (
        "legacy.s23.option_selling.contract_selection"
    )
    assert s23.policy_selection.target == "legacy.s23.option_selling.target"
    assert s23.policy_selection.msl == "legacy.s23.option_selling.msl"


def test_strategy_policy_composition_config_validates_explicit_policy_keys() -> None:
    config = load_strategy_policy_composition_config(
        ROOT / "config" / "strategy_policy_composition.yaml"
    )

    selection = config.selection_for_instance("NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT")

    assert config.version == "phase2c"
    assert selection.product == "legacy.s23.option_selling.product"
    assert selection.target == "legacy.s23.option_selling.target"
    assert selection.msl == "legacy.s23.option_selling.msl"


def test_strategy_policy_composition_config_rejects_missing_mandatory_policy(
    tmp_path: Path,
) -> None:
    path = tmp_path / "bad_policy_composition.yaml"
    path.write_text(
        "\n".join(
            (
                "version: bad",
                "strategies:",
                "  TEST_BRANCH:",
                "    strategy_code: S23",
                "    product_policy: legacy.s23.option_selling.product",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing required policies"):
        load_strategy_policy_composition_config(path)


def test_saved_s23_prelude_evidence_inventory_is_captured_but_partial() -> None:
    evidence = load_saved_paper_prelude_evidence(
        ROOT / "tests" / "fixtures" / "paper" / "s23_fyers_prelude.jsonl"
    )

    assert evidence.captured is True
    assert evidence.strategy_branch == "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
    assert evidence.monthly_status == "BEAR"
    assert evidence.trade_plan is not None
    assert evidence.trade_plan["target_price"] == 791.85
    assert evidence.trade_plan["stoploss_price"] == 816.35
    assert evidence.orpt_snapshot is not None
    assert evidence.rc_snapshot is not None
    assert evidence.has_option_chain is False


def test_unknown_monthly_status_fails_closed_before_legacy_adapters_run() -> None:
    rule = load_strategy_rule(S23_ROOT / S23_BRANCHES[0])
    runtime_input = _runtime_input(
        strategy_rule=rule,
        market_levels=_s23_market_levels(),
        runtime_values=_s23_runtime_values(),
        option_chain_snapshot=_option_chain_snapshot(
            rule.symbol,
            rule.option_type,
            22500,
            250.0,
        ),
        monthly_status=MonthlyStatus.UNKNOWN,
    )
    registry = LegacyPolicyRegistryFactory().build(rule)
    selection = policy_selection_for_strategy(rule.strategy_code)

    decision = TFISDecisionEngine(registry.compose(selection.policy_selection)).evaluate(
        runtime_input
    )

    assert decision.trade_result is TFISTradeResult.REJECTED
    assert decision.rejection_reason_code == "MONTHLY_STATUS_UNKNOWN"
    assert decision.intermediate_calculation_evidence["policies_executed"] == ()


def test_s23_gap_and_missed_entry_adapters_preserve_supplied_orpt_rc_evidence() -> None:
    rule = load_strategy_rule(S23_ROOT / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT")
    runtime_input = _runtime_input(
        strategy_rule=rule,
        market_levels=_s23_market_levels(),
        runtime_values=_s23_runtime_values(),
        option_chain_snapshot=_option_chain_snapshot(
            rule.symbol,
            rule.option_type,
            22350.0,
            271.2,
        ),
        monthly_status=MonthlyStatus.BEAR,
        gap_context={
            "orpt_rc_timing": {
                "status": "ENTRY_MISSED_RECALCULATED",
                "reason": "fixture legacy timing recalculation",
            }
        },
    )
    product = object()
    entry = object()

    gap = S23GapPolicyAdapter().evaluate(
        GapPolicyInput(runtime_input, product, entry)
    )
    missed = S23MissedEntryPolicyAdapter().evaluate(
        MissedEntryPolicyInput(runtime_input, product, entry, gap)
    )

    assert gap.status.value == "PASSED"
    assert gap.branch == "ENTRY_MISSED_RECALCULATED"
    assert missed.status.value == "PASSED"
    assert missed.missed is True


def _parity_case(
    strategy_path: Path,
    market_levels: MarketLevels,
    runtime_values: dict[str, object],
) -> LegacyPolicyParityCase:
    rule = load_strategy_rule(strategy_path)
    plan = StrategyEvaluator().evaluate(
        rule,
        market_levels=market_levels,
        runtime_values=runtime_values,
    )
    snapshot = _option_chain_snapshot(
        rule.symbol,
        rule.option_type,
        float(plan.start_strike),
        float(plan.ideal_premium),
    )
    return LegacyPolicyParityCase(
        strategy_rule=rule,
        runtime_input=_runtime_input(
            strategy_rule=rule,
            market_levels=market_levels,
            runtime_values=runtime_values,
            option_chain_snapshot=snapshot,
            monthly_status=rule.allowed_monthly_statuses[0],
        ),
        market_levels=market_levels,
        runtime_values=runtime_values,
        option_chain_snapshot=snapshot,
    )


def _runtime_input(
    *,
    strategy_rule,
    market_levels: MarketLevels,
    runtime_values: dict[str, object],
    option_chain_snapshot: OptionChainSnapshotEvent,
    monthly_status: MonthlyStatus,
    gap_context: dict[str, object] | None = None,
) -> TFISRuntimeInput:
    return TFISRuntimeInput(
        evaluation_id=f"phase2b-{strategy_rule.unique_code}",
        evaluated_at=EVALUATED_AT,
        strategy_code=strategy_rule.strategy_code,
        strategy_version="phase2b-fixture",
        strategy_branch=strategy_rule.unique_code,
        symbol=strategy_rule.symbol,
        segment=strategy_rule.segment,
        product_type=product_type_from_segment(strategy_rule.segment),
        account_id=None,
        lots=1,
        quantity=50 if strategy_rule.symbol == "NIFTY" else 35,
        session_date=EVALUATED_AT.date(),
        session_label="phase2b-offline-parity",
        timezone="Asia/Kolkata",
        price_source="fixture",
        cmp=100.0,
        contract=None,
        monthly_status=monthly_status,
        monthly_status_evidence={
            "source": "phase2b-fixture",
            "preserved_status": monthly_status,
        },
        market_structure_references=_market_level_mapping(market_levels),
        current_week_references={},
        current_month_references={},
        gap_context=gap_context or {},
        option_chain_context=None,
        data_quality={"status": "VALID"},
        provenance={"source": "phase2b-offline-parity"},
        configuration_snapshot={"strategy_unique_code": strategy_rule.unique_code},
        configuration_version="phase2b-fixture",
        runtime_values=runtime_values,
        product_specific={
            "option_chain_snapshot": option_chain_snapshot,
            "expiry_date": EXPIRY,
        },
    )


def _option_chain_snapshot(
    underlying_symbol: str,
    option_type,
    selected_strike: float,
    ltp: float,
) -> OptionChainSnapshotEvent:
    captured = EVALUATED_AT + timedelta(seconds=1)
    return OptionChainSnapshotEvent(
        envelope=EventEnvelope(
            event_type=PaperEventType.OPTION_CHAIN_SNAPSHOT,
            session_date=EVALUATED_AT.date(),
            effective_timestamp=EVALUATED_AT,
            captured_at=captured,
            timezone="Asia/Kolkata",
            source_type="test_fixture",
            source_id="phase2b-parity",
            synthetic_fixture=True,
            normalized_by="phase2b-parity",
        ),
        underlying_symbol=underlying_symbol,
        expiry=EXPIRY,
        contracts=(
            OptionChainContract(
                symbol=f"{underlying_symbol}_{EXPIRY:%Y%m%d}_{int(selected_strike)}",
                option_type=option_type,
                strike=float(selected_strike),
                expiry=EXPIRY,
                bid=ltp - 1.0,
                ask=ltp + 1.0,
                ltp=ltp,
                oi=999999.0,
                volume=1000.0,
            ),
        ),
    )


def _s21_market_levels() -> MarketLevels:
    return MarketLevels(
        d2hh=46200.0,
        d2ll=44800.0,
        d3hh=46500.0,
        d3ll=45000.0,
        current_day_high=46100.0,
        current_day_low=45200.0,
    )


def _s23_market_levels() -> MarketLevels:
    return MarketLevels(
        d2hh=22500.0,
        d2ll=21900.0,
        d3hh=22600.0,
        d3ll=22000.0,
        current_day_high=22400.0,
        current_day_low=22100.0,
    )


def _s21_runtime_values() -> dict[str, object]:
    return {
        "OPT_LEVELS": {
            "OPT_PRV_2DHH": 760.0,
            "OPT_PRV_2DLL": 480.0,
            "OPT_PRV_3DHH": 780.0,
            "OPT_PRV_3DLL": 500.0,
        },
    }


def _s23_runtime_values() -> dict[str, object]:
    return {
        "ENTRY": 200.0,
        "OPT_LEVELS": {
            "OPT_PRV_2DLL": 210.0,
            "OPT_PRV_3DLL": 220.0,
            "OPT_PRV_2DHH": 300.0,
            "OPT_PRV_3DHH": 330.0,
        },
    }


def _market_level_mapping(market_levels: MarketLevels) -> dict[str, float | None]:
    return {
        "previous_month_high": market_levels.previous_month_high,
        "previous_month_low": market_levels.previous_month_low,
        "previous_week_high": market_levels.previous_week_high,
        "previous_week_low": market_levels.previous_week_low,
        "d2hh": market_levels.d2hh,
        "d2ll": market_levels.d2ll,
        "d3hh": market_levels.d3hh,
        "d3ll": market_levels.d3ll,
        "d4hh": market_levels.d4hh,
        "d4ll": market_levels.d4ll,
        "current_day_high": market_levels.current_day_high,
        "current_day_low": market_levels.current_day_low,
    }
