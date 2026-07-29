from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date, datetime, time
import inspect
import json
import pytest

from tfis.domain import (
    APSAction,
    ExpiryType,
    ExitRule,
    LifecyclePlan,
    MonthlyStatus,
    RolloverPolicy,
    Segment,
    StopPlan,
    StrategyExpiryPolicy,
    StrategyRule,
    TargetStep,
    TFISDecision,
    TFISDirection,
    TFISExecutionSide,
    TFISFormulaTrace,
    TFISProductType,
    TFISQuantityEffectType,
    TFISRuntimeInput,
    TFISTradeResult,
    TrailingStopStep,
    product_type_from_segment,
)


def test_runtime_input_does_not_require_option_context_for_futures_or_equity() -> None:
    for segment in (Segment.FUTURES, Segment.EQUITY):
        runtime_input = _runtime_input(segment=segment)

        assert runtime_input.product_type is product_type_from_segment(segment)
        assert runtime_input.option_chain_context is None
        assert runtime_input.contract is None


def test_buy_and_sell_are_valid_execution_sides() -> None:
    assert TFISExecutionSide.BUY.value == "BUY"
    assert TFISExecutionSide.SELL.value == "SELL"


def test_runtime_input_and_decision_are_immutable() -> None:
    runtime_input = _runtime_input()
    decision = _decision()

    with pytest.raises(FrozenInstanceError):
        runtime_input.strategy_code = "MUTATED"  # type: ignore[misc]
    with pytest.raises(TypeError):
        runtime_input.monthly_status_evidence["source"] = "mutated"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        decision.decision_id = "MUTATED"  # type: ignore[misc]
    with pytest.raises(TypeError):
        decision.data_versions["source"] = "mutated"  # type: ignore[index]


def test_paper_replay_serialization_is_deterministic() -> None:
    first = _runtime_input(
        monthly_status_evidence={"b": 2, "a": {"z": 1, "y": 2}},
        runtime_values={"ENTRY": 100.0, "OPT": 55.0},
    )
    second = _runtime_input(
        monthly_status_evidence={"a": {"y": 2, "z": 1}, "b": 2},
        runtime_values={"OPT": 55.0, "ENTRY": 100.0},
    )

    assert first.to_json() == second.to_json()
    assert first.comparison_key() == second.comparison_key()
    assert json.loads(first.to_json())["monthly_status_evidence"]["a"]["z"] == 1


def test_generic_runtime_contract_names_do_not_expose_strategy_assumptions() -> None:
    import tfis.domain.runtime_contracts as runtime_contracts

    names = [
        runtime_contracts.__name__,
        TFISRuntimeInput.__name__,
        TFISDecision.__name__,
        TFISProductType.__name__,
        TFISExecutionSide.__name__,
    ]
    source = inspect.getsource(runtime_contracts)

    assert all("S21" not in name and "S23" not in name for name in names)
    assert "S21" not in source
    assert "S23" not in source


def test_strategy_rule_for_non_option_products_keeps_option_fields_optional() -> None:
    for segment in (Segment.FUTURES, Segment.EQUITY):
        rule = StrategyRule(
            strategy_code="GENERIC_TEST",
            unique_code=f"GENERIC_{segment.value}",
            symbol="TEST",
            segment=segment,
            expiry_policy=StrategyExpiryPolicy(
                expiry_type=ExpiryType.MONTHLY,
                rollover_policy=RolloverPolicy.T_MINUS_1,
            ),
            allowed_monthly_statuses=(MonthlyStatus.BEAR,),
            option_type=None,
            entry_time=time(9, 15),
            recalculation_time=time(9, 30),
            start_strike_formula="CMP",
            end_strike_formula="CMP",
            ideal_premium_formula="CMP",
            minimum_premium_formula="CMP",
            minimum_oi=0,
            entry_formula="CMP",
            target_formula="CMP",
            stoploss_formula="CMP",
            carry_forward_allowed=True,
        )

        assert rule.option_type is None


