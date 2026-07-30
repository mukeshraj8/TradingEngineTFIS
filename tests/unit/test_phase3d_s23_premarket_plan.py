from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from tfis.adapters.legacy_policies import s23_call_captured_evidence as m5
from tfis.adapters.legacy_policies import s23_premarket_plan as premarket
from tfis.adapters.legacy_policies import s23_vertical_slice as vertical
from tfis.decision import MSLPolicyResult, PolicyStatus, TargetPolicyResult
from tfis.domain import BusinessEngineStatus, EntryFailure, MonthlyStatus, PreMarketPlanStatus
from tfis.premarket import PreMarketPlanningContext, PreMarketStrategyPlanBuilder


BULL_M3_HASH = "4d2e514f05f873c17b7077ce6710c559dac54422ed6898cbb51e6ed9bbb24b84"
BULL_M5_HASH = "4e327a977aeaad6841891b2a044155ca8a1f644c1b11a261e255252506deaa1c"
BEAR_M5_HASH = "3a8dbc6b507ac7603f2c0a4b289f3ecf9855f17206b3d96744b3291af8f20d41"


def test_bull_call_premarket_plan_is_prepared() -> None:
    plan = premarket.build_s23_bull_call_premarket_plan()

    assert plan.plan_status is PreMarketPlanStatus.PREPARED
    assert plan.strategy_family == "S23"
    assert plan.monthly_status is MonthlyStatus.BULL
    assert plan.resolved_branch == "NIFTY_OP_SELL_WK_DIFF_2D_3D"
    assert plan.contract_resolution.selected_contract.symbol == "NIFTY_20260806_22250_CALL"
    assert plan.contract_resolution.selected_expiry.isoformat() == "2026-08-06"
    assert plan.contract_resolution.selected_strike == 22250.0
    assert plan.contract_resolution.premium == 264.0
    assert plan.contract_resolution.oi == 999999.0
    assert plan.planned_values.base_entry == 203.5
    assert plan.planned_values.preliminary_target == 81.4
    assert plan.planned_values.preliminary_msl == 321.0
    assert plan.planned_values.normal_orpt.isoformat() == "09:19:59"
    assert plan.planned_values.rc_time.isoformat() == "09:29:59"
    assert plan.execution_permission == "NONE"


def test_bear_call_premarket_plan_is_prepared() -> None:
    plan = premarket.build_s23_bear_call_premarket_plan()

    assert plan.plan_status is PreMarketPlanStatus.PREPARED
    assert plan.monthly_status is MonthlyStatus.BEAR
    assert plan.resolved_branch == "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL"
    assert plan.contract_resolution.selected_contract.symbol == "NIFTY_20260806_22150_CALL"
    assert plan.contract_resolution.selected_strike == 22150.0
    assert plan.contract_resolution.premium == 262.8
    assert plan.planned_values.base_entry == 194.25
    assert plan.planned_values.preliminary_target == 77.7
    assert plan.planned_values.preliminary_msl == 310.8


def test_bull_and_bear_use_the_same_generic_builder(monkeypatch) -> None:
    calls: list[str] = []
    original = PreMarketStrategyPlanBuilder.build

    def observe(self, runtime_input, resolved_strategy_configuration, planning_context, stage_policies):
        calls.append(type(self).__name__)
        return original(self, runtime_input, resolved_strategy_configuration, planning_context, stage_policies)

    monkeypatch.setattr(PreMarketStrategyPlanBuilder, "build", observe)

    premarket.build_s23_bull_call_premarket_plan()
    premarket.build_s23_bear_call_premarket_plan()

    assert calls == ["PreMarketStrategyPlanBuilder", "PreMarketStrategyPlanBuilder"]


def test_premarket_plan_is_deterministic_for_bull_and_bear() -> None:
    assert premarket.build_s23_bull_call_premarket_plan().to_json() == premarket.build_s23_bull_call_premarket_plan().to_json()
    assert premarket.build_s23_bear_call_premarket_plan().to_json() == premarket.build_s23_bear_call_premarket_plan().to_json()
    assert premarket.build_s23_bull_call_premarket_plan().plan_hash == premarket.build_s23_bull_call_premarket_plan().plan_hash
    assert premarket.build_s23_bear_call_premarket_plan().plan_hash == premarket.build_s23_bear_call_premarket_plan().plan_hash


