from __future__ import annotations

import json
from pathlib import Path

from tfis.adapters.phase5b import (
    AUTHORITATIVE_PUT_MISSED_ENTRY_RESOLUTION,
    build_phase5b_report_set,
    build_phase5b_summary,
    build_put_case,
)
from tfis.adapters.phase5b.s23_put_four_branch import (
    build_branch_contract,
    build_four_branch_certification,
    build_natural_branch_selection,
    build_put_cell_trace,
    build_put_rule_matrix,
    build_put_source_inventory,
)
from tfis.internal_paper.runtime import ControlledInternalPaperRuntime, build_default_s23_single_instance_profile


def test_put_source_inventory_resolves_missed_entry_to_option_low() -> None:
    inventory = build_put_source_inventory()
    trace = build_put_cell_trace()

    assert AUTHORITATIVE_PUT_MISSED_ENTRY_RESOLUTION == "AUTHORITATIVE_OPTION_LOW"
    assert trace["legacy_high_profile_status"] == "LEGACY_ONLY_NOT_AUTHORITY"
    assert {row["branch"] for row in inventory} == {"BULL_PUT", "BEAR_PUT"}
    assert not any(row.get("authority_status") == "RULE_AUTHORITY_UNRESOLVED" for row in inventory)
    assert all(row["workbook_file"] == "TFISRulesAndSpec/AB7 OS.xlsx" for row in inventory)
    assert all(row["sheet"] == "AB6 OS" for row in inventory)


def test_put_matrix_has_verified_cells_for_bull_and_bear_put() -> None:
    matrix = build_put_rule_matrix()

    assert matrix["BULL_PUT"]["normal_entry"]["cells"]["base_entry"] == "M165"
    assert matrix["BULL_PUT"]["normal_entry"]["cells"]["original_sl_msl"] == "M166"
    assert matrix["BULL_PUT"]["gap_missed_entry"]["cells"]["entry"] == "X179"
    assert matrix["BULL_PUT"]["revised_fsl_trp"]["cells"]["revised_fsl_trp"] == "M187:O187"
    assert matrix["BEAR_PUT"]["normal_entry"]["cells"]["base_entry"] == "M171"
    assert matrix["BEAR_PUT"]["normal_entry"]["cells"]["original_sl_msl"] == "M172"
    assert matrix["BEAR_PUT"]["gap_missed_entry"]["cells"]["entry"] == "X180"
    assert matrix["BEAR_PUT"]["revised_fsl_trp"]["cells"]["revised_fsl_trp"] == "M188:O188"
    assert matrix["BULL_PUT"]["eod"]["authority_status"] == "USER_CLARIFIED"


def test_branch_contract_supports_complete_s23_without_display_name_parsing() -> None:
    contract = build_branch_contract()

    assert set(contract["supported_branches"]) == {"BULL_CALL", "BEAR_CALL", "BULL_PUT", "BEAR_PUT"}
    assert contract["supported_branches"]["BULL_PUT"]["option_type"] == "PUT"
    assert contract["supported_branches"]["BEAR_PUT"]["option_type"] == "PUT"
    assert contract["display_name_parsing"] is False


def test_put_contract_selection_premarket_and_fail_closed_boundaries() -> None:
    bull = build_put_case("bull_put_target")
    bear = build_put_case("bear_put_original_sl")

    for case in (bull, bear):
        assert case["status"] == "PASSED"
        assert case["contract_selection"]["option_type"] == "PUT"
        assert case["contract_selection"]["oi_threshold"] == "500 Lots"
        assert case["contract_selection"]["fallback"] == "FAIL_CLOSED_IF_NEAR_AND_NEXT_DO_NOT_QUALIFY"
        assert case["premarket_plan"]["selected_contract"].endswith("_PE")
        assert case["opening_context"]["missed_entry_observation_source"] == "OPTION_LOW"
        assert case["opening_context"]["comparison"] == "OPTION_LOW < BASE_ENTRY"


def test_put_effective_execution_paths_and_lifecycle_outcomes() -> None:
    normal = build_put_case("bull_put_target")
    original_sl = build_put_case("bear_put_original_sl")
    gap = build_put_case("bull_put_gap_revised_sl")
    bear_gap = build_put_case("bear_put_gap_revised_sl")
    partial = build_put_case("bull_put_partial_fill")
    eod = build_put_case("bull_put_eod_exit")
    carry = build_put_case("bull_put_carry_recovery")

    assert normal["position_cycle"]["exit_reason"] == "TARGET"
    assert original_sl["position_cycle"]["exit_reason"] == "ORIGINAL_SL"
    assert gap["effective_execution_plan"]["effective_entry"] == "RECALCULATED_ENTRY"
    assert gap["position_cycle"]["exit_reason"] == "REVISED_SL"
    assert bear_gap["branch"] == "BEAR_PUT"
    assert partial["position_cycle"]["remaining_quantity"] > 0
    assert eod["position_cycle"]["exit_reason"] == "EOD_EXIT"
    assert carry["position_cycle"]["exit_reason"] == "CARRIED_FORWARD"
    assert carry["position_cycle"]["remaining_quantity"] > 0


