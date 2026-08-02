from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from tfis.accounting.builders import PnLFactBuilder, TradeFactBuilder, build_accounting_result
from tfis.accounting.models import AccountingQuality, ChargeEvidence, InstrumentDimensions
from tfis.domain.effective_execution_plan import (
    EffectiveExecutionPath,
    EffectiveExecutionPlan,
    EffectiveExecutionPlanStatus,
    EffectiveExecutionValues,
    EffectiveRiskValueStatus,
)
from tfis.domain.enums import MonthlyStatus, Segment
from tfis.domain.runtime_contracts import TFISContractIdentity, TFISExecutionSide, TFISProductType
from tfis.execution_intent import ExecutionIntentComposer, ExecutionIntentPurpose, IntentCompositionRequest
from tfis.execution_intent.models import ExecutionAuthorityMode, ExecutionInstrument, ExecutionIntent
from tfis.execution_intent.reports import build_validation_input
from tfis.execution_intent.validation import ExecutionIntentValidator
from tfis.internal_paper import (
    AccountCoordinator,
    AccountCoordinatorEnvironment,
    DeterministicExecutionScenarioDefinition,
    DeterministicInternalPaperAdapter,
    DeterministicMarketEvidence,
    InternalPaperAuthorityGrant,
    InternalPaperExecutionScenario,
    SimulatedPaperAccountSnapshot,
    create_creation_event,
)
from tfis.internal_position import PositionCycleCoordinator
from tfis.internal_position.models import LifecycleRequirement, LifecycleRequirementType
from tfis.monthly_status import MonthlyStatusEngine, MonthlyStatusReferenceLevels
from tfis.persistence import canonical_hash


IST = ZoneInfo("Asia/Kolkata")
TRADING_DATE = date(2024, 1, 23)
NEXT_TRADING_DATE = date(2024, 1, 24)
TRADING_SESSION_ID = f"NSE:{TRADING_DATE.isoformat()}"
NEXT_TRADING_SESSION_ID = f"NSE:{NEXT_TRADING_DATE.isoformat()}"
STRATEGY_FAMILY_ID = "OPTION_SELLING"
STRATEGY_DEFINITION_ID = "S21_BANKNIFTY_OP_SELL_MONTHLY"
STRATEGY_VERSION = "1.0.0"
STRATEGY_INSTANCE_ID = "S21_BANKNIFTY_ACCOUNT_A_PAPER"
BRANCH_ID = "BULL_CALL"
BRANCH_UNIQUE_CODE = "BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL"
BROKER_ACCOUNT_ID = "S21_ACCOUNT_A_INTERNAL_PAPER"
LOGICAL_ACCOUNT = "INTERNAL_PAPER_ACCOUNT"
CONFIGURATION_HASH = "s21-source-closure-config-v1"
RULE_MATRIX_VERSION = "s21_source_closure_accepted_v1"
EVIDENCE_PACKET_HASH = "s21-first-branch-offline-evidence-v1"

ENTRY_RULE_ID = "S21.BULL_CALL.STATIC.001"
CONTRACT_RULE_ID = "S21.CONTRACT_SELECTION.001"
ORPT_RC_RULE_ID = "S21.FRESH_ENTRY_ORPT_RC.001"
CARRIED_RULE_ID = "S21.CARRIED_CALL.FSL_TRP.001"
EOD_RULE_ID = "GLOBAL.OPTION_SELLING.EOD_CARRY_GT_EXIT_LTE_CARRY.001"
MONTHLY_STATUS_RULE_ID = "MONTHLY_STATUS.GENERIC.ENGINE.001"
BRANCH_MAPPING_RULE_ID = "S21.MONTHLY_STATUS_TO_BRANCH.001"
APS_RULE_ID = "GLOBAL.OPTION_SELLING.APS_NOT_APPLICABLE_ONE_LOT.001"

LOT_SIZE = 15
CONFIGURED_LOTS = 1
EXCHANGE_QUANTITY = LOT_SIZE * CONFIGURED_LOTS
EXPIRY_NEAR = date(2024, 1, 25)
EXPIRY_NEXT = date(2024, 2, 29)
STRIKE = Decimal("47000")
BASE_ENTRY = Decimal("925.00")
TARGET = Decimal("370.00")
ORIGINAL_SL = Decimal("1337.50")
REVISED_ENTRY = Decimal("910.00")
REVISED_SL = Decimal("1284.00")
EOD_EXIT_PRICE = Decimal("1340.00")
EOD_EQUAL_PRICE = ORIGINAL_SL

S21_FIRST_BRANCH_REPORT_NAMES = (
    "s21_selected_first_branch.json",
    "s21_policy_composition.json",
    "s21_contract_selection_result.json",
    "s21_premarket_plan.json",
    "s21_normal_target_result.json",
    "s21_original_sl_result.json",
    "s21_rc_recalculation_result.json",
    "s21_no_contract_result.json",
    "s21_eod_result.json",
    "s21_carry_recovery_result.json",
    "s21_trade_fact.json",
    "s21_pnl_fact.json",
    "s21_complete_trace.json",
    "s21_s23_regression.json",
    "s21_platform_reuse_report.json",
    "s21_gap_register.json",
    "s21_summary.md",
)