def test_premarket_plan_is_immutable() -> None:
    plan = premarket.build_s23_bull_call_premarket_plan()

    with pytest.raises(FrozenInstanceError):
        plan.plan_status = PreMarketPlanStatus.BLOCKED_PREMARKET


def test_plan_hash_changes_for_material_input_change() -> None:
    case = vertical.build_s23_bull_call_vertical_case()
    changed = replace(case, runtime_input=replace(case.runtime_input, quantity=100))

    assert premarket.build_s23_call_side_premarket_plan(case).plan_hash != premarket.build_s23_call_side_premarket_plan(changed).plan_hash


def test_missing_monthly_status_blocks() -> None:
    case = vertical.build_s23_bear_call_vertical_case()
    blocked = replace(case, runtime_input=replace(case.runtime_input, monthly_status=None))

    plan = premarket.build_s23_call_side_premarket_plan(blocked)

    assert plan.plan_status is PreMarketPlanStatus.BLOCKED_PREMARKET
    assert plan.block_code == "UNKNOWN_S23_BRANCH"


@pytest.mark.parametrize(
    ("runtime_change", "planning_context", "resolved_configuration", "expected_code"),
    (
        ({"strategy_family_id": None}, None, None, "MISSING_STRATEGY_IDENTITY"),
        ({"strategy_definition_id": None}, None, None, "MISSING_STRATEGY_IDENTITY"),
        ({"strategy_instance_id": None}, None, None, "MISSING_STRATEGY_IDENTITY"),
        ({"resolved_configuration_hash": None}, None, None, "MISSING_RESOLVED_CONFIGURATION"),
        ({}, None, {}, "MISSING_RESOLVED_CONFIGURATION"),
        ({}, {"enabled": False}, None, "STRATEGY_DISABLED"),
        ({}, {"trading_day_eligible": False}, None, "TRADING_DAY_INELIGIBLE"),
        ({}, {"expected_configuration_hash": "different"}, None, "CONFIGURATION_HASH_MISMATCH"),
    ),
)
def test_initial_identity_configuration_and_eligibility_failures_block(
    runtime_change,
    planning_context,
    resolved_configuration,
    expected_code,
) -> None:
    case = vertical.build_s23_bull_call_vertical_case()
    runtime_input = replace(case.runtime_input, **runtime_change)
    context_kwargs = planning_context or {"expected_configuration_hash": runtime_input.resolved_configuration_hash}
    context = PreMarketPlanningContext(underlying_instrument="NSE:NIFTY", **context_kwargs)
    config = resolved_configuration if resolved_configuration is not None else premarket._resolved_configuration(case)

    plan = PreMarketStrategyPlanBuilder().build(runtime_input, config, context, premarket._stage_policies(case))

    assert plan.plan_status is PreMarketPlanStatus.BLOCKED_PREMARKET
    assert plan.block_code == expected_code


@pytest.mark.parametrize("runtime_change, expected_field", (({"quantity": 0}, "valid quantity"), ({"lots": 0}, "valid lots")))
def test_invalid_quantity_or_lots_blocks(runtime_change, expected_field) -> None:
    case = vertical.build_s23_bull_call_vertical_case()
    runtime_input = replace(case.runtime_input, **runtime_change)

    plan = premarket.build_s23_call_side_premarket_plan(replace(case, runtime_input=runtime_input))

    assert plan.plan_status is PreMarketPlanStatus.BLOCKED_PREMARKET
    assert expected_field in plan.missing_fields


def test_missing_underlying_reference_blocks() -> None:
    case = vertical.build_s23_bear_call_vertical_case()
    bad_input = replace(case.runtime_input, market_structure_references={"d2hh": case.market_levels.d2hh})

    plan = premarket.build_s23_call_side_premarket_plan(replace(case, runtime_input=bad_input))

    assert plan.plan_status is PreMarketPlanStatus.BLOCKED_PREMARKET
    assert plan.block_code == "UNDERLYING_REFERENCE_FAILURE"