def test_put_execution_intents_accounting_and_trace_are_internal_only() -> None:
    case = build_put_case("bear_put_gap_revised_sl")
    purposes = {intent["purpose"] for intent in case["execution_intents"]}

    assert purposes == {"ENTRY", "TARGET", "ORIGINAL_SL", "REVISED_SL", "EOD_EXIT"}
    assert {intent["status"] for intent in case["execution_intents"]} == {"VALIDATED_NOT_SUBMITTABLE"}
    assert case["external_broker_live_authority"] == "NONE"
    assert case["accounting"]["trade_fact"]["instrument"]["option_type"] == "PUT"
    assert case["accounting"]["trade_fact"]["instrument"]["contract"].endswith("_PE")
    assert case["accounting"]["pnl_facts"]
    assert {"ExecutionIntent", "TradeFact", "PnLFact"}.issubset({node["node_type"] for node in case["trace"]})


def test_natural_ce_pe_selection_uses_common_pipeline_without_runner_side_hint() -> None:
    selection = build_natural_branch_selection()

    assert selection["ce_case"]["resolved_branch"] == "BULL_CALL"
    assert selection["ce_case"]["option_type"] == "CALL"
    assert selection["pe_case"]["resolved_branch"] == "BEAR_PUT"
    assert selection["pe_case"]["option_type"] == "PUT"
    assert selection["runner_told_call_or_put_after_resolution"] is False


def test_four_branch_certification_and_runtime_profile_are_complete() -> None:
    certification = build_four_branch_certification()
    profile = build_default_s23_single_instance_profile()
    preview = ControlledInternalPaperRuntime().preview()

    assert certification["status"] == "COMPLETE_S23_INTERNAL_PAPER_CERTIFIED"
    assert set(certification["branches"]) == {"BULL_CALL", "BEAR_CALL", "BULL_PUT", "BEAR_PUT"}
    assert certification["trace_complete_through_pnl"] is True
    assert profile.strategy_instance_id == "S23_FOUR_BRANCH_INTERNAL_PAPER_CONTROLLED"
    assert profile.strategy_definition_id == "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_FOUR_BRANCH"
    assert profile.strategy_version == "s23.phase5b.controlled.v1"
    assert profile.permitted_branches == ("BULL_CALL", "BEAR_CALL", "BULL_PUT", "BEAR_PUT")
    assert preview.profile["permitted_branches"] == ["BULL_CALL", "BEAR_CALL", "BULL_PUT", "BEAR_PUT"]


def test_phase5b_reports_are_generated(tmp_path: Path) -> None:
    written = build_phase5b_report_set(tmp_path)
    required = {
        "phase5b_put_source_inventory.json",
        "phase5b_put_cell_trace.json",
        "phase5b_put_rule_matrix.json",
        "phase5b_generic_reuse_audit.json",
        "phase5b_branch_contract.json",
        "phase5b_bull_put_premarket.json",
        "phase5b_bear_put_premarket.json",
        "phase5b_bull_put_normal_result.json",
        "phase5b_bear_put_normal_result.json",
        "phase5b_bull_put_gap_result.json",
        "phase5b_bear_put_gap_result.json",
        "phase5b_put_target_result.json",
        "phase5b_put_original_sl_result.json",
        "phase5b_put_revised_sl_result.json",
        "phase5b_put_eod_result.json",
        "phase5b_put_carry_recovery_result.json",
        "phase5b_four_branch_certification.json",
        "phase5b_natural_branch_selection.json",
        "phase5b_call_regression.json",
        "phase5b_capture_readiness.json",
        "phase5b_gap_register.json",
        "phase5b_put_conflict_resolution.md",
        "phase5b_summary.md",
    }

    assert required.issubset(set(written))
    summary = json.loads((tmp_path / "phase5b_four_branch_certification.json").read_text(encoding="utf-8"))
    assert summary["status"] == "COMPLETE_S23_INTERNAL_PAPER_CERTIFIED"


def test_phase5b_summary_verdict() -> None:
    summary = build_phase5b_summary()

    assert summary["verdict"] == "PHASE5B_M1_ACCEPT"
    assert summary["missed_entry_conflict_resolution"] == "AUTHORITATIVE_OPTION_LOW"