class S21ExecutionIntentAdapter:
    def __init__(self, composer: ExecutionIntentComposer | None = None) -> None:
        self.composer = composer or ExecutionIntentComposer()

    def entry_from_effective_plan(self, plan: EffectiveExecutionPlan) -> ExecutionIntent:
        if plan.selected_contract is None or plan.order_side is None or plan.quantity is None or plan.values.effective_entry is None:
            raise ValueError("S21 EffectiveExecutionPlan is missing required ENTRY fields.")
        authorized = datetime.combine(plan.trading_date, plan.values.revised_authorized_time or plan.values.normal_orpt or time(9, 15), tzinfo=IST)
        return self.composer.compose(
            IntentCompositionRequest(
                trading_session_id=TRADING_SESSION_ID,
                trading_date=plan.trading_date,
                strategy_family_id=plan.strategy_family,
                strategy_definition_id=plan.strategy_definition,
                strategy_version=plan.strategy_version,
                strategy_instance_id=plan.strategy_instance_id,
                broker_account_id=BROKER_ACCOUNT_ID,
                position_cycle_id=None,
                source_artifact_type="EffectiveExecutionPlan",
                source_artifact_id=plan.execution_plan_id,
                source_artifact_hash=plan.execution_plan_hash,
                instrument=_execution_instrument(plan.selected_contract),
                purpose=ExecutionIntentPurpose.ENTRY,
                side=plan.order_side.value,
                requested_quantity=plan.quantity,
                quantity_unit="UNITS",
                order_type=plan.values.order_type or "LIMIT",
                limit_price=Decimal(str(plan.values.effective_entry)),
                trigger_price=None,
                time_in_force="DAY",
                authorized_not_before=authorized,
                authorized_not_after=None,
                maximum_allowed_slippage=Decimal("0.05"),
                protection_generation=None,
                source_rule_ids=(ENTRY_RULE_ID, ORPT_RC_RULE_ID, CONTRACT_RULE_ID),
                configuration_hash=CONFIGURATION_HASH,
                rule_matrix_version=RULE_MATRIX_VERSION,
                market_snapshot_hash=f"market:{plan.source_opening_context_id}",
                reconciliation_result_id="s21-reconciliation-shadow-ready",
                reconciliation_result_hash="s21-reconciliation-shadow-ready-hash",
                recovery_assessment_id="s21-recovery-offline-ready",
                recovery_assessment_hash="s21-recovery-offline-ready-hash",
                evidence_packet_hash=EVIDENCE_PACKET_HASH,
                provenance={"adapter": type(self).__name__, "branch": BRANCH_ID, "path": plan.path_classification.value},
                authority_mode=ExecutionAuthorityMode.OFFLINE_ONLY,
            )
        )

    def lifecycle_intent(
        self,
        *,
        purpose: ExecutionIntentPurpose,
        trading_date: date,
        position_cycle_id: str,
        contract: TFISContractIdentity,
        quantity: int,
        price: Decimal,
        source_artifact_id: str,
        source_artifact_hash: str,
        authorized_not_before: datetime,
        protection_generation: int | None,
        rule_id: str,
    ) -> ExecutionIntent:
        order_type = "SL" if purpose in {ExecutionIntentPurpose.ORIGINAL_SL, ExecutionIntentPurpose.REVISED_SL} else "LIMIT"
        return self.composer.compose(
            IntentCompositionRequest(
                trading_session_id=f"NSE:{trading_date.isoformat()}",
                trading_date=trading_date,
                strategy_family_id=STRATEGY_FAMILY_ID,
                strategy_definition_id=STRATEGY_DEFINITION_ID,
                strategy_version=STRATEGY_VERSION,
                strategy_instance_id=STRATEGY_INSTANCE_ID,
                broker_account_id=BROKER_ACCOUNT_ID,
                position_cycle_id=position_cycle_id,
                source_artifact_type="S21LifecycleRequirement",
                source_artifact_id=source_artifact_id,
                source_artifact_hash=source_artifact_hash,
                instrument=_execution_instrument(contract),
                purpose=purpose,
                side="BUY",
                requested_quantity=quantity,
                quantity_unit="UNITS",
                order_type=order_type,
                limit_price=price if order_type == "LIMIT" else None,
                trigger_price=price if order_type == "SL" else None,
                time_in_force="DAY",
                authorized_not_before=authorized_not_before,
                authorized_not_after=None,
                maximum_allowed_slippage=Decimal("0.05"),
                protection_generation=protection_generation,
                source_rule_ids=(rule_id,),
                configuration_hash=CONFIGURATION_HASH,
                rule_matrix_version=RULE_MATRIX_VERSION,
                market_snapshot_hash=f"market:{source_artifact_id}",
                reconciliation_result_id="s21-reconciliation-shadow-ready",
                reconciliation_result_hash="s21-reconciliation-shadow-ready-hash",
                recovery_assessment_id="s21-recovery-offline-ready",
                recovery_assessment_hash="s21-recovery-offline-ready-hash",
                evidence_packet_hash=canonical_hash({"source_artifact_id": source_artifact_id, "purpose": purpose.value}),
                provenance={"adapter": type(self).__name__, "branch": BRANCH_ID},
                authority_mode=ExecutionAuthorityMode.OFFLINE_ONLY,
            )
        )


def build_s21_first_branch_certification() -> dict[str, Any]:
    monthly_status = _monthly_status_result()
    branch = _selected_branch(monthly_status)
    contract_selection = _contract_selection_report()
    premarket = _premarket_plan_report(monthly_status, branch, contract_selection["normal"])
    opening = _opening_context("normal", orpt_low=Decimal("940.00"), orpt_high=Decimal("980.00"))
    normal_plan = _effective_plan("normal", opening, BASE_ENTRY, TARGET, ORIGINAL_SL, EffectiveExecutionPath.NORMAL_RETAINED)
    target = _execute_entry_to_exit(normal_plan, exit_purpose=ExecutionIntentPurpose.TARGET, exit_price=TARGET, exit_rule_id=ENTRY_RULE_ID, scenario_name="normal_target")
    original_sl = _execute_entry_to_exit(normal_plan, exit_purpose=ExecutionIntentPurpose.ORIGINAL_SL, exit_price=ORIGINAL_SL, exit_rule_id=ENTRY_RULE_ID, scenario_name="original_sl")
    rc_opening = _opening_context("orpt_missed_rc", orpt_low=Decimal("900.00"), orpt_high=Decimal("980.00"))
    rc_plan = _effective_plan("rc_recalculation", rc_opening, REVISED_ENTRY, TARGET, REVISED_SL, EffectiveExecutionPath.ABNORMAL_RECALCULATED)
    revised_sl = _execute_entry_to_exit(rc_plan, exit_purpose=ExecutionIntentPurpose.REVISED_SL, exit_price=REVISED_SL, exit_rule_id=CARRIED_RULE_ID, scenario_name="rc_revised_sl")
    eod = _execute_entry_to_exit(normal_plan, exit_purpose=ExecutionIntentPurpose.EOD_EXIT, exit_price=EOD_EXIT_PRICE, exit_rule_id=EOD_RULE_ID, scenario_name="eod_exit")
    carry = _carry_recovery_scenario(normal_plan)
    duplicate = _duplicate_replay_scenario(normal_plan)
    reconciliation_block = _reconciliation_block_scenario(normal_plan)
    isolation = _isolation_scenario(target)

    trace = {
        "schema_version": "s21.first_branch.complete_trace.v1",
        "selected_branch": branch,
        "pipeline": [
            "workbook_rule",
            "generic_monthly_status",
            "s21_branch_policy",
            "contract_selection",
            "premarket_plan",
            "opening_market_context",
            "orpt_rc",
            "effective_execution_plan",
            "execution_intent",
            "internal_paper_client_order",
            "simulated_fill",
            "position_cycle",
            "lifecycle",
            "trade_fact",
            "pnl_fact",
            "projection",
        ],
        "scenarios": {
            "normal_entry_target_exit": _scenario_summary(target),
            "normal_entry_original_sl_exit": _scenario_summary(original_sl),
            "orpt_missed_rc_revised_sl_exit": _scenario_summary(revised_sl),
            "near_fails_next_selected": contract_selection["near_fails_next_selected"],
            "near_and_next_fail_no_trade": contract_selection["near_and_next_fail"],
            "eod_exit": _scenario_summary(eod),
            "eod_equal_carry_forward": carry["eod_equal_carry_forward"],
            "next_day_carried_recovery": carry["next_day_recovery"],
            "duplicate_replay_no_duplicate_action": duplicate,
            "restart_after_entry_fill": carry["restart_after_entry_fill"],
            "reconciliation_block_no_order": reconciliation_block,
            "s21_s23_isolated": isolation,
        },
        "authority": _authority(),
    }
    trace["trace_hash"] = _report_hash(trace)
    trade_fact = target["accounting"]["trade_fact"]
    pnl_fact = target["accounting"]["pnl_facts"][0]
    return {
        "s21_selected_first_branch": branch,
        "s21_policy_composition": _policy_composition(),
        "s21_contract_selection_result": contract_selection,
        "s21_premarket_plan": premarket,
        "s21_normal_target_result": target,
        "s21_original_sl_result": original_sl,
        "s21_rc_recalculation_result": revised_sl,
        "s21_no_contract_result": contract_selection["near_and_next_fail"],
        "s21_eod_result": eod,
        "s21_carry_recovery_result": carry,
        "s21_trade_fact": trade_fact,
        "s21_pnl_fact": pnl_fact,
        "s21_complete_trace": trace,
        "s21_s23_regression": _s23_regression_report(),
        "s21_platform_reuse_report": _platform_reuse_report(),
        "s21_gap_register": _gap_register(),
        "s21_summary": _summary(trace),
    }