def test_lifecycle_plan_supports_multiple_targets_and_ordered_tsl_aps_steps() -> None:
    plan = LifecyclePlan(
        plan_id="plan-1",
        product_type=TFISProductType.OPTION_SELLING,
        direction=TFISDirection.SHORT,
        entry_side=TFISExecutionSide.SELL,
        exit_side=TFISExecutionSide.BUY,
        position_quantity=100,
        targets=(
            TargetStep(
                order=1,
                label="target-1",
                target_price=90.0,
                quantity_pct=50.0,
                quantity_effect=TFISQuantityEffectType.PERCENTAGE,
                activation_conditions={"ltp_at_or_below": 90.0},
                formula_trace=TFISFormulaTrace(name="target_1", formula="ENTRY - 25%"),
            ),
            TargetStep(
                order=2,
                label="target-2",
                target_price=75.0,
                quantity_pct=50.0,
                quantity_effect=TFISQuantityEffectType.PERCENTAGE,
                activation_conditions={"ltp_at_or_below": 75.0},
            ),
        ),
        stop_plan=StopPlan(
            label="msl",
            stop_price=130.0,
            activation_conditions={"ltp_at_or_above": 130.0},
        ),
        trailing_stop_steps=(
            TrailingStopStep(
                order=1,
                label="trail-1",
                trigger_conditions={"target_hit": "target-1"},
                stop_price=105.0,
            ),
            TrailingStopStep(
                order=2,
                label="trail-2",
                trigger_conditions={"target_hit": "target-2"},
                stop_price=95.0,
            ),
        ),
        aps_actions=(
            APSAction(
                order=1,
                label="aps-review",
                action_type="REVIEW",
                side=TFISExecutionSide.BUY,
                activation_conditions={"time": "15:00:00"},
            ),
            APSAction(
                order=2,
                label="aps-exit",
                action_type="EXIT",
                side=TFISExecutionSide.BUY,
                quantity_effect=TFISQuantityEffectType.REMAINING,
                activation_conditions={"time": "15:15:00"},
            ),
        ),
        exit_rules=(
            ExitRule(
                order=1,
                label="expiry-force-close",
                side=TFISExecutionSide.BUY,
                activation_conditions={"expiry_day": True},
            ),
        ),
        evidence={"source": "unit"},
    )

    assert len(plan.targets) == 2
    assert tuple(step.order for step in plan.trailing_stop_steps) == (1, 2)
    assert tuple(action.order for action in plan.aps_actions) == (1, 2)
    assert plan.to_json() == plan.comparison_key()
    assert json.loads(plan.to_json())["targets"][0]["quantity_effect"] == "PERCENTAGE"


def test_lifecycle_plan_supports_buy_side_futures_and_equity_without_options() -> None:
    for product_type in (TFISProductType.FUTURES, TFISProductType.EQUITY):
        plan = LifecyclePlan(
            plan_id=f"{product_type.value}-plan",
            product_type=product_type,
            direction=TFISDirection.LONG,
            entry_side=TFISExecutionSide.BUY,
            exit_side=TFISExecutionSide.SELL,
            targets=(),
            trailing_stop_steps=(),
            aps_actions=(),
            exit_rules=(),
        )

        assert plan.product_type is product_type
        assert plan.entry_side is TFISExecutionSide.BUY
        assert plan.exit_side is TFISExecutionSide.SELL


def test_lifecycle_plan_rejects_unordered_tsl_or_aps_steps() -> None:
    with pytest.raises(ValueError):
        LifecyclePlan(
            plan_id="bad-plan",
            product_type=TFISProductType.OPTION_SELLING,
            direction=TFISDirection.SHORT,
            entry_side=TFISExecutionSide.SELL,
            trailing_stop_steps=(
                TrailingStopStep(
                    order=2,
                    label="second",
                    trigger_conditions={"target": 2},
                ),
                TrailingStopStep(
                    order=1,
                    label="first",
                    trigger_conditions={"target": 1},
                ),
            ),
        )


def _runtime_input(
    *,
    segment: Segment = Segment.FUTURES,
    monthly_status_evidence: dict[str, object] | None = None,
    runtime_values: dict[str, object] | None = None,
) -> TFISRuntimeInput:
    return TFISRuntimeInput(
        evaluation_id="eval-1",
        evaluated_at=datetime(2026, 7, 29, 9, 17),
        strategy_code="GENERIC_TEST",
        strategy_version="v1",
        strategy_branch="GENERIC_BRANCH",
        symbol="TEST",
        segment=segment,
        product_type=product_type_from_segment(segment),
        account_id=None,
        lots=1,
        quantity=1,
        session_date=date(2026, 7, 29),
        session_label="morning",
        timezone="Asia/Calcutta",
        price_source="fixture",
        cmp=100.0,
        contract=None,
        monthly_status=None,
        monthly_status_evidence=monthly_status_evidence or {"source": "fixture"},
        market_structure_references={"d2hh": 101.0},
        current_week_references={"CWH": 101.0},
        current_month_references={"CMH": 102.0},
        gap_context={},
        option_chain_context=None,
        data_quality={"status": "ok"},
        provenance={"source": "unit"},
        configuration_snapshot={"version": "v1"},
        configuration_version="v1",
        runtime_values=runtime_values or {},
        product_specific={},
    )


def _decision() -> TFISDecision:
    return TFISDecision(
        evaluation_id="eval-1",
        decision_id="decision-1",
        decided_at=datetime(2026, 7, 29, 9, 17),
        strategy_code="GENERIC_TEST",
        strategy_branch="GENERIC_BRANCH",
        monthly_status_branch="BEAR",
        trade_result=TFISTradeResult.TRADE,
        product_type=TFISProductType.FUTURES,
        direction=TFISDirection.LONG,
        execution_side=TFISExecutionSide.BUY,
        selected_instrument=None,
        entry_calculation=None,
        gap_result={},
        missed_entry_result={},
        lots=1,
        quantity=1,
        target_policy=None,
        msl_policy=None,
        tsl_policy=None,
        aps_policy=None,
        final_exit_rule={},
        rejection_reason_code=None,
        rejection_reason=None,
        intermediate_calculation_evidence={},
        data_versions={"source": "fixture"},
        configuration_versions={"strategy": "v1"},
    )