def test_no_qualifying_contract_blocks() -> None:
    case = vertical.build_s23_bear_call_vertical_case()
    expiry = case.runtime_input.product_specific["expiry_date"]
    bad_chain = vertical._option_chain(case.strategy_rule.symbol, expiry, case.strategy_rule.option_type, 22250.0, 280.0, 1.0, case.runtime_input.evaluated_at)
    bad_input = replace(case.runtime_input, product_specific={"option_chain_snapshot": bad_chain, "expiry_date": expiry})

    plan = premarket.build_s23_call_side_premarket_plan(replace(case, runtime_input=bad_input, option_chain_snapshot=bad_chain))

    assert plan.plan_status is PreMarketPlanStatus.BLOCKED_PREMARKET
    assert plan.block_code == "NO_QUALIFYING_CONTRACT"


def test_missing_option_chain_input_blocks() -> None:
    case = vertical.build_s23_bear_call_vertical_case()
    bad_input = replace(case.runtime_input, product_specific={"expiry_date": case.runtime_input.product_specific["expiry_date"]})

    plan = premarket.build_s23_call_side_premarket_plan(replace(case, runtime_input=bad_input))

    assert plan.plan_status is PreMarketPlanStatus.BLOCKED_PREMARKET
    assert plan.block_code == "NO_QUALIFYING_CONTRACT"
    assert "option_chain_snapshot" in plan.block_reason


def test_missing_selected_contract_history_blocks() -> None:
    case = vertical.build_s23_bear_call_vertical_case()
    context = _context_through_contract_selection(case)
    legacy_entry = replace(context["legacy_entry"], entry_value=None)

    result = vertical._base_entry({**context, "legacy_entry": legacy_entry})

    assert result.status == "BLOCKED"
    assert EntryFailure.MISSING_REFERENCE in result.payload["base_entry"].failures


def test_entry_failure_blocks() -> None:
    case = vertical.build_s23_bear_call_vertical_case()
    context = _context_through_contract_selection(case)
    selected = replace(context["selected_contract"], strike=None)

    result = vertical._base_entry({**context, "selected_contract": selected})

    assert result.status == "BLOCKED"
    assert result.payload["base_entry"].status is BusinessEngineStatus.BLOCKED


def test_target_failure_blocks(monkeypatch) -> None:
    def fail_target(self, policy_input):
        return TargetPolicyResult("fixture.target", policy_input.runtime_input.evaluated_at, PolicyStatus.BLOCKED, True, "target failed")

    monkeypatch.setattr(premarket.S23TargetPolicyAdapter, "evaluate", fail_target)

    plan = premarket.build_s23_bear_call_premarket_plan()

    assert plan.plan_status is PreMarketPlanStatus.BLOCKED_PREMARKET
    assert plan.block_code == "TARGET_ADAPTER_FAILURE"


def test_msl_failure_blocks(monkeypatch) -> None:
    def fail_msl(self, policy_input):
        return MSLPolicyResult("fixture.msl", policy_input.runtime_input.evaluated_at, PolicyStatus.BLOCKED, True, "msl failed")

    monkeypatch.setattr(premarket.S23MSLPolicyAdapter, "evaluate", fail_msl)

    plan = premarket.build_s23_bear_call_premarket_plan()

    assert plan.plan_status is PreMarketPlanStatus.BLOCKED_PREMARKET
    assert plan.block_code == "MSL_ADAPTER_FAILURE"


def test_missing_orpt_and_rc_block(monkeypatch) -> None:
    def missing_timing(case, context):
        return premarket.PreMarketStageResult("timing", "PASSED", {})

    monkeypatch.setattr(premarket, "_timing", missing_timing)

    plan = premarket.build_s23_bull_call_premarket_plan()

    assert plan.plan_status is PreMarketPlanStatus.BLOCKED_PREMARKET
    assert plan.block_code == "MISSING_REQUIRED_PLAN_FIELD"
    assert "normal ORPT" in plan.missing_fields
    assert "RC time" in plan.missing_fields


def test_required_rc_time_missing_blocks(monkeypatch) -> None:
    def missing_rc(case, context):
        return premarket.PreMarketStageResult("timing", "PASSED", {"normal_orpt": premarket.S23_PREMARKET_PLAN_ORPT})

    monkeypatch.setattr(premarket, "_timing", missing_rc)

    plan = premarket.build_s23_bull_call_premarket_plan()

    assert plan.plan_status is PreMarketPlanStatus.BLOCKED_PREMARKET
    assert "RC time" in plan.missing_fields