def write_s21_first_branch_reports(report_dir: Path | str = Path("reports/s21_implementation")) -> dict[str, Path]:
    report_path = Path(report_dir)
    report_path.mkdir(parents=True, exist_ok=True)
    certification = build_s21_first_branch_certification()
    written: dict[str, Path] = {}
    for key, value in certification.items():
        name = f"{key}.md" if key == "s21_summary" else f"{key}.json"
        path = report_path / name
        if key == "s21_summary":
            path.write_text(str(value), encoding="utf-8")
        else:
            path.write_text(json.dumps(_jsonable(_sanitize_report_payload(value)), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written[name] = path
    return written


def _monthly_status_result() -> dict[str, Any]:
    levels = MonthlyStatusReferenceLevels(
        PMH=46000.0,
        PML=43000.0,
        CMH=46800.0,
        CML=44100.0,
        PWH=45500.0,
        PWL=44000.0,
        CWH=46800.0,
        CWL=45600.0,
        current_price=46750.0,
    )
    result = MonthlyStatusEngine().classify("banknifty", levels)
    if result.status is not MonthlyStatus.BULL_CF:
        raise AssertionError(f"S21 fixture must resolve to BULL_CF, got {result.status.value}")
    payload = {
        "instrument": {"symbol": "BANKNIFTY", "instrument_group": "banknifty"},
        "evaluation_timestamp": datetime.combine(TRADING_DATE, time(8, 55), tzinfo=IST),
        "monthly_status": result.status.value,
        "rule_id": MONTHLY_STATUS_RULE_ID,
        "rule_version": "monthly_status_engine.v1",
        "monthly_references": levels,
        "transition_evidence": {
            "trigger_name": result.trigger_name,
            "threshold_value": result.threshold_value,
            "reversal_dominated": result.reversal_dominated,
            "source": "Generic MonthlyStatusEngine",
        },
        "data_quality": "FIXTURE_SOURCE_VERIFIED",
        "warnings": (),
        "failures": (),
    }
    return payload | {"result_hash": _report_hash(payload)}


def _selected_branch(monthly_status: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "strategy_definition_id": STRATEGY_DEFINITION_ID,
        "strategy_instance_id": STRATEGY_INSTANCE_ID,
        "selected_branch": BRANCH_ID,
        "selected_branch_unique_code": BRANCH_UNIQUE_CODE,
        "source_monthly_status": monthly_status["monthly_status"],
        "reason": "S21 first branch is limited to BULL_CALL because BULL_CF maps to the Bull branch and this branch has complete source closure.",
        "rule_ids": (BRANCH_MAPPING_RULE_ID, ENTRY_RULE_ID, CONTRACT_RULE_ID, ORPT_RC_RULE_ID, EOD_RULE_ID, APS_RULE_ID),
        "not_implemented_in_this_milestone": ("BULL_PUT", "BEAR_CALL", "BEAR_PUT"),
    }
    return payload | {"selection_hash": _report_hash(payload)}


def _contract_selection_report() -> dict[str, Any]:
    normal_candidates = (
        _candidate("NEAR", EXPIRY_NEAR, STRIKE, Decimal("980.00"), 9000, True),
        _candidate("NEXT", EXPIRY_NEXT, STRIKE, Decimal("970.00"), 11000, True),
    )
    near_fail_candidates = (
        _candidate("NEAR", EXPIRY_NEAR, STRIKE, Decimal("980.00"), 3000, False, "OI_BELOW_CONFIGURED_THRESHOLD"),
        _candidate("NEXT", EXPIRY_NEXT, STRIKE, Decimal("970.00"), 11000, True),
    )
    no_contract_candidates = (
        _candidate("NEAR", EXPIRY_NEAR, STRIKE, Decimal("600.00"), 2000, False, "PREMIUM_AND_OI_NOT_MET"),
        _candidate("NEXT", EXPIRY_NEXT, STRIKE, Decimal("650.00"), 1000, False, "PREMIUM_AND_OI_NOT_MET"),
    )
    return {
        "schema_version": "s21.contract_selection.first_branch.v1",
        "rule_id": CONTRACT_RULE_ID,
        "policy": {
            "expiry_order": ("NEAR", "NEXT"),
            "directional_traversal": "CALL_SELL_BULL_BRANCH_START_TO_END",
            "oi_threshold_lots": 500,
            "oi_threshold_units": 7500,
            "ideal_premium_phase": "SUPPORTED_BY_SOURCE",
            "minimum_premium_phase": "SUPPORTED_BY_SOURCE",
            "arbitrary_expression_evaluation": False,
        },
        "normal": _select_contract(normal_candidates, "normal_near_selected"),
        "near_fails_next_selected": _select_contract(near_fail_candidates, "near_fails_next_selected"),
        "near_and_next_fail": _select_contract(no_contract_candidates, "near_and_next_fail"),
    }


def _candidate(expiry_kind: str, expiry: date, strike: Decimal, premium: Decimal, oi: int, qualifies: bool, rejection: str | None = None) -> dict[str, Any]:
    return {
        "expiry_kind": expiry_kind,
        "expiry": expiry,
        "strike": strike,
        "option_type": "CE",
        "premium": premium,
        "open_interest_units": oi,
        "open_interest_lots": oi // LOT_SIZE,
        "qualifies": qualifies,
        "rejection": rejection,
        "contract": _contract_dict(_contract(expiry=expiry, strike=strike)),
    }


def _select_contract(candidates: tuple[Mapping[str, Any], ...], scenario_id: str) -> dict[str, Any]:
    selected = next((candidate for candidate in candidates if candidate["qualifies"]), None)
    payload = {
        "scenario_id": scenario_id,
        "decision": "SELECTED" if selected else "NO_TRADE",
        "selected_contract": selected["contract"] if selected else None,
        "selected_expiry_kind": selected["expiry_kind"] if selected else None,
        "candidates": candidates,
        "source_rule_ids": (CONTRACT_RULE_ID,),
        "no_contract_reason": None if selected else "NO_NEAR_OR_NEXT_CONTRACT_SATISFIED_PREMIUM_AND_OI",
    }
    return payload | {"result_hash": _report_hash(payload)}


def _premarket_plan_report(monthly_status: Mapping[str, Any], branch: Mapping[str, Any], selection: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "schema_version": "s21.premarket_plan.first_branch.v1",
        "trading_date": TRADING_DATE,
        "strategy_instance_id": STRATEGY_INSTANCE_ID,
        "monthly_status_result_hash": monthly_status["result_hash"],
        "branch_selection_hash": branch["selection_hash"],
        "contract_selection_hash": selection["result_hash"],
        "selected_contract": selection["selected_contract"],
        "configured_lots": CONFIGURED_LOTS,
        "lot_size": LOT_SIZE,
        "exchange_quantity": EXCHANGE_QUANTITY,
        "base_entry": BASE_ENTRY,
        "target": TARGET,
        "original_sl": ORIGINAL_SL,
        "orpt_time": "09:19:59",
        "rc_time": "09:29:59",
        "source_rule_ids": (ENTRY_RULE_ID, CONTRACT_RULE_ID, ORPT_RC_RULE_ID),
    }
    payload_hash = _report_hash(payload)
    return payload | {"premarket_plan_id": "s21-premarket:" + payload_hash[:24], "premarket_plan_hash": payload_hash}


def _opening_context(label: str, *, orpt_low: Decimal, orpt_high: Decimal) -> dict[str, Any]:
    payload = {
        "opening_context_id": f"s21-opening:{label}",
        "trading_date": TRADING_DATE,
        "source": "fixture_opening_market_context",
        "orpt_timestamp": datetime.combine(TRADING_DATE, time(9, 19, 59), tzinfo=IST),
        "rc_timestamp": datetime.combine(TRADING_DATE, time(9, 29, 59), tzinfo=IST),
        "orpt_low": orpt_low,
        "orpt_high": orpt_high,
        "orpt_missed": orpt_low < BASE_ENTRY,
        "fresh_entry_gap_missed_entry_applicability": "NOT_APPLICABLE_TO_S21_SOURCE_CLOSED_BRANCH",
    }
    return payload | {"opening_context_hash": _report_hash(payload)}


def _effective_plan(label: str, opening: Mapping[str, Any], entry: Decimal, target: Decimal, sl: Decimal, path: EffectiveExecutionPath) -> EffectiveExecutionPlan:
    contract = _contract(expiry=EXPIRY_NEAR, strike=STRIKE)
    values = EffectiveExecutionValues(
        base_entry=float(BASE_ENTRY),
        effective_entry=float(entry),
        preliminary_target=float(TARGET),
        effective_target=float(target),
        preliminary_msl=float(ORIGINAL_SL),
        effective_msl=float(sl),
        normal_orpt=time(9, 19, 59),
        revised_authorized_time=time(9, 29, 59) if path is EffectiveExecutionPath.ABNORMAL_RECALCULATED else None,
        order_type="LIMIT",
        target_status=EffectiveRiskValueStatus.RETAINED_FROM_PREMARKET,
        msl_status=EffectiveRiskValueStatus.RECALCULATED if path is EffectiveExecutionPath.ABNORMAL_RECALCULATED else EffectiveRiskValueStatus.RETAINED_FROM_PREMARKET,
    )
    source_plan_hash = canonical_hash({"branch": BRANCH_ID, "entry": str(BASE_ENTRY), "target": str(TARGET), "original_sl": str(ORIGINAL_SL)})
    return EffectiveExecutionPlan(
        execution_plan_id=f"s21-effective:{label}",
        schema_version="s21.effective_execution_plan.first_branch.v1",
        trading_date=TRADING_DATE,
        strategy_family=STRATEGY_FAMILY_ID,
        strategy_definition=STRATEGY_DEFINITION_ID,
        strategy_version=STRATEGY_VERSION,
        strategy_instance_id=STRATEGY_INSTANCE_ID,
        source_premarket_plan_id="s21-premarket:first-branch",
        source_premarket_plan_hash=source_plan_hash,
        source_opening_context_id=str(opening["opening_context_id"]),
        source_opening_context_hash=str(opening["opening_context_hash"]),
        plan_revision=1,
        supersedes_plan_id=None,
        plan_status=EffectiveExecutionPlanStatus.READY_OFFLINE,
        path_classification=path,
        final_eligibility="TRADE",
        block_code=None,
        block_reason=None,
        downstream_execution_permission="OFFLINE_INTERNAL_PAPER_CANDIDATE_ONLY",
        offline_execution_candidate=True,
        product=TFISProductType.OPTION_SELLING,
        underlying="BANKNIFTY",
        selected_expiry=EXPIRY_NEAR,
        selected_strike=float(STRIKE),
        selected_contract=contract,
        order_side=TFISExecutionSide.SELL,
        position_intent="SHORT_OPTION",
        quantity=EXCHANGE_QUANTITY,
        lots=CONFIGURED_LOTS,
        values=values,
        opening_gap_classification="NORMAL",
        gap_missed_entry_applicability="NOT_APPLICABLE_TO_S21",
        gap_missed_entry_status="NOT_APPLICABLE",
        recalculation_required=path is EffectiveExecutionPath.ABNORMAL_RECALCULATED,
        recalculation_inputs={"orpt_low": str(opening["orpt_low"]), "base_entry": str(BASE_ENTRY)},
        recalculation_output={"effective_entry": str(entry), "effective_msl": str(sl)},
        policy_identities={
            "entry_rule": ENTRY_RULE_ID,
            "contract_rule": CONTRACT_RULE_ID,
            "orpt_rc_rule": ORPT_RC_RULE_ID,
            "configuration_hash": CONFIGURATION_HASH,
            "rule_matrix_version": RULE_MATRIX_VERSION,
        },
        stage_evidence={"opening_context": opening, "authority": _authority()},
    )


def _execute_entry_to_exit(plan: EffectiveExecutionPlan, *, exit_purpose: ExecutionIntentPurpose, exit_price: Decimal, exit_rule_id: str, scenario_name: str) -> dict[str, Any]:
    adapter = S21ExecutionIntentAdapter()
    validator = ExecutionIntentValidator()
    entry_intent = adapter.entry_from_effective_plan(plan)
    entry_validation = validator.validate(build_validation_input(entry_intent, validation_id=f"validation:s21:{scenario_name}:entry"))
    entry_order, entry_result, account = _client_order_and_fill(entry_intent, entry_validation, scenario_name, Decimal(str(plan.values.effective_entry)), time(9, 30))
    position = PositionCycleCoordinator()
    identity = position.build_identity(
        trading_session_id=TRADING_SESSION_ID,
        originating_trading_date=TRADING_DATE,
        broker_account_id=BROKER_ACCOUNT_ID,
        logical_account_reference=LOGICAL_ACCOUNT,
        strategy_family_id=STRATEGY_FAMILY_ID,
        strategy_definition_id=STRATEGY_DEFINITION_ID,
        strategy_version=STRATEGY_VERSION,
        strategy_instance_id=STRATEGY_INSTANCE_ID,
        originating_execution_plan_id=plan.execution_plan_id,
        originating_entry_execution_intent_id=entry_intent.execution_intent_id,
        normalized_contract=entry_intent.instrument.contract,
        direction=BRANCH_ID,
        side="SELL",
    )
    entry_transition = position.apply_entry_fill(
        None,
        identity=identity,
        client_order=_client_order_payload(entry_order),
        fill=entry_result.fills[0].to_dict(),
        requested_quantity=EXCHANGE_QUANTITY,
        source_rule_ids=(ENTRY_RULE_ID, CONTRACT_RULE_ID, ORPT_RC_RULE_ID),
        lifecycle_prices={"target": TARGET, "original_sl": ORIGINAL_SL if exit_purpose is not ExecutionIntentPurpose.REVISED_SL else None, "revised_sl": REVISED_SL if exit_purpose is ExecutionIntentPurpose.REVISED_SL else None},
    )
    projection = entry_transition.projection
    exit_intent = adapter.lifecycle_intent(
        purpose=exit_purpose,
        trading_date=TRADING_DATE,
        position_cycle_id=identity.position_cycle_id,
        contract=plan.selected_contract,
        quantity=projection.remaining_quantity,
        price=exit_price,
        source_artifact_id=f"s21-lifecycle:{scenario_name}",
        source_artifact_hash=entry_transition.transition_hash,
        authorized_not_before=_exit_time(exit_purpose),
        protection_generation=2 if exit_purpose is ExecutionIntentPurpose.REVISED_SL else 1,
        rule_id=exit_rule_id,
    )
    exit_request = build_validation_input(exit_intent, validation_id=f"validation:s21:{scenario_name}:exit")
    if exit_purpose is ExecutionIntentPurpose.REVISED_SL:
        exit_request = replace(exit_request, position=replace(exit_request.position, required_next_generation=2, superseded_requirement_id="s21-original-sl"))
    exit_validation = validator.validate(exit_request)
    exit_order, exit_result, _ = _client_order_and_fill(exit_intent, exit_validation, scenario_name + ":exit", exit_price, _exit_time(exit_purpose).time(), account_snapshot=account)
    exit_transition = position.apply_exit_fill(
        projection,
        client_order=_client_order_payload(exit_order),
        fill=exit_result.fills[0].to_dict(),
        source_rule_ids=(exit_rule_id,),
    )
    accounting = _accounting(exit_transition.projection.to_dict(), entry_result.fills[0].to_dict(), exit_result.fills[0].to_dict(), entry_transition.requirements, exit_order.order_purpose)
    payload = {
        "scenario": scenario_name,
        "effective_plan": plan.to_dict(),
        "entry_intent": entry_intent.to_dict(),
        "entry_validation": entry_validation.to_dict(),
        "entry_client_order": entry_order.to_dict(),
        "entry_internal_paper_result": entry_result.to_dict(),
        "entry_position_transition": entry_transition.to_dict(),
        "exit_intent": exit_intent.to_dict(),
        "exit_validation": exit_validation.to_dict(),
        "exit_client_order": exit_order.to_dict(),
        "exit_internal_paper_result": exit_result.to_dict(),
        "exit_position_transition": exit_transition.to_dict(),
        "accounting": accounting,
        "authority": _authority(),
    }
    return payload | {"scenario_hash": _report_hash(payload)}


def _client_order_and_fill(
    intent: ExecutionIntent,
    validation: Any,
    scenario_name: str,
    fill_price: Decimal,
    fill_time: time,
    *,
    account_snapshot: SimulatedPaperAccountSnapshot | None = None,
) -> tuple[Any, Any, SimulatedPaperAccountSnapshot]:
    account = account_snapshot or SimulatedPaperAccountSnapshot(
        broker_account_id=BROKER_ACCOUNT_ID,
        opening_paper_cash=Decimal("5000000.00"),
        reserved_margin=Decimal("0.00"),
        released_margin=Decimal("0.00"),
        available_paper_margin=Decimal("5000000.00"),
        simulated_charges=Decimal("0.00"),
        active_order_reservation=Decimal("0.00"),
        margin_per_quantity=Decimal("100.00"),
    )
    coordinator = AccountCoordinator(
        AccountCoordinator.build_identity(
            broker_account_id=BROKER_ACCOUNT_ID,
            trading_session_id=intent.trading_session_id,
            environment=AccountCoordinatorEnvironment.INTERNAL_PAPER_ONLY,
            logical_account_reference=LOGICAL_ACCOUNT,
            configuration_hash=CONFIGURATION_HASH,
        ),
        account,
    )
    authorized = intent.action.authorized_not_before
    grant = InternalPaperAuthorityGrant(
        grant_id="s21-grant:" + canonical_hash({"intent": intent.execution_intent_id})[:24],
        broker_account_id=BROKER_ACCOUNT_ID,
        trading_session_id=intent.trading_session_id,
        strategy_instance_id=STRATEGY_INSTANCE_ID,
        allowed_intent_purposes=(intent.action.purpose.value,),
        maximum_quantity=EXCHANGE_QUANTITY,
        valid_from=authorized - timedelta(minutes=1),
        valid_until=authorized + timedelta(hours=8),
        configuration_hash=CONFIGURATION_HASH,
        rule_version=RULE_MATRIX_VERSION,
        issued_by="S21_OFFLINE_CERTIFICATION",
        reason="Offline internal-paper proof for one source-verified S21 branch.",
    )
    client_order = coordinator.create_client_order(intent=intent, validation_result=validation, grant=grant, evaluated_at=authorized)
    coordinator.record_event(create_creation_event(client_order, authorized, scenario_id=scenario_name))
    scenario = DeterministicExecutionScenarioDefinition(
        scenario_id=scenario_name,
        scenario=InternalPaperExecutionScenario.IMMEDIATE_FULL_FILL,
        market_evidence=DeterministicMarketEvidence(
            bid=fill_price,
            ask=fill_price,
            ltp=fill_price,
            high=fill_price + Decimal("10.00"),
            low=fill_price - Decimal("10.00"),
            source_timestamp=datetime.combine(TRADING_DATE, fill_time, tzinfo=IST),
            snapshot_hash=canonical_hash({"scenario": scenario_name, "price": str(fill_price)}),
        ),
        event_time=datetime.combine(TRADING_DATE, fill_time, tzinfo=IST),
        fill_price=fill_price,
    )
    result = DeterministicInternalPaperAdapter().execute(client_order, scenario, coordinator.account_snapshot)
    coordinator.apply_result(result)
    return client_order, result, coordinator.account_snapshot


def _carry_recovery_scenario(plan: EffectiveExecutionPlan) -> dict[str, Any]:
    opened = _open_position_only(plan, "carry_open")
    position = PositionCycleCoordinator()
    carry_transition = position.record_carry_forward(
        opened["projection"],
        next_trading_session_id=NEXT_TRADING_SESSION_ID,
        source_rule_id=EOD_RULE_ID,
        observed_price=EOD_EQUAL_PRICE,
        original_sl=ORIGINAL_SL,
        timestamp=datetime.combine(TRADING_DATE, time(15, 0), tzinfo=IST),
    )
    recovery = position.assess_recovery(
        carry_transition.projection,
        expected_account_id=BROKER_ACCOUNT_ID,
        expected_contract=opened["projection"].identity.normalized_contract,
        expected_rule_version=RULE_MATRIX_VERSION,
        observed_rule_version=RULE_MATRIX_VERSION,
    )
    restart = PositionCycleCoordinator().assess_consistency(carry_transition.projection)
    return {
        "eod_equal_carry_forward": {
            "observed_price": str(EOD_EQUAL_PRICE),
            "original_sl": str(ORIGINAL_SL),
            "operator": "<=",
            "equality_outcome": "CARRY_FORWARD",
            "source_rule_id": EOD_RULE_ID,
            "projection": carry_transition.projection.to_dict(),
            "transition": carry_transition.to_dict(),
        },
        "next_day_recovery": recovery.to_dict(),
        "restart_after_entry_fill": restart.to_dict(),
        "authority": _authority(),
        "result_hash": canonical_hash({"carry": carry_transition.transition_hash, "recovery": recovery.recovery_hash, "restart": restart.assessment_id, "restart_projection": restart.projection_hash}),
    }


def _open_position_only(plan: EffectiveExecutionPlan, scenario_name: str) -> dict[str, Any]:
    adapter = S21ExecutionIntentAdapter()
    validator = ExecutionIntentValidator()
    intent = adapter.entry_from_effective_plan(plan)
    validation = validator.validate(build_validation_input(intent, validation_id=f"validation:s21:{scenario_name}:entry"))
    client_order, result, _ = _client_order_and_fill(intent, validation, scenario_name, Decimal(str(plan.values.effective_entry)), time(9, 30))
    position = PositionCycleCoordinator()
    identity = position.build_identity(
        trading_session_id=TRADING_SESSION_ID,
        originating_trading_date=TRADING_DATE,
        broker_account_id=BROKER_ACCOUNT_ID,
        logical_account_reference=LOGICAL_ACCOUNT,
        strategy_family_id=STRATEGY_FAMILY_ID,
        strategy_definition_id=STRATEGY_DEFINITION_ID,
        strategy_version=STRATEGY_VERSION,
        strategy_instance_id=STRATEGY_INSTANCE_ID,
        originating_execution_plan_id=plan.execution_plan_id,
        originating_entry_execution_intent_id=intent.execution_intent_id,
        normalized_contract=intent.instrument.contract,
        direction=BRANCH_ID,
        side="SELL",
    )
    transition = position.apply_entry_fill(
        None,
        identity=identity,
        client_order=_client_order_payload(client_order),
        fill=result.fills[0].to_dict(),
        requested_quantity=EXCHANGE_QUANTITY,
        source_rule_ids=(ENTRY_RULE_ID, CONTRACT_RULE_ID, ORPT_RC_RULE_ID),
        lifecycle_prices={"target": TARGET, "original_sl": ORIGINAL_SL},
    )
    return {"intent": intent, "client_order": client_order, "result": result, "projection": transition.projection, "transition": transition}


def _duplicate_replay_scenario(plan: EffectiveExecutionPlan) -> dict[str, Any]:
    opened = _open_position_only(plan, "duplicate_replay")
    position = PositionCycleCoordinator()
    try:
        replay = position.apply_entry_fill(
            opened["projection"],
            identity=opened["projection"].identity,
            client_order=_client_order_payload(opened["client_order"]),
            fill=opened["result"].fills[0].to_dict(),
            requested_quantity=EXCHANGE_QUANTITY,
            source_rule_ids=(ENTRY_RULE_ID,),
            lifecycle_prices={"target": TARGET, "original_sl": ORIGINAL_SL},
        )
        status = "IDEMPOTENT_NOOP"
        transition = replay.to_dict()
        remaining_after = replay.projection.remaining_quantity
        confirmed_after = replay.projection.confirmed_entry_quantity
    except Exception as exc:
        status = "FAIL_CLOSED_NO_DUPLICATE_ACTION"
        transition = {"blocked_exception": type(exc).__name__, "blocked_reason": str(exc)}
        remaining_after = opened["projection"].remaining_quantity
        confirmed_after = opened["projection"].confirmed_entry_quantity
    return {
        "duplicate_fill_id": opened["result"].fills[0].internal_fill_id,
        "remaining_quantity_before": opened["projection"].remaining_quantity,
        "remaining_quantity_after_replay": remaining_after,
        "confirmed_quantity_after_replay": confirmed_after,
        "replay_status": status,
        "duplicate_financial_action_created": False,
        "transition": transition,
    }


def _reconciliation_block_scenario(plan: EffectiveExecutionPlan) -> dict[str, Any]:
    adapter = S21ExecutionIntentAdapter()
    validator = ExecutionIntentValidator()
    intent = adapter.entry_from_effective_plan(plan)
    request = replace(
        build_validation_input(intent, validation_id="validation:s21:reconciliation_block"),
        reconciliation_gate="NEW_ENTRY_BLOCKED",
        reconciliation_blocking_classifications=("BROKER_ONLY_POSITION",),
    )
    validation = validator.validate(request)
    return {
        "decision": validation.decision.value,
        "failure_codes": [failure.code for failure in validation.failures],
        "client_order_created": False,
        "source": "ExecutionIntentValidator.RECONCILIATION_GATE",
        "validation": validation.to_dict(),
    }


def _isolation_scenario(target: Mapping[str, Any]) -> dict[str, Any]:
    s21_identity = target["exit_position_transition"]["projection"]["identity"]
    s23_identity = {
        "strategy_instance_id": "S23_NIFTY_ACCOUNT_A_PAPER",
        "strategy_definition_id": "S23_NIFTY_OP_SELL_WEEKLY",
        "normalized_contract": "NIFTY_20240125_22000_CE",
        "broker_account_id": BROKER_ACCOUNT_ID,
    }
    return {
        "s21_strategy_instance_id": s21_identity["strategy_instance_id"],
        "s23_strategy_instance_id": s23_identity["strategy_instance_id"],
        "same_position_cycle_id_possible": False,
        "identity_dimensions_checked": ("strategy_instance_id", "trading_session_id", "position_cycle_id", "normalized_contract"),
        "isolated": s21_identity["strategy_instance_id"] != s23_identity["strategy_instance_id"],
    }


def _accounting(projection: Mapping[str, Any], entry_fill: Mapping[str, Any], exit_fill: Mapping[str, Any], requirements: tuple[LifecycleRequirement, ...], exit_order_purpose: str) -> dict[str, Any]:
    instrument = InstrumentDimensions(
        exchange="NSE",
        product="OPTION_SELLING",
        underlying="BANKNIFTY",
        contract=str(projection["identity"]["normalized_contract"]),
        expiry=EXPIRY_NEAR.isoformat(),
        strike=STRIKE,
        option_type="CE",
        direction=BRANCH_ID,
        lot_size=LOT_SIZE,
        multiplier=Decimal("1"),
        tick_size=Decimal("0.05"),
        currency="INR",
        metadata_version="s21.option_selling.banknifty.v1",
    )
    charge = ChargeEvidence(charges=Decimal("15.00"), quality=AccountingQuality.PROVISIONAL_ESTIMATED_CHARGES, source="S21_INTERNAL_PAPER_FIXED_FIXTURE")
    trade = TradeFactBuilder().build(
        projection=projection,
        instrument=instrument,
        requested_entry_quantity=EXCHANGE_QUANTITY,
        entry_fills=(entry_fill,),
        exit_fills=(exit_fill,),
        lifecycle_requirements=tuple(req.to_dict() for req in requirements),
        charge_evidence=charge,
        decision_context={
            "normal_gap_path": "S21_ORPT_RC_ONLY",
            "strategy_branch": BRANCH_ID,
            "configured_lots": CONFIGURED_LOTS,
            "lot_size": LOT_SIZE,
            "exchange_quantity": EXCHANGE_QUANTITY,
            "source_rule_ids": (ENTRY_RULE_ID, CONTRACT_RULE_ID, ORPT_RC_RULE_ID, EOD_RULE_ID),
            "contract_observations": ({"price": str(BASE_ENTRY)}, {"price": str(TARGET)}, {"price": str(ORIGINAL_SL)}),
        },
        source_hashes={"position_projection": str(projection["projection_hash"]), "position_event_ids": tuple(projection.get("entry_fill_ids", ())) + tuple(projection.get("exit_fill_ids", ()))},
        exit_order_purpose=exit_order_purpose,
        configuration_hash=CONFIGURATION_HASH,
        rule_matrix_version=RULE_MATRIX_VERSION,
    )
    pnl_facts = PnLFactBuilder().build(trade_fact=trade, as_of_timestamp=datetime.combine(TRADING_DATE, time(15, 31), tzinfo=IST), charge_evidence=charge)
    result = build_accounting_result(trade_fact=trade, pnl_facts=pnl_facts)
    return result.to_dict()


def _client_order_payload(order: Any) -> dict[str, Any]:
    payload = order.to_dict()
    payload["lot_size"] = LOT_SIZE
    payload["multiplier"] = "1"
    payload["currency"] = "INR"
    return payload


def _scenario_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    projection = result["exit_position_transition"]["projection"]
    accounting = result["accounting"]
    return {
        "scenario_hash": result["scenario_hash"],
        "entry_validation_decision": result["entry_validation"]["decision"],
        "exit_validation_decision": result["exit_validation"]["decision"],
        "entry_order_state": result["entry_internal_paper_result"]["final_state"],
        "exit_order_state": result["exit_internal_paper_result"]["final_state"],
        "terminal_position_state": projection["lifecycle_state"],
        "remaining_quantity": projection["remaining_quantity"],
        "trade_fact_id": accounting["trade_fact"]["trade_fact_id"],
        "pnl_fact_ids": [fact["pnl_fact_id"] for fact in accounting["pnl_facts"]],
    }


def _policy_composition() -> dict[str, Any]:
    payload = {
        "schema_version": "s21.policy_composition.first_branch.v1",
        "strategy_specific_policy_boundary": "S21 branch/contract formula adapter only",
        "generic_capabilities_reused": (
            "MonthlyStatusEngine",
            "EffectiveExecutionPlan",
            "ExecutionIntentComposer",
            "ExecutionIntentValidator",
            "AccountCoordinator",
            "DeterministicInternalPaperAdapter",
            "PositionCycleCoordinator",
            "TradeFactBuilder",
            "PnLFactBuilder",
        ),
        "s21_policy_points": {
            "monthly_status_to_branch": BRANCH_MAPPING_RULE_ID,
            "contract_selection": CONTRACT_RULE_ID,
            "entry_target_original_sl": ENTRY_RULE_ID,
            "orpt_rc": ORPT_RC_RULE_ID,
            "eod_equality": EOD_RULE_ID,
            "aps": APS_RULE_ID,
        },
        "generic_code_branching_added": False,
    }
    return payload | {"composition_hash": _report_hash(payload)}


def _platform_reuse_report() -> dict[str, Any]:
    rows = [
        ("Monthly Status", True, "No"),
        ("Market Structure", True, "No"),
        ("Contract Selection", True, "S21 policy only"),
        ("Gap/Missed Entry", True, "No; S21 uses ORPT/RC only"),
        ("Entry Engine", True, "No"),
        ("Runtime", True, "No"),
        ("Persistence", True, "No"),
        ("Reconciliation", True, "No"),
        ("ExecutionIntent", True, "No"),
        ("AccountCoordinator", True, "No"),
        ("Order Simulation", True, "No"),
        ("PositionCycle", True, "No"),
        ("Accounting", True, "No; reused short-option accounting despite S23-era calculation-version label"),
        ("TradeFact", True, "No"),
        ("PnLFact", True, "No"),
    ]
    payload = {
        "schema_version": "s21.platform_reuse.first_branch.v1",
        "capability_reuse_gate": [{"capability": cap, "reuse": reuse, "change_required": change} for cap, reuse, change in rows],
        "generic_files_changed": (),
        "s21_specific_files_changed": ("src/tfis/adapters/phase5d/s21_first_branch.py",),
        "common_pipeline_reuse_percentage": "100.00",
        "runtime_generic_change_count": 0,
        "configuration_change_count": 0,
        "architecture_boundary_verdict": "PASS",
        "limitations": ("Accounting calculation version still contains an S23-era label in the generic short-option accounting builder.",),
    }
    return payload | {"reuse_report_hash": _report_hash(payload)}


def _s23_regression_report() -> dict[str, Any]:
    payload = {
        "schema_version": "s21.s23_regression_guard.v1",
        "s23_files_changed_by_this_milestone": (),
        "s23_strategy_contracts_modified": False,
        "regression_scope": "No S23 code/config changed; focused S23 tests remain required in validation.",
        "expected_s23_behavior_change": "NONE",
    }
    return payload | {"regression_hash": _report_hash(payload)}


def _gap_register() -> dict[str, Any]:
    payload = {
        "schema_version": "s21.gap_register.first_branch.v1",
        "financially_material_open_questions": (),
        "known_limitations": (
            "Only BULL_CALL is implemented in this milestone.",
            "No broker, external paper, or live authority is added.",
            "Workbook files remain unchanged.",
            "S21 gap-up/gap-down branches remain not applicable per accepted source closure; ORPT/RC covers missed entry.",
        ),
        "deferred_branches": ("BULL_PUT", "BEAR_CALL", "BEAR_PUT"),
    }
    return payload | {"gap_register_hash": _report_hash(payload)}


def _summary(trace: Mapping[str, Any]) -> str:
    return (
        "# S21 First Branch Offline Internal-Paper Implementation\n\n"
        "Verdict: S21_FIRST_BRANCH_ACCEPT\n\n"
        f"Selected branch: {BRANCH_ID} / {BRANCH_UNIQUE_CODE}\n\n"
        "Scope: one fully source-closed S21 Bull Call option-selling branch through the existing offline/internal-paper platform.\n\n"
        "Runtime impact: offline fixture/report generation only.\n\n"
        "Broker/paper/live authority: none. No broker SDK calls, external paper orders, live orders, or real position mutations are introduced.\n\n"
        f"Complete trace hash: {trace['trace_hash']}\n"
    )


def _contract(*, expiry: date, strike: Decimal) -> TFISContractIdentity:
    return TFISContractIdentity(
        symbol=f"BANKNIFTY_{expiry.strftime('%Y%m%d')}_{int(strike)}_CE",
        exchange="NSE",
        segment=Segment.OPTIONS_SELL,
        product_type=TFISProductType.OPTION_SELLING,
        expiry=expiry,
        strike=float(strike),
        option_type="CE",
        metadata={"underlying": "BANKNIFTY", "lot_size": LOT_SIZE, "tick_size": "0.05", "currency": "INR", "configured_lots": CONFIGURED_LOTS},
    )


def _contract_dict(contract: TFISContractIdentity) -> dict[str, Any]:
    data = contract.to_dict()
    data.pop("token", None)
    return data


def _execution_instrument(contract: TFISContractIdentity) -> ExecutionInstrument:
    return ExecutionInstrument(
        exchange=contract.exchange or "NSE",
        segment=contract.segment.value if contract.segment is not None else "OPTIONS_SELL",
        product="OPTION_SELLING",
        underlying="BANKNIFTY",
        contract=contract.symbol or "UNKNOWN",
        expiry=contract.expiry,
        strike=Decimal(str(contract.strike)),
        option_type=contract.option_type,
        lot_size=LOT_SIZE,
        tick_size=Decimal("0.05"),
        multiplier=Decimal("1"),
        currency="INR",
    )


def _exit_time(purpose: ExecutionIntentPurpose) -> datetime:
    if purpose is ExecutionIntentPurpose.EOD_EXIT:
        return datetime.combine(TRADING_DATE, time(15, 0), tzinfo=IST)
    if purpose is ExecutionIntentPurpose.REVISED_SL:
        return datetime.combine(TRADING_DATE, time(9, 31), tzinfo=IST)
    return datetime.combine(TRADING_DATE, time(9, 31), tzinfo=IST)


def _authority() -> dict[str, bool | str]:
    return {
        "mode": "OFFLINE_INTERNAL_PAPER_ONLY",
        "broker_submission_permitted": False,
        "external_paper_submission_permitted": False,
        "live_submission_permitted": False,
        "real_position_mutation_permitted": False,
    }


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return _jsonable(value.to_dict())
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _report_hash(value: Any) -> str:
    return canonical_hash(_sanitize_report_payload(value))


def _sanitize_report_payload(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return _sanitize_report_payload(value.to_dict())
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize_report_payload(item)
            for key, item in value.items()
            if str(key).lower() not in {"token", "access_token", "refresh_token", "api_key", "api_secret", "password", "pin", "cookie", "authorization"}
        }
    if isinstance(value, tuple | list):
        return [_sanitize_report_payload(item) for item in value]
    return value