def test_carried_position_prevents_fresh_entry_plan(monkeypatch) -> None:
    def should_not_run(case, context):
        raise AssertionError("fresh-entry stages must not run for carried positions")

    monkeypatch.setattr(premarket, "_contract_selection", should_not_run)
    case = vertical.build_s23_bull_call_vertical_case()
    context = PreMarketPlanningContext(
        underlying_instrument="NSE:NIFTY",
        carried_position_detected=True,
        expected_configuration_hash=case.runtime_input.resolved_configuration_hash,
    )

    plan = premarket.build_s23_call_side_premarket_plan(case, planning_context=context)

    assert plan.plan_status is PreMarketPlanStatus.NO_ACTION_TODAY
    assert plan.block_code == "MANAGING_CARRIED_POSITION"
    assert plan.fresh_entry_eligible is False


def test_opening_quote_current_gap_and_orpt_rc_observations_are_not_required() -> None:
    plan = premarket.build_s23_bull_call_premarket_plan()
    payload = plan.to_json()

    assert plan.plan_status is PreMarketPlanStatus.PREPARED
    assert "gap_missed_entry" not in plan.stage_evidence
    assert "opening_quote" not in payload
    assert "current_day_gap" not in payload
    assert "orpt_observation" not in payload
    assert "rc_observation" not in payload


def test_no_broker_paper_live_filesystem_or_execution_dependency_in_generic_builder(monkeypatch) -> None:
    source = Path("src/tfis/premarket/plan_builder.py").read_text(encoding="utf-8")

    assert "S23" not in source
    assert "S21" not in source
    assert "strategy_code ==" not in source
    assert "tfis.paper" not in source
    assert "broker" not in source.lower()
    assert "place_order" not in source
    assert "ORDER_SUBMITTED" not in source
    assert "POSITION_OPEN" not in source
    assert "write_text" not in source
    assert "open(" not in source
    assert "eval(" not in source
    assert "exec(" not in source


def test_no_filesystem_persistence_when_building_plan(monkeypatch) -> None:
    def fail_write(self, *args, **kwargs):
        raise AssertionError(f"unexpected write: {self}")

    monkeypatch.setattr(Path, "write_text", fail_write)

    assert premarket.build_s23_bear_call_premarket_plan().plan_status is PreMarketPlanStatus.PREPARED


def test_plan_to_vertical_compatibility_mapping() -> None:
    plan = premarket.build_s23_bear_call_premarket_plan()

    assert plan.contract_resolution.selected_contract is not None
    assert plan.references.underlying
    assert plan.references.selected_contract
    assert plan.planned_values.base_entry is not None
    assert plan.planned_values.normal_orpt is not None
    assert plan.planned_values.rc_time is not None
    assert plan.planned_values.policy_identities["gap_missed_entry"]


def test_existing_m3_to_m7_hashes_remain_unchanged() -> None:
    assert vertical.run_s23_bull_call_vertical_slice().deterministic_hash == BULL_M3_HASH
    assert m5.run_s23_call_evidence_fixture("s23_bull_call_workbook_fixture").deterministic_hash == BULL_M5_HASH
    assert m5.run_s23_call_evidence_fixture("s23_bear_call_workbook_fixture").deterministic_hash == BEAR_M5_HASH


def test_field_provenance_and_evidence_classification_are_explicit() -> None:
    plan = premarket.build_s23_bull_call_premarket_plan()

    assert set(plan.field_provenance.values()) <= {
        "LEGACY_CONFIG",
        "WORKBOOK_NORMALIZED",
        "LEGACY_FIXTURE",
        "SYNTHETIC_SUPPLEMENT",
        "DERIVED",
        "MISSING",
        "NOT_APPLICABLE",
    }
    assert "single qualifying option-chain candidate" in plan.supplemented_fields
    assert plan.stage_evidence["timing"]["evidence"]["source"] == "S23 fixture timing policy"


def _context_through_contract_selection(case) -> dict[str, object]:
    context: dict[str, object] = {"case": case}
    for current in (
        vertical._strategy_resolution,
        vertical._monthly_status_and_branch,
        vertical._underlying_references,
        vertical._contract_selection,
    ):
        result = current(context)
        context.update(dict(result.payload))
        if result.status != "PASSED":
            raise AssertionError(f"{result.stage_name} did not pass: {result.failure_code} {result.reason}")
    return context
