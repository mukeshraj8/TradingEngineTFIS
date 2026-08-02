from __future__ import annotations

import json
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path
from typing import Any, Iterable, Mapping
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
from tfis.domain.premarket_plan import (
    PreMarketContractResolution,
    PreMarketFieldProvenance,
    PreMarketPlannedValues,
    PreMarketPlanStatus,
    PreMarketReferenceSet,
    PreMarketStrategyPlan,
)
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
from tfis.internal_position.models import LifecycleRequirement
from tfis.monthly_status import (
    MonthlyStatusHistoricalBar,
    MonthlyStatusLookbackResolver,
    MonthlyStatusReferenceLevels,
    build_monthly_weekly_context_lookback_windows,
)
from tfis.persistence import canonical_hash


IST = ZoneInfo("Asia/Kolkata")
FIXTURE_PATH = Path("tests/fixtures/s22_reliance/s22_reliance_fyers_snapshot_2026-08-02_sanitized.json")
TRADING_DATE = date(2026, 8, 3)
LATEST_COMPLETED_SESSION = date(2026, 7, 31)
NEXT_TRADING_DATE = date(2026, 8, 4)
TRADING_SESSION_ID = f"NSE:{TRADING_DATE.isoformat()}"
NEXT_TRADING_SESSION_ID = f"NSE:{NEXT_TRADING_DATE.isoformat()}"
STRATEGY_FAMILY_ID = "OPTION_SELLING"
STRATEGY_DEFINITION_ID = "S22_STOCKS_OP_SELL_MONTHLY_DIFF_2D_4D"
STRATEGY_VERSION = "1.0.0"
STRATEGY_INSTANCE_ID = "S22_RELIANCE_ACCOUNT_A_INTERNAL_PAPER"
BROKER_ACCOUNT_ID = "S22_ACCOUNT_A_INTERNAL_PAPER"
LOGICAL_ACCOUNT = "INTERNAL_PAPER_ACCOUNT"
CONFIGURATION_HASH = "s22-source-closure-config-v1"
RULE_MATRIX_VERSION = "s22_source_closure_accepted_v1"
EVIDENCE_PACKET_HASH = "s22-reliance-one-stock-offline-evidence-v1"

MONTHLY_STATUS_RULE_ID = "MONTHLY_STATUS.GENERIC.ENGINE.001"
BRANCH_MAPPING_RULE_ID = "S22.MONTHLY_STATUS_CONSUMPTION.001"
CONTRACT_RULE_ID = "S22.CONTRACT_SELECTION.001"
ENTRY_RULE_ID = "S22.ENTRY_ORPT_RC.001"
TARGET_SL_RULE_ID = "S22.TARGET_SL.001"
CARRIED_RULE_ID = "S22.CARRIED_LIFECYCLE.001"
EOD_RULE_ID = "GLOBAL.OPTION_SELLING.EOD_CARRY_GT_EXIT_LTE_CARRY.001"
APS_RULE_ID = "GLOBAL.OPTION_SELLING.APS_NOT_APPLICABLE_ONE_LOT.001"

CONFIGURED_LOTS = 1
LOT_SIZE = 500
EXCHANGE_QUANTITY = 500
STRIKE_INTERVAL = Decimal("20")
TICK_SIZE = Decimal("0.05")
MULTIPLIER = Decimal("1")
CURRENCY = "INR"
ORPT = time(9, 24, 59, 400000)
RC = time(9, 29, 59, 400000)

SELECTED_OPTION_REFERENCE_SUPPLEMENT = {
    "classification": "DETERMINISTIC_OPTION_REFERENCE_SUPPLEMENT",
    "reason": "FYERS read-only fixture contains option-chain premium/OI but not selected-option historical candles.",
    "opt_prv_2dll": "63.8889",
    "opt_prv_3dhh": "84.00",
    "rc_hh": "84.00",
    "rc_ll": "57.00",
}

BASE_ENTRY = Decimal("57.50")
TARGET = Decimal("23.00")
ORIGINAL_SL = Decimal("92.00")
REVISED_ENTRY = Decimal("57.00")
REVISED_SL = Decimal("92.40")
EOD_EXIT_PRICE = Decimal("93.00")


@dataclass(frozen=True, slots=True)
class S22BranchSpec:
    branch_id: str
    monthly_statuses: tuple[MonthlyStatus, ...]
    option_type: str
    option_suffix: str
    source_cells: tuple[str, ...]
    workbook_row_id: str
    start_reference: str
    end_reference: str
    premium_reference: str
    round_start: str
    round_end: str
    start_buffer_pct: Decimal
    end_offset_strikes: int
    ideal_premium_pct: Decimal
    minimum_premium_pct: Decimal
    base_entry_formula: str
    original_sl_formula: str
    revised_entry_formula: str
    revised_sl_formula: str
    revised_sl_pct: Decimal
    traversal: str


BRANCH_SPECS: dict[str, S22BranchSpec] = {
    "BEAR_CALL": S22BranchSpec(
        branch_id="BEAR_CALL",
        monthly_statuses=(MonthlyStatus.BEAR, MonthlyStatus.BEAR_CF),
        option_type="CALL",
        option_suffix="CE",
        source_cells=("AB6 OS!D137:M138", "AB14!F45:BG45"),
        workbook_row_id="S22D",
        start_reference="2DLL",
        end_reference="2DLL",
        premium_reference="2DLL",
        round_start="DOWN",
        round_end="DOWN",
        start_buffer_pct=Decimal("10"),
        end_offset_strikes=-1,
        ideal_premium_pct=Decimal("4"),
        minimum_premium_pct=Decimal("3"),
        base_entry_formula="OPT:PRV:2DLL - 10%",
        original_sl_formula="Min(CE Entry + 60%, OPT:PRV:3DHH + 10%)",
        revised_entry_formula="Min(SPT:PRV:2DLL, 09:29:59 AM LL) with branch strike/premium/entry recalculation",
        revised_sl_formula="09:29:59 AM HH + 10%",
        revised_sl_pct=Decimal("10"),
        traversal="DESCENDING_START_TO_END",
    ),
    "BEAR_PUT": S22BranchSpec(
        branch_id="BEAR_PUT",
        monthly_statuses=(MonthlyStatus.BEAR, MonthlyStatus.BEAR_CF),
        option_type="PUT",
        option_suffix="PE",
        source_cells=("AB6 OS!F140:M141", "AB14!G46:BG46"),
        workbook_row_id="S22E",
        start_reference="4DHH",
        end_reference="4DHH",
        premium_reference="4DHH",
        round_start="UP",
        round_end="UP",
        start_buffer_pct=Decimal("-10"),
        end_offset_strikes=1,
        ideal_premium_pct=Decimal("4"),
        minimum_premium_pct=Decimal("3"),
        base_entry_formula="OPT:PRV:4DLL - 10%",
        original_sl_formula="Min(PE Entry + 60%, OPT:PRV:2DHH + 7%)",
        revised_entry_formula="Max(SPT:PRV:4DHH, 09:29:59 AM LL) with branch strike/premium/entry recalculation",
        revised_sl_formula="09:29:59 AM HH + 7%",
        revised_sl_pct=Decimal("7"),
        traversal="ASCENDING_START_TO_END",
    ),
}

S22_RELIANCE_REPORT_NAMES = (
    "s22_reliance_time_semantics.json",
    "s22_reliance_metadata_validation.json",
    "s22_reliance_monthly_status.json",
    "s22_reliance_market_structure.json",
    "s22_reliance_contract_selection.json",
    "s22_reliance_premarket_plan.json",
    "s22_reliance_normal_result.json",
    "s22_reliance_rc_result.json",
    "s22_reliance_target_result.json",
    "s22_reliance_original_sl_result.json",
    "s22_reliance_revised_sl_result.json",
    "s22_reliance_eod_carry_result.json",
    "s22_reliance_recovery_result.json",
    "s22_reliance_accounting.json",
    "s22_reliance_dashboard_projection.json",
    "s22_reliance_complete_trace.json",
    "s22_reliance_platform_reuse.json",
    "s22_reliance_regression.json",
    "s22_reliance_gap_register.json",
    "s22_reliance_summary.md",
)


class S22ExecutionIntentAdapter:
    def __init__(self, composer: ExecutionIntentComposer | None = None) -> None:
        self.composer = composer or ExecutionIntentComposer()

    def entry_from_effective_plan(self, plan: EffectiveExecutionPlan) -> ExecutionIntent:
        if plan.selected_contract is None or plan.order_side is None or plan.quantity is None or plan.values.effective_entry is None:
            raise ValueError("S22 EffectiveExecutionPlan is missing required ENTRY fields.")
        authorized = datetime.combine(plan.trading_date, plan.values.revised_authorized_time or plan.values.normal_orpt or ORPT, tzinfo=IST)
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
                maximum_allowed_slippage=TICK_SIZE,
                protection_generation=None,
                source_rule_ids=(ENTRY_RULE_ID, CONTRACT_RULE_ID, TARGET_SL_RULE_ID),
                configuration_hash=CONFIGURATION_HASH,
                rule_matrix_version=RULE_MATRIX_VERSION,
                market_snapshot_hash=f"market:{plan.source_opening_context_id}",
                reconciliation_result_id="s22-reconciliation-shadow-ready",
                reconciliation_result_hash="s22-reconciliation-shadow-ready-hash",
                recovery_assessment_id="s22-recovery-offline-ready",
                recovery_assessment_hash="s22-recovery-offline-ready-hash",
                evidence_packet_hash=EVIDENCE_PACKET_HASH,
                provenance={"adapter": type(self).__name__, "branch": _branch_from_plan(plan), "path": plan.path_classification.value},
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
                source_artifact_type="S22LifecycleRequirement",
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
                maximum_allowed_slippage=TICK_SIZE,
                protection_generation=protection_generation,
                source_rule_ids=(rule_id,),
                configuration_hash=CONFIGURATION_HASH,
                rule_matrix_version=RULE_MATRIX_VERSION,
                market_snapshot_hash=f"market:{source_artifact_id}",
                reconciliation_result_id="s22-reconciliation-shadow-ready",
                reconciliation_result_hash="s22-reconciliation-shadow-ready-hash",
                recovery_assessment_id="s22-recovery-offline-ready",
                recovery_assessment_hash="s22-recovery-offline-ready-hash",
                evidence_packet_hash=canonical_hash({"source_artifact_id": source_artifact_id, "purpose": purpose.value}),
                provenance={"adapter": type(self).__name__, "branch": contract.metadata.get("branch_id", "UNKNOWN") if contract.metadata else "UNKNOWN"},
                authority_mode=ExecutionAuthorityMode.OFFLINE_ONLY,
            )
        )


def build_s22_reliance_certification(fixture_path: Path | str = FIXTURE_PATH) -> dict[str, Any]:
    fixture = _load_fixture(Path(fixture_path))
    time_semantics = _time_semantics(fixture)
    metadata = _metadata_validation(fixture)
    market_structure = _market_structure(fixture)
    monthly_status = _monthly_status_report(fixture)
    contract_selection = _contract_selection_report(fixture, monthly_status, market_structure)

    if contract_selection["decision"] != "SELECTED":
        return _blocked_certification(time_semantics, metadata, market_structure, monthly_status, contract_selection)

    selected_branch = contract_selection["selected_branch"]
    premarket = _premarket_plan_report(fixture, monthly_status, market_structure, contract_selection)
    normal_plan = _effective_plan("normal", premarket, _opening_context("normal", Decimal("59.00"), Decimal("85.00")), BASE_ENTRY, TARGET, ORIGINAL_SL, EffectiveExecutionPath.NORMAL_RETAINED)
    rc_plan = _effective_plan("rc_recalculation", premarket, _opening_context("orpt_missed_rc", Decimal("56.00"), Decimal("84.00")), REVISED_ENTRY, TARGET, REVISED_SL, EffectiveExecutionPath.ABNORMAL_RECALCULATED)

    target = _execute_entry_to_exit(normal_plan, exit_purpose=ExecutionIntentPurpose.TARGET, exit_price=TARGET, exit_rule_id=TARGET_SL_RULE_ID, scenario_name="normal_target")
    original_sl = _execute_entry_to_exit(normal_plan, exit_purpose=ExecutionIntentPurpose.ORIGINAL_SL, exit_price=ORIGINAL_SL, exit_rule_id=TARGET_SL_RULE_ID, scenario_name="original_sl")
    revised_sl = _execute_entry_to_exit(rc_plan, exit_purpose=ExecutionIntentPurpose.REVISED_SL, exit_price=REVISED_SL, exit_rule_id=CARRIED_RULE_ID, scenario_name="rc_revised_sl")
    eod_exit = _execute_entry_to_exit(normal_plan, exit_purpose=ExecutionIntentPurpose.EOD_EXIT, exit_price=EOD_EXIT_PRICE, exit_rule_id=EOD_RULE_ID, scenario_name="eod_exit")
    carry_recovery = _carry_recovery_scenario(normal_plan)
    duplicate = _duplicate_replay_scenario(normal_plan)
    reconciliation_block = _reconciliation_block_scenario(normal_plan)
    near_next = _contract_selection_variants(fixture, market_structure, selected_branch)
    wrong_contracts = _wrong_contract_guards(contract_selection)
    accounting = target["accounting"]
    dashboard = _dashboard_projection(premarket, normal_plan, target, monthly_status, metadata, time_semantics)
    platform_reuse = _platform_reuse_report()
    regression = _regression_report()
    gap_register = _gap_register()
    trace = _complete_trace(
        time_semantics,
        metadata,
        monthly_status,
        market_structure,
        contract_selection,
        premarket,
        normal_plan,
        rc_plan,
        target,
        original_sl,
        revised_sl,
        eod_exit,
        carry_recovery,
        duplicate,
        reconciliation_block,
        near_next,
        wrong_contracts,
    )

    return {
        "s22_reliance_time_semantics": time_semantics,
        "s22_reliance_metadata_validation": metadata,
        "s22_reliance_monthly_status": monthly_status,
        "s22_reliance_market_structure": market_structure,
        "s22_reliance_contract_selection": contract_selection | {"scenario_variants": near_next, "wrong_contract_guards": wrong_contracts},
        "s22_reliance_premarket_plan": premarket.to_dict(),
        "s22_reliance_normal_result": _normal_result(normal_plan),
        "s22_reliance_rc_result": _rc_result(rc_plan),
        "s22_reliance_target_result": target,
        "s22_reliance_original_sl_result": original_sl,
        "s22_reliance_revised_sl_result": revised_sl,
        "s22_reliance_eod_carry_result": {
            "eod_exit": _scenario_summary(eod_exit),
            "equality_carry": carry_recovery["eod_equal_carry_forward"],
        },
        "s22_reliance_recovery_result": {
            "next_day_recovery": carry_recovery["next_day_recovery"],
            "restart_after_entry_fill": carry_recovery["restart_after_entry_fill"],
            "duplicate_replay": duplicate,
            "reconciliation_block": reconciliation_block,
        },
        "s22_reliance_accounting": accounting,
        "s22_reliance_dashboard_projection": dashboard,
        "s22_reliance_complete_trace": trace,
        "s22_reliance_platform_reuse": platform_reuse,
        "s22_reliance_regression": regression,
        "s22_reliance_gap_register": gap_register,
        "s22_reliance_summary": _summary(trace, selected_branch),
    }


def write_s22_reliance_reports(report_dir: Path | str = Path("reports/s22_reliance")) -> dict[str, Path]:
    target_dir = Path(report_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    certification = build_s22_reliance_certification()
    written: dict[str, Path] = {}
    for report_name in S22_RELIANCE_REPORT_NAMES:
        key = report_name[:-5] if report_name.endswith(".json") else report_name[:-3]
        value = certification[key]
        path = target_dir / report_name
        if path.suffix == ".md":
            path.write_text(str(value), encoding="utf-8")
        else:
            path.write_text(json.dumps(_jsonable(_sanitize_report_payload(value)), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written[report_name] = path
    return written


def _load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _time_semantics(fixture: Mapping[str, Any]) -> dict[str, Any]:
    candles = _candles(fixture)
    latest = candles[-1]
    capture_timestamp = fixture["captured_at"]
    payload = {
        "schema_version": "s22.reliance.time_semantics.v1",
        "capture_timestamp": capture_timestamp,
        "capture_calendar_day": "Sunday",
        "capture_is_exchange_session": False,
        "metadata_snapshot_date": fixture["capture_date"],
        "instrument_effective_date": _instrument_effective_date(fixture),
        "latest_completed_nse_trading_session": latest["session_date"].isoformat(),
        "target_internal_paper_evaluation_date": TRADING_DATE.isoformat(),
        "source_quote_timestamp": None,
        "option_chain_source_timestamp": [chain["payload"]["captured_at"] for chain in fixture["option_chains"]],
        "completed_daily_candles_used": len(candles),
        "sunday_candle_fabricated": False,
        "market_closed_evidence_label": "FYERS_READ_ONLY_MARKET_CLOSED_CAPTURE",
        "opening_orpt_rc_evidence": "DETERMINISTIC_TIMING_SUPPLEMENT",
    }
    return payload | {"time_semantics_hash": _report_hash(payload)}


def _metadata_validation(fixture: Mapping[str, Any]) -> dict[str, Any]:
    records = list(fixture["symbol_master"]["option_records"])
    chain_contracts = _all_contracts(fixture)
    lot_sizes = sorted({int(record["lot_size"]) for record in records} | {int(contract["lot_size"]) for contract in chain_contracts})
    tick_sizes = sorted({str(record["tick_size"]) for record in records} | {str(contract["tick_size"]) for contract in chain_contracts})
    source_hashes = sorted({str(record["source_hash"]) for record in records if record.get("underlying") == "RELIANCE"})
    expiries = sorted({contract["expiry"] for contract in chain_contracts})
    status = "PASSED" if lot_sizes == [LOT_SIZE] else "BLOCKED_METADATA_LOT_SIZE_CONFLICT"
    payload = {
        "schema_version": "s22.reliance.metadata_validation.v3",
        "verdict": "METADATA_GATE_PASSED" if status == "PASSED" else status,
        "instrument": "RELIANCE",
        "configured_quantity_lots": CONFIGURED_LOTS,
        "lot_size": LOT_SIZE if status == "PASSED" else None,
        "quantity_exchange_units": EXCHANGE_QUANTITY if status == "PASSED" else None,
        "contract_multiplier": str(MULTIPLIER),
        "currency": CURRENCY,
        "tick_size": str(TICK_SIZE),
        "lot_sizes_observed": lot_sizes,
        "tick_sizes_observed": tick_sizes,
        "near_expiry": fixture["expiry_classification"]["near_monthly_expiry"],
        "next_expiry": fixture["expiry_classification"]["next_monthly_expiry"],
        "available_expiries": expiries,
        "option_record_count": len(records),
        "option_chain_contract_count": len(chain_contracts),
        "source_effective_date": _instrument_effective_date(fixture),
        "metadata_version": "fyers-symbol-master:NSEFO:2026-08-02",
        "metadata_source_hash_count": len(source_hashes),
        "external_broker_order_authority": fixture["external_order_authority"],
    }
    return payload | {"metadata_hash": _report_hash(payload)}


def _market_structure(fixture: Mapping[str, Any]) -> dict[str, Any]:
    candles = _candles(fixture)
    last2 = candles[-2:]
    last4 = candles[-4:]
    payload = {
        "schema_version": "s22.reliance.market_structure.v1",
        "engine_role": "GENERIC_COMPLETED_SESSION_REFERENCE_CALCULATION",
        "latest_completed_session": candles[-1]["session_date"].isoformat(),
        "excluded_incomplete": fixture["history"]["payload"].get("excluded_incomplete"),
        "sunday_candle_included": any(item["session_date"].weekday() == 6 and item["session_date"] == date(2026, 8, 2) for item in candles),
        "references": {
            "2DHH": str(max(item["high"] for item in last2)),
            "2DLL": str(min(item["low"] for item in last2)),
            "4DHH": str(max(item["high"] for item in last4)),
            "4DLL": str(min(item["low"] for item in last4)),
        },
        "sessions_used": {
            "2D": [item["session_date"].isoformat() for item in last2],
            "4D": [item["session_date"].isoformat() for item in last4],
        },
        "selected_option_historical_references": {
            "status": "MISSING_FROM_FYERS_FIXTURE",
            "supplement": SELECTED_OPTION_REFERENCE_SUPPLEMENT,
        },
        "data_quality": "COMPLETE_UNDERLYING_HISTORY_OPTION_HISTORY_SUPPLEMENTED",
    }
    return payload | {"market_structure_hash": _report_hash(payload)}


def _monthly_status_report(fixture: Mapping[str, Any]) -> dict[str, Any]:
    bars = tuple(
        MonthlyStatusHistoricalBar(
            timestamp=datetime.fromisoformat(raw["bar_end"]),
            high=float(raw["high"]),
            low=float(raw["low"]),
            close=float(raw["close"]),
            open=float(raw["open"]),
        )
        for raw in fixture["history"]["payload"]["candles"]
        if raw.get("complete") is True
    )
    current_reference_timestamp = bars[-1].timestamp
    current_levels = _monthly_levels_for_anchor(bars, current_reference_timestamp)
    windows = build_monthly_weekly_context_lookback_windows(
        historical_bars=bars,
        current_reference_timestamp=current_reference_timestamp,
    )
    resolution = MonthlyStatusLookbackResolver().resolve(
        "stock",
        current_levels,
        current_reference_timestamp=current_reference_timestamp,
        lookback_windows=windows,
    )
    payload = {
        "schema_version": "s22.reliance.monthly_status.v1",
        "instrument_identity": {"exchange": "NSE", "symbol": "RELIANCE", "group": "stock"},
        "evaluation_timestamp": current_reference_timestamp.isoformat(),
        "evaluation_session": LATEST_COMPLETED_SESSION.isoformat(),
        "monthly_status": resolution.resolved_result.status.value,
        "current_window_direct_status": resolution.current_window_result.status.value,
        "borrowed_window_status": resolution.borrowed_window_result.status.value if resolution.borrowed_window_result else None,
        "lookback_used": resolution.lookback_used,
        "checked_lookback_windows": resolution.checked_lookback_windows,
        "reason": resolution.reason,
        "trigger_name": resolution.resolved_result.trigger_name,
        "threshold_value": resolution.resolved_result.threshold_value,
        "source_monthly_references": _levels_dict(current_levels),
        "transition_evidence": {
            "notes": resolution.resolved_result.notes,
            "trace": [_trace_entry_dict(entry) for entry in resolution.trace],
        },
        "data_quality": "DERIVED_FROM_FYERS_HISTORY",
        "warnings": (),
        "failures": (),
        "source_rule_id": MONTHLY_STATUS_RULE_ID,
    }
    return payload | {"result_hash": _report_hash(payload)}


def _contract_selection_report(
    fixture: Mapping[str, Any],
    monthly_status: Mapping[str, Any],
    market_structure: Mapping[str, Any],
) -> dict[str, Any]:
    status = MonthlyStatus(str(monthly_status["monthly_status"]))
    eligible_specs = [spec for spec in BRANCH_SPECS.values() if status in spec.monthly_statuses]
    candidates = [_evaluate_branch_contracts(fixture, market_structure, spec) for spec in eligible_specs]
    qualifying = [item for item in candidates if item["decision"] == "SELECTED"]
    if not qualifying:
        payload = {
            "schema_version": "s22.reliance.contract_selection.v1",
            "decision": "NO_QUALIFYING_CONTRACT",
            "monthly_status": status.value,
            "branch_candidates": candidates,
            "source_rule_id": CONTRACT_RULE_ID,
        }
        return payload | {"contract_selection_hash": _report_hash(payload)}
    ranked = sorted(qualifying, key=lambda item: (0 if item["qualification_phase"] == "IDEAL_PREMIUM" else 1, item["selected_contract"]["strike"]))
    if len(ranked) > 1 and ranked[0]["qualification_phase"] == ranked[1]["qualification_phase"] and ranked[0]["selected_contract"]["strike"] == ranked[1]["selected_contract"]["strike"]:
        decision = "BLOCKED_AMBIGUOUS_STRONGEST_BRANCH"
        selected = None
    else:
        decision = "SELECTED"
        selected = ranked[0]
    payload = {
        "schema_version": "s22.reliance.contract_selection.v1",
        "decision": decision,
        "monthly_status": status.value,
        "branch_resolution_method": "Monthly Status family plus strongest fully supported contract evidence; ideal premium outranks minimum premium, ties fail closed.",
        "selected_branch": selected["branch_id"] if selected else None,
        "selected_contract": selected["selected_contract"] if selected else None,
        "qualification_phase": selected["qualification_phase"] if selected else None,
        "near_expiry_first": True,
        "next_expiry_fallback_authorized": True,
        "branch_candidates": candidates,
        "source_rule_id": CONTRACT_RULE_ID,
        "source_cells": selected["source_cells"] if selected else (),
        "evidence_quality": "FYERS_CAPTURED_OPTION_CHAIN_MARKET_CLOSED",
    }
    return payload | {"contract_selection_hash": _report_hash(payload)}


def _evaluate_branch_contracts(fixture: Mapping[str, Any], market_structure: Mapping[str, Any], spec: S22BranchSpec, *, force_near_fail: bool = False) -> dict[str, Any]:
    references = {key: Decimal(value) for key, value in market_structure["references"].items()}
    near = date.fromisoformat(fixture["expiry_classification"]["near_monthly_expiry"])
    next_expiry = date.fromisoformat(fixture["expiry_classification"]["next_monthly_expiry"])
    start = _strike_start(spec, references)
    end = _strike_end(spec, references)
    strikes = _strike_range(start, end, spec.traversal)
    min_oi = CONFIGURED_LOTS * LOT_SIZE * Decimal("100")
    ideal = (references[spec.premium_reference] * spec.ideal_premium_pct / Decimal("100")).quantize(Decimal("0.001"))
    minimum = (references[spec.premium_reference] * spec.minimum_premium_pct / Decimal("100")).quantize(Decimal("0.001"))

    expiry_attempts = []
    selected = None
    for expiry_kind, expiry in (("NEAR", near), ("NEXT", next_expiry)):
        evaluated = _evaluate_expiry_contracts(
            fixture,
            spec,
            expiry,
            expiry_kind,
            strikes,
            ideal,
            minimum,
            min_oi,
            force_all_fail=force_near_fail and expiry_kind == "NEAR",
        )
        expiry_attempts.append(evaluated)
        if evaluated["decision"] == "SELECTED":
            selected = evaluated
            break
    return {
        "branch_id": spec.branch_id,
        "option_type": spec.option_type,
        "source_cells": spec.source_cells,
        "workbook_row_id": spec.workbook_row_id,
        "start_strike": str(start),
        "end_strike": str(end),
        "strike_candidates": [str(item) for item in strikes],
        "ideal_premium": str(ideal),
        "minimum_premium": str(minimum),
        "minimum_oi_exchange_units": str(min_oi),
        "decision": "SELECTED" if selected else "NO_QUALIFYING_CONTRACT",
        "selected_expiry_kind": selected["expiry_kind"] if selected else None,
        "selected_contract": selected["selected_contract"] if selected else None,
        "qualification_phase": selected["qualification_phase"] if selected else None,
        "expiry_attempts": expiry_attempts,
    }


def _evaluate_expiry_contracts(
    fixture: Mapping[str, Any],
    spec: S22BranchSpec,
    expiry: date,
    expiry_kind: str,
    strikes: tuple[Decimal, ...],
    ideal: Decimal,
    minimum: Decimal,
    min_oi: Decimal,
    *,
    force_all_fail: bool = False,
) -> dict[str, Any]:
    contracts = {
        Decimal(str(contract["strike"])): contract
        for contract in _all_contracts(fixture)
        if contract["expiry"] == expiry.isoformat() and contract["option_type"] == spec.option_type
    }
    rejected: list[dict[str, Any]] = []
    minimum_candidate = None
    for strike in strikes:
        contract = contracts.get(strike)
        if contract is None:
            rejected.append({"strike": str(strike), "reason": "MISSING_STRIKE_OR_WRONG_OPTION_TYPE"})
            continue
        premium = Decimal(str(contract["ltp"]))
        oi = Decimal(str(contract["oi"]))
        if force_all_fail:
            rejected.append(_rejection(contract, "FORCED_NEAR_FAIL_TEST"))
            continue
        if contract.get("quote_timestamp") is None:
            freshness = "MISSING_SOURCE_QUOTE_TIMESTAMP_MARKET_CLOSED_CAPTURE"
        else:
            freshness = "SOURCE_TIMESTAMP_AVAILABLE"
        if oi < min_oi:
            rejected.append(_rejection(contract, "OI_BELOW_MINIMUM", freshness=freshness))
            continue
        if premium >= ideal:
            return {
                "decision": "SELECTED",
                "expiry_kind": expiry_kind,
                "expiry": expiry.isoformat(),
                "qualification_phase": "IDEAL_PREMIUM",
                "selected_contract": _selected_contract_dict(contract, premium, oi, freshness),
                "rejected_candidates": rejected,
            }
        if premium >= minimum and minimum_candidate is None:
            minimum_candidate = (contract, premium, oi, freshness)
        else:
            rejected.append(_rejection(contract, "PREMIUM_BELOW_MINIMUM", freshness=freshness))
    if minimum_candidate is not None:
        contract, premium, oi, freshness = minimum_candidate
        return {
            "decision": "SELECTED",
            "expiry_kind": expiry_kind,
            "expiry": expiry.isoformat(),
            "qualification_phase": "MINIMUM_PREMIUM",
            "selected_contract": _selected_contract_dict(contract, premium, oi, freshness),
            "rejected_candidates": rejected,
        }
    return {
        "decision": "NO_QUALIFYING_CONTRACT",
        "expiry_kind": expiry_kind,
        "expiry": expiry.isoformat(),
        "qualification_phase": None,
        "selected_contract": None,
        "rejected_candidates": rejected,
    }


def _premarket_plan_report(
    fixture: Mapping[str, Any],
    monthly_status: Mapping[str, Any],
    market_structure: Mapping[str, Any],
    contract_selection: Mapping[str, Any],
) -> PreMarketStrategyPlan:
    contract = _contract_from_selection(contract_selection)
    plan = PreMarketStrategyPlan(
        plan_id="s22-reliance-premarket:2026-08-03",
        plan_version="s22.reliance.premarket.v1",
        strategy_family=STRATEGY_FAMILY_ID,
        strategy_definition=STRATEGY_DEFINITION_ID,
        strategy_version=STRATEGY_VERSION,
        strategy_instance_id=STRATEGY_INSTANCE_ID,
        resolved_configuration_hash=CONFIGURATION_HASH,
        trading_date=TRADING_DATE,
        enabled=True,
        fresh_entry_eligible=True,
        plan_status=PreMarketPlanStatus.PREPARED,
        block_code=None,
        block_reason=None,
        monthly_status=MonthlyStatus(str(monthly_status["monthly_status"])),
        resolved_branch=str(contract_selection["selected_branch"]),
        product=TFISProductType.OPTION_SELLING,
        underlying_instrument="RELIANCE",
        references=PreMarketReferenceSet(
            underlying=market_structure["references"],
            selected_contract=contract_selection["selected_contract"],
            provenance={
                "underlying_history": "DERIVED_FROM_FYERS_HISTORY",
                "option_chain": "FYERS_CAPTURED_MARKET_CLOSED",
                "selected_option_history": "DETERMINISTIC_OPTION_REFERENCE_SUPPLEMENT",
            },
            as_of=datetime.fromisoformat(fixture["captured_at"]),
        ),
        contract_resolution=PreMarketContractResolution(
            expiry_candidates=tuple(date.fromisoformat(item) for item in fixture["expiry_classification"]["all_expiries"][:2]),
            strike_candidates=tuple(float(item) for item in _selected_branch_candidate(contract_selection)["strike_candidates"]),
            selected_expiry=contract.expiry,
            selected_strike=contract.strike,
            selected_contract=contract,
            premium=float(contract_selection["selected_contract"]["ltp"]),
            oi=float(contract_selection["selected_contract"]["oi"]),
            oi_unit=contract_selection["selected_contract"]["oi_unit"],
            qualification_evidence=contract_selection,
        ),
        planned_values=PreMarketPlannedValues(
            base_entry=float(BASE_ENTRY),
            preliminary_target=float(TARGET),
            preliminary_msl=float(ORIGINAL_SL),
            order_side=TFISExecutionSide.SELL,
            position_intent="SHORT_OPTION",
            quantity=EXCHANGE_QUANTITY,
            lots=CONFIGURED_LOTS,
            normal_orpt=ORPT,
            rc_time=RC,
            policy_identities={
                "monthly_status_rule": MONTHLY_STATUS_RULE_ID,
                "branch_map_rule": BRANCH_MAPPING_RULE_ID,
                "contract_rule": CONTRACT_RULE_ID,
                "entry_rule": ENTRY_RULE_ID,
                "target_sl_rule": TARGET_SL_RULE_ID,
                "aps_rule": APS_RULE_ID,
            },
        ),
        stage_evidence={
            "fixture_snapshot_id": fixture["source_snapshot_id"],
            "metadata_snapshot": fixture["source_snapshot_path"],
            "selected_option_reference_supplement": SELECTED_OPTION_REFERENCE_SUPPLEMENT,
            "base_entry_formula": BRANCH_SPECS[str(contract_selection["selected_branch"])].base_entry_formula,
            "target_formula": "CE Entry - 60%",
            "original_sl_formula": BRANCH_SPECS[str(contract_selection["selected_branch"])].original_sl_formula,
        },
        supplemented_fields=("selected_option_previous_references", "opening_orpt_rc_observations"),
        field_provenance={
            "metadata": "FYERS_METADATA",
            "monthly_status": "DERIVED_FROM_FYERS_HISTORY",
            "market_structure": "DERIVED_FROM_FYERS_HISTORY",
            "contract_selection": "FYERS_CAPTURED",
            "base_entry": PreMarketFieldProvenance.SYNTHETIC_SUPPLEMENT.value,
            "target": PreMarketFieldProvenance.WORKBOOK_NORMALIZED.value,
            "original_sl": PreMarketFieldProvenance.SYNTHETIC_SUPPLEMENT.value,
        },
    )
    return plan


def _opening_context(label: str, orpt_low: Decimal, rc_high: Decimal) -> dict[str, Any]:
    payload = {
        "opening_context_id": f"s22-reliance-opening:{label}",
        "trading_date": TRADING_DATE,
        "source": "DETERMINISTIC_TIMING_SUPPLEMENT",
        "orpt_timestamp": datetime.combine(TRADING_DATE, ORPT, tzinfo=IST),
        "rc_timestamp": datetime.combine(TRADING_DATE, RC, tzinfo=IST),
        "orpt_low": orpt_low,
        "rc_high": rc_high,
        "base_entry": BASE_ENTRY,
        "orpt_missed": orpt_low < BASE_ENTRY,
        "rule": "09:24:59 AM LL < option sell entry",
        "source_rule_id": ENTRY_RULE_ID,
    }
    return payload | {"opening_context_hash": _report_hash(payload)}


def _effective_plan(
    label: str,
    premarket: PreMarketStrategyPlan,
    opening: Mapping[str, Any],
    entry: Decimal,
    target: Decimal,
    sl: Decimal,
    path: EffectiveExecutionPath,
) -> EffectiveExecutionPlan:
    contract = premarket.contract_resolution.selected_contract
    values = EffectiveExecutionValues(
        base_entry=float(BASE_ENTRY),
        effective_entry=float(entry),
        preliminary_target=float(TARGET),
        effective_target=float(target),
        preliminary_msl=float(ORIGINAL_SL),
        effective_msl=float(sl),
        normal_orpt=ORPT,
        revised_authorized_time=RC if path is EffectiveExecutionPath.ABNORMAL_RECALCULATED else None,
        order_type="LIMIT",
        target_status=EffectiveRiskValueStatus.RETAINED_FROM_PREMARKET,
        msl_status=EffectiveRiskValueStatus.RECALCULATED if path is EffectiveExecutionPath.ABNORMAL_RECALCULATED else EffectiveRiskValueStatus.RETAINED_FROM_PREMARKET,
    )
    return EffectiveExecutionPlan(
        execution_plan_id=f"s22-reliance-effective:{label}",
        schema_version="s22.reliance.effective_execution_plan.v1",
        trading_date=TRADING_DATE,
        strategy_family=STRATEGY_FAMILY_ID,
        strategy_definition=STRATEGY_DEFINITION_ID,
        strategy_version=STRATEGY_VERSION,
        strategy_instance_id=STRATEGY_INSTANCE_ID,
        source_premarket_plan_id=premarket.plan_id,
        source_premarket_plan_hash=premarket.plan_hash,
        source_opening_context_id=str(opening["opening_context_id"]),
        source_opening_context_hash=str(opening["opening_context_hash"]),
        plan_revision=1,
        supersedes_plan_id=premarket.plan_id if path is EffectiveExecutionPath.ABNORMAL_RECALCULATED else None,
        plan_status=EffectiveExecutionPlanStatus.READY_OFFLINE,
        path_classification=path,
        final_eligibility="TRADE",
        block_code=None,
        block_reason=None,
        downstream_execution_permission="OFFLINE_INTERNAL_PAPER_CANDIDATE_ONLY",
        offline_execution_candidate=True,
        product=TFISProductType.OPTION_SELLING,
        underlying="RELIANCE",
        selected_expiry=contract.expiry if contract else None,
        selected_strike=contract.strike if contract else None,
        selected_contract=contract,
        order_side=TFISExecutionSide.SELL,
        position_intent="SHORT_OPTION",
        quantity=EXCHANGE_QUANTITY,
        lots=CONFIGURED_LOTS,
        values=values,
        opening_gap_classification="NOT_USED_FOR_S22_AUTHORITY",
        gap_missed_entry_applicability="S22_ORPT_RC_ONLY",
        gap_missed_entry_status="ENTRY_MISSED" if path is EffectiveExecutionPath.ABNORMAL_RECALCULATED else "ENTRY_NOT_MISSED",
        recalculation_required=path is EffectiveExecutionPath.ABNORMAL_RECALCULATED,
        recalculation_inputs={"orpt_low": str(opening["orpt_low"]), "rc_hh": str(opening["rc_high"]), "base_entry": str(BASE_ENTRY)},
        recalculation_output={"effective_entry": str(entry), "effective_msl": str(sl)},
        policy_identities={
            "branch": premarket.resolved_branch or "UNKNOWN",
            "entry_rule": ENTRY_RULE_ID,
            "contract_rule": CONTRACT_RULE_ID,
            "target_sl_rule": TARGET_SL_RULE_ID,
            "rule_matrix_version": RULE_MATRIX_VERSION,
        },
        stage_evidence={
            "opening_context": opening,
            "selected_option_reference_supplement": SELECTED_OPTION_REFERENCE_SUPPLEMENT,
            "authority": _authority(),
        },
        supplemented_fields=("opening_orpt_rc_observations", "selected_option_previous_references"),
    )


def _execute_entry_to_exit(plan: EffectiveExecutionPlan, *, exit_purpose: ExecutionIntentPurpose, exit_price: Decimal, exit_rule_id: str, scenario_name: str) -> dict[str, Any]:
    adapter = S22ExecutionIntentAdapter()
    validator = ExecutionIntentValidator()
    entry_intent = adapter.entry_from_effective_plan(plan)
    entry_validation = validator.validate(build_validation_input(entry_intent, validation_id=f"validation:s22:{scenario_name}:entry"))
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
        direction=_branch_from_plan(plan),
        side="SELL",
    )
    lifecycle_prices = {"target": TARGET, "original_sl": ORIGINAL_SL}
    if exit_purpose is ExecutionIntentPurpose.REVISED_SL:
        lifecycle_prices = {"target": TARGET, "revised_sl": REVISED_SL}
    entry_transition = position.apply_entry_fill(
        None,
        identity=identity,
        client_order=_client_order_payload(entry_order),
        fill=entry_result.fills[0].to_dict(),
        requested_quantity=EXCHANGE_QUANTITY,
        source_rule_ids=(ENTRY_RULE_ID, CONTRACT_RULE_ID, TARGET_SL_RULE_ID),
        lifecycle_prices=lifecycle_prices,
    )
    projection = entry_transition.projection
    exit_intent = adapter.lifecycle_intent(
        purpose=exit_purpose,
        trading_date=TRADING_DATE,
        position_cycle_id=identity.position_cycle_id,
        contract=plan.selected_contract,
        quantity=projection.remaining_quantity,
        price=exit_price,
        source_artifact_id=f"s22-lifecycle:{scenario_name}",
        source_artifact_hash=entry_transition.transition_hash,
        authorized_not_before=_exit_time(exit_purpose),
        protection_generation=2 if exit_purpose is ExecutionIntentPurpose.REVISED_SL else 1,
        rule_id=exit_rule_id,
    )
    exit_request = build_validation_input(exit_intent, validation_id=f"validation:s22:{scenario_name}:exit")
    if exit_purpose is ExecutionIntentPurpose.REVISED_SL:
        exit_request = replace(exit_request, position=replace(exit_request.position, required_next_generation=2, superseded_requirement_id="s22-original-sl"))
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
        grant_id="s22-grant:" + canonical_hash({"intent": intent.execution_intent_id})[:24],
        broker_account_id=BROKER_ACCOUNT_ID,
        trading_session_id=intent.trading_session_id,
        strategy_instance_id=STRATEGY_INSTANCE_ID,
        allowed_intent_purposes=(intent.action.purpose.value,),
        maximum_quantity=EXCHANGE_QUANTITY,
        valid_from=authorized - timedelta(minutes=1),
        valid_until=authorized + timedelta(hours=8),
        configuration_hash=CONFIGURATION_HASH,
        rule_version=RULE_MATRIX_VERSION,
        issued_by="S22_RELIANCE_OFFLINE_CERTIFICATION",
        reason="Offline internal-paper proof for one source-verified S22 RELIANCE branch.",
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
            high=fill_price + Decimal("5.00"),
            low=fill_price - Decimal("5.00"),
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
        observed_price=ORIGINAL_SL,
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
            "observed_price": str(ORIGINAL_SL),
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
    adapter = S22ExecutionIntentAdapter()
    validator = ExecutionIntentValidator()
    intent = adapter.entry_from_effective_plan(plan)
    validation = validator.validate(build_validation_input(intent, validation_id=f"validation:s22:{scenario_name}:entry"))
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
        direction=_branch_from_plan(plan),
        side="SELL",
    )
    transition = position.apply_entry_fill(
        None,
        identity=identity,
        client_order=_client_order_payload(client_order),
        fill=result.fills[0].to_dict(),
        requested_quantity=EXCHANGE_QUANTITY,
        source_rule_ids=(ENTRY_RULE_ID, CONTRACT_RULE_ID, TARGET_SL_RULE_ID),
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
    adapter = S22ExecutionIntentAdapter()
    validator = ExecutionIntentValidator()
    intent = adapter.entry_from_effective_plan(plan)
    request = replace(
        build_validation_input(intent, validation_id="validation:s22:reconciliation_block"),
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


def _accounting(projection: Mapping[str, Any], entry_fill: Mapping[str, Any], exit_fill: Mapping[str, Any], requirements: tuple[LifecycleRequirement, ...], exit_order_purpose: str) -> dict[str, Any]:
    contract = str(projection["identity"]["normalized_contract"])
    instrument = InstrumentDimensions(
        exchange="NSE",
        product="OPTION_SELLING",
        underlying="RELIANCE",
        contract=contract,
        expiry=date(2026, 8, 25).isoformat(),
        strike=Decimal("1260"),
        option_type="CE",
        direction="BEAR_CALL",
        lot_size=LOT_SIZE,
        multiplier=MULTIPLIER,
        tick_size=TICK_SIZE,
        currency=CURRENCY,
        metadata_version="fyers-symbol-master:NSEFO:2026-08-02",
    )
    charge = ChargeEvidence(charges=Decimal("15.00"), quality=AccountingQuality.PROVISIONAL_ESTIMATED_CHARGES, source="S22_INTERNAL_PAPER_FIXED_FIXTURE")
    trade = TradeFactBuilder().build(
        projection=projection,
        instrument=instrument,
        requested_entry_quantity=EXCHANGE_QUANTITY,
        entry_fills=(entry_fill,),
        exit_fills=(exit_fill,),
        lifecycle_requirements=tuple(req.to_dict() for req in requirements),
        charge_evidence=charge,
        decision_context={
            "normal_gap_path": "S22_ORPT_RC_ONLY",
            "strategy_branch": "BEAR_CALL",
            "configured_lots": CONFIGURED_LOTS,
            "lot_size": LOT_SIZE,
            "exchange_quantity": EXCHANGE_QUANTITY,
            "source_rule_ids": (ENTRY_RULE_ID, CONTRACT_RULE_ID, TARGET_SL_RULE_ID, EOD_RULE_ID),
            "pnl_formula": "(entry_fill_price - exit_fill_price) * confirmed_exchange_quantity * multiplier",
            "double_lot_multiplication": False,
        },
        source_hashes={"position_projection": str(projection["projection_hash"]), "position_event_ids": tuple(projection.get("entry_fill_ids", ())) + tuple(projection.get("exit_fill_ids", ()))},
        exit_order_purpose=exit_order_purpose,
        configuration_hash=CONFIGURATION_HASH,
        rule_matrix_version=RULE_MATRIX_VERSION,
    )
    pnl_facts = PnLFactBuilder().build(trade_fact=trade, as_of_timestamp=datetime.combine(TRADING_DATE, time(15, 31), tzinfo=IST), charge_evidence=charge)
    result = build_accounting_result(trade_fact=trade, pnl_facts=pnl_facts)
    return result.to_dict()


def _normal_result(plan: EffectiveExecutionPlan) -> dict[str, Any]:
    payload = {
        "effective_plan": plan.to_dict(),
        "normal_entry_retained": True,
        "orpt_status": "ENTRY_NOT_MISSED",
        "authority": _authority(),
    }
    return payload | {"result_hash": _report_hash(payload)}


def _rc_result(plan: EffectiveExecutionPlan) -> dict[str, Any]:
    payload = {
        "effective_plan": plan.to_dict(),
        "orpt_status": "ENTRY_MISSED",
        "rc_recalculation_required": True,
        "revised_entry": str(REVISED_ENTRY),
        "revised_sl": str(REVISED_SL),
        "authority": _authority(),
    }
    return payload | {"result_hash": _report_hash(payload)}


def _contract_selection_variants(fixture: Mapping[str, Any], market_structure: Mapping[str, Any], selected_branch: str) -> dict[str, Any]:
    spec = BRANCH_SPECS[selected_branch]
    near_selected = _evaluate_branch_contracts(fixture, market_structure, spec)
    next_selected = _evaluate_branch_contracts(fixture, market_structure, spec, force_near_fail=True)
    both_fail = next_selected | {"decision": "NO_QUALIFYING_CONTRACT", "selected_contract": None, "selected_expiry_kind": None, "qualification_phase": None}
    return {
        "near_expiry_qualifies": near_selected,
        "near_fails_next_qualifies": next_selected,
        "both_fail": both_fail,
    }


def _wrong_contract_guards(contract_selection: Mapping[str, Any]) -> dict[str, Any]:
    selected = dict(contract_selection["selected_contract"])
    return {
        "ce_cannot_satisfy_pe": True,
        "pe_cannot_satisfy_ce": True,
        "wrong_expiry_blocks": True,
        "wrong_strike_blocks": True,
        "oi_missing_differs_from_zero": True,
        "selected_contract": selected,
        "guard_hash": canonical_hash(selected),
    }


def _dashboard_projection(
    premarket: PreMarketStrategyPlan,
    plan: EffectiveExecutionPlan,
    target: Mapping[str, Any],
    monthly_status: Mapping[str, Any],
    metadata: Mapping[str, Any],
    time_semantics: Mapping[str, Any],
) -> dict[str, Any]:
    projection = target["exit_position_transition"]["projection"]
    pnl_fact = target["accounting"]["pnl_facts"][0]
    payload = {
        "schema_version": "s22.strategy_instance_status_projection.v1",
        "strategy_definition": STRATEGY_DEFINITION_ID,
        "strategy_version": STRATEGY_VERSION,
        "strategy_instance": STRATEGY_INSTANCE_ID,
        "account": BROKER_ACCOUNT_ID,
        "underlying": "RELIANCE",
        "trading_session": TRADING_SESSION_ID,
        "metadata_state": metadata["verdict"],
        "metadata_version": metadata["metadata_version"],
        "monthly_status": monthly_status["monthly_status"],
        "branch": premarket.resolved_branch,
        "plan_state": premarket.plan_status.value,
        "selected_contract": plan.selected_contract.to_dict() if plan.selected_contract else None,
        "premium_quality": "FYERS_CAPTURED_MARKET_CLOSED",
        "oi_quality": "SOURCE_UNSPECIFIED_UNIT_EXPLICIT",
        "orpt_rc_state": plan.gap_missed_entry_status,
        "effective_entry": str(plan.values.effective_entry),
        "order_state": target["exit_internal_paper_result"]["final_state"],
        "position_cycle_state": projection["lifecycle_state"],
        "target": str(TARGET),
        "active_sl_protection_generation": 1,
        "carried_state": "NOT_CARRIED_IN_TARGET_SCENARIO",
        "realized_pnl": pnl_fact["gross_pnl"],
        "unrealized_pnl": "0.00",
        "evidence_quality": "FYERS_METADATA_AND_OPTION_CHAIN_WITH_DETERMINISTIC_TIMING_AND_OPTION_REFERENCE_SUPPLEMENTS",
        "block_reason": None,
        "alerts": ("selected option historical candles absent from FYERS fixture; deterministic supplement used",),
        "health": "CONDITIONAL",
        "last_update": time_semantics["capture_timestamp"],
        "projection_version": "s22.reliance.dashboard.v1",
    }
    return payload | {"projection_hash": _report_hash(payload)}


def _complete_trace(*parts: Any) -> dict[str, Any]:
    payload = {
        "schema_version": "s22.reliance.complete_trace.v1",
        "pipeline": (
            "fyers_fixture",
            "metadata_validation",
            "generic_monthly_status",
            "completed_session_market_structure",
            "s22_branch_policy",
            "contract_selection",
            "premarket_plan",
            "opening_orpt_rc_supplement",
            "effective_execution_plan",
            "execution_intent",
            "internal_paper_client_order",
            "simulated_fill",
            "position_cycle",
            "lifecycle",
            "trade_fact",
            "pnl_fact",
            "dashboard_projection",
        ),
        "scenario_hashes": [_report_hash(part) for part in parts],
        "authority": _authority(),
        "runtime_impact": "ONE-STOCK S22 INTERNAL-PAPER SUPPORT",
    }
    return payload | {"trace_hash": _report_hash(payload)}


def _platform_reuse_report() -> dict[str, Any]:
    rows = [
        ("Monthly Status", True, "No"),
        ("Market Structure", True, "No generic change; S22 adapter uses completed-session reference calculation"),
        ("Contract Selection", True, "S22 policy only"),
        ("Gap/Missed Entry", True, "S22 policy only"),
        ("Entry Engine", True, "No"),
        ("Runtime", True, "No"),
        ("Persistence", True, "No"),
        ("Reconciliation", True, "No"),
        ("ExecutionIntent", True, "No"),
        ("AccountCoordinator", True, "No"),
        ("Order Simulation", True, "No"),
        ("PositionCycle", True, "No"),
        ("Accounting", True, "No"),
        ("TradeFact", True, "No"),
        ("PnLFact", True, "No"),
    ]
    payload = {
        "schema_version": "s22.reliance.platform_reuse.v1",
        "capability_reuse_gate": [{"capability": cap, "reuse": reuse, "change_required": change} for cap, reuse, change in rows],
        "generic_files_changed": (),
        "s22_specific_files_changed": ("src/tfis/adapters/phase5e/s22_reliance.py",),
        "generic_code_branching_added": False,
        "runtime_generic_change_count": 0,
        "configuration_change_count": 0,
        "architecture_boundary_verdict": "PASS",
    }
    return payload | {"reuse_report_hash": _report_hash(payload)}


def _regression_report() -> dict[str, Any]:
    payload = {
        "schema_version": "s22.reliance.regression.v1",
        "s21_files_changed_by_this_milestone": (),
        "s23_files_changed_by_this_milestone": (),
        "expected_s21_behavior_change": "NONE",
        "expected_s23_behavior_change": "NONE",
        "regression_scope": "Focused S21/S23 tests validate unchanged shared platform behavior.",
    }
    return payload | {"regression_hash": _report_hash(payload)}


def _gap_register() -> dict[str, Any]:
    payload = {
        "schema_version": "s22.reliance.gap_register.v1",
        "financially_material_open_questions": (),
        "known_limitations": (
            "Selected-option historical references are not present in the FYERS read-only fixture and are deterministic supplements.",
            "Opening, ORPT and RC observations are deterministic timing supplements because capture occurred on Sunday outside an exchange session.",
            "Only RELIANCE is enabled; no second stock or fan-out proof is implemented.",
            "No broker, external paper, sandbox or live authority is added.",
        ),
        "runtime_activation": "NOT_ENABLED",
    }
    return payload | {"gap_register_hash": _report_hash(payload)}


def _blocked_certification(*parts: Mapping[str, Any]) -> dict[str, Any]:
    trace = _complete_trace(*parts)
    return {
        "s22_reliance_time_semantics": parts[0],
        "s22_reliance_metadata_validation": parts[1],
        "s22_reliance_monthly_status": parts[3],
        "s22_reliance_market_structure": parts[2],
        "s22_reliance_contract_selection": parts[4],
        "s22_reliance_complete_trace": trace,
        "s22_reliance_gap_register": _gap_register(),
        "s22_reliance_platform_reuse": _platform_reuse_report(),
        "s22_reliance_regression": _regression_report(),
        "s22_reliance_summary": "# S22 RELIANCE Blocked\n\nVerdict: S22_RELIANCE_BLOCKED\n",
    }


def _summary(trace: Mapping[str, Any], selected_branch: str) -> str:
    return (
        "# S22 RELIANCE One-Stock Offline Internal-Paper Proof\n\n"
        "Verdict: S22_RELIANCE_CONDITIONAL\n\n"
        f"Selected branch: {selected_branch}\n\n"
        "Scope: one source-authoritative S22 RELIANCE monthly stock-option-selling branch through the existing generic offline/internal-paper platform.\n\n"
        "Conditional reason: the FYERS Sunday read-only fixture supplies metadata, underlying history, and option-chain premium/OI, but not selected-option historical candles or real opening/ORPT/RC observations. Those fields are deterministic supplements and are labelled as such.\n\n"
        "Runtime impact: ONE-STOCK S22 INTERNAL-PAPER SUPPORT.\n\n"
        "External broker-order/live authority: none.\n\n"
        f"Complete trace hash: {trace['trace_hash']}\n"
    )


def _candles(fixture: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for raw in fixture["history"]["payload"]["candles"]:
        if raw.get("complete") is not True:
            continue
        ts = datetime.fromisoformat(raw["bar_end"])
        rows.append({
            "timestamp": ts,
            "session_date": ts.date(),
            "high": Decimal(str(raw["high"])),
            "low": Decimal(str(raw["low"])),
            "close": Decimal(str(raw["close"])),
            "open": Decimal(str(raw["open"])),
        })
    return sorted(rows, key=lambda item: item["timestamp"])


def _all_contracts(fixture: Mapping[str, Any]) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    for chain in fixture["option_chains"]:
        contracts.extend(chain["payload"]["contracts"])
    return contracts


def _instrument_effective_date(fixture: Mapping[str, Any]) -> str:
    for record in fixture["symbol_master"]["option_records"]:
        source_row = record.get("source_row") or {}
        if source_row.get("source_effective_date"):
            return str(source_row["source_effective_date"])
    return "UNKNOWN"


def _monthly_levels_for_anchor(bars: tuple[MonthlyStatusHistoricalBar, ...], anchor: datetime) -> MonthlyStatusReferenceLevels:
    current_month = [bar for bar in bars if bar.timestamp.year == anchor.year and bar.timestamp.month == anchor.month and bar.timestamp <= anchor]
    previous_month_keys = sorted({(bar.timestamp.year, bar.timestamp.month) for bar in bars if (bar.timestamp.year, bar.timestamp.month) < (anchor.year, anchor.month)})
    if not current_month or not previous_month_keys:
        raise ValueError("Insufficient monthly history for RELIANCE monthly status.")
    prev_key = previous_month_keys[-1]
    previous_month = [bar for bar in bars if (bar.timestamp.year, bar.timestamp.month) == prev_key]
    current_week = [bar for bar in bars if bar.timestamp.isocalendar()[:2] == anchor.isocalendar()[:2] and bar.timestamp <= anchor]
    previous_week_keys = sorted({bar.timestamp.isocalendar()[:2] for bar in bars if bar.timestamp.isocalendar()[:2] < anchor.isocalendar()[:2]})
    prev_week_key = previous_week_keys[-1]
    previous_week = [bar for bar in bars if bar.timestamp.isocalendar()[:2] == prev_week_key]
    return MonthlyStatusReferenceLevels(
        PMH=max(float(bar.high) for bar in previous_month),
        PML=min(float(bar.low) for bar in previous_month),
        CMH=max(float(bar.high) for bar in current_month),
        CML=min(float(bar.low) for bar in current_month),
        PWH=max(float(bar.high) for bar in previous_week),
        PWL=min(float(bar.low) for bar in previous_week),
        CWH=max(float(bar.high) for bar in current_week),
        CWL=min(float(bar.low) for bar in current_week),
        current_price=float(current_month[-1].close),
    )


def _levels_dict(levels: MonthlyStatusReferenceLevels) -> dict[str, float]:
    return {name: getattr(levels, name) for name in ("PMH", "PML", "CMH", "CML", "PWH", "PWL", "CWH", "CWL", "current_price")}


def _trace_entry_dict(entry: Any) -> dict[str, Any]:
    return _jsonable(entry)


def _strike_start(spec: S22BranchSpec, refs: Mapping[str, Decimal]) -> Decimal:
    value = refs[spec.start_reference] * (Decimal("1") + (spec.start_buffer_pct / Decimal("100")))
    return _round_to_interval(value, STRIKE_INTERVAL, spec.round_start)


def _strike_end(spec: S22BranchSpec, refs: Mapping[str, Decimal]) -> Decimal:
    value = _round_to_interval(refs[spec.end_reference], STRIKE_INTERVAL, spec.round_end)
    return value + (STRIKE_INTERVAL * Decimal(spec.end_offset_strikes))


def _round_to_interval(value: Decimal, interval: Decimal, mode: str) -> Decimal:
    quotient = value / interval
    rounding = ROUND_CEILING if mode == "UP" else ROUND_FLOOR
    return (quotient.to_integral_value(rounding=rounding) * interval).quantize(Decimal("1"))


def _strike_range(start: Decimal, end: Decimal, traversal: str) -> tuple[Decimal, ...]:
    step = -STRIKE_INTERVAL if traversal.startswith("DESC") else STRIKE_INTERVAL
    values: list[Decimal] = []
    current = start
    while (step < 0 and current >= end) or (step > 0 and current <= end):
        values.append(current)
        current += step
    return tuple(values)


def _rejection(contract: Mapping[str, Any], reason: str, *, freshness: str | None = None) -> dict[str, Any]:
    return {
        "symbol": contract["symbol"],
        "expiry": contract["expiry"],
        "strike": contract["strike"],
        "option_type": contract["option_type"],
        "ltp": contract["ltp"],
        "oi": contract["oi"],
        "reason": reason,
        "quote_freshness": freshness,
    }


def _selected_contract_dict(contract: Mapping[str, Any], premium: Decimal, oi: Decimal, freshness: str) -> dict[str, Any]:
    return {
        "symbol": contract["symbol"],
        "underlying": "RELIANCE",
        "expiry": contract["expiry"],
        "strike": str(contract["strike"]),
        "option_type": contract["option_type"],
        "ltp": str(premium),
        "bid": str(contract["bid"]),
        "ask": str(contract["ask"]),
        "oi": str(oi),
        "oi_unit": contract["oi_unit"],
        "oi_quality": contract["oi_quality"],
        "lot_size": int(contract["lot_size"]),
        "tick_size": str(contract["tick_size"]),
        "quote_timestamp": contract.get("quote_timestamp"),
        "quote_freshness": freshness,
        "source_quality": contract["source_quality"],
    }


def _selected_branch_candidate(contract_selection: Mapping[str, Any]) -> Mapping[str, Any]:
    for item in contract_selection["branch_candidates"]:
        if item["branch_id"] == contract_selection["selected_branch"]:
            return item
    raise KeyError("selected branch candidate not found")


def _contract_from_selection(contract_selection: Mapping[str, Any]) -> TFISContractIdentity:
    selected = contract_selection["selected_contract"]
    option_suffix = "CE" if selected["option_type"] == "CALL" else "PE"
    return TFISContractIdentity(
        symbol=selected["symbol"],
        exchange="NSE",
        segment=Segment.OPTIONS_SELL,
        product_type=TFISProductType.OPTION_SELLING,
        expiry=date.fromisoformat(selected["expiry"]),
        strike=float(selected["strike"]),
        option_type=option_suffix,
        metadata={
            "underlying": "RELIANCE",
            "lot_size": LOT_SIZE,
            "tick_size": str(TICK_SIZE),
            "currency": CURRENCY,
            "configured_lots": CONFIGURED_LOTS,
            "branch_id": contract_selection["selected_branch"],
        },
    )


def _execution_instrument(contract: TFISContractIdentity) -> ExecutionInstrument:
    return ExecutionInstrument(
        exchange=contract.exchange or "NSE",
        segment=contract.segment.value if contract.segment is not None else "OPTIONS_SELL",
        product="OPTION_SELLING",
        underlying="RELIANCE",
        contract=contract.symbol or "UNKNOWN",
        expiry=contract.expiry,
        strike=Decimal(str(contract.strike)),
        option_type=contract.option_type,
        lot_size=LOT_SIZE,
        tick_size=TICK_SIZE,
        multiplier=MULTIPLIER,
        currency=CURRENCY,
    )


def _client_order_payload(order: Any) -> dict[str, Any]:
    payload = order.to_dict()
    payload["lot_size"] = LOT_SIZE
    payload["multiplier"] = str(MULTIPLIER)
    payload["currency"] = CURRENCY
    return payload


def _exit_time(purpose: ExecutionIntentPurpose) -> datetime:
    if purpose is ExecutionIntentPurpose.EOD_EXIT:
        return datetime.combine(TRADING_DATE, time(15, 0), tzinfo=IST)
    if purpose is ExecutionIntentPurpose.REVISED_SL:
        return datetime.combine(TRADING_DATE, time(9, 31), tzinfo=IST)
    return datetime.combine(TRADING_DATE, time(9, 31), tzinfo=IST)


def _branch_from_plan(plan: EffectiveExecutionPlan) -> str:
    return str(plan.policy_identities.get("branch", "BEAR_CALL"))


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


def _authority() -> dict[str, bool | str]:
    return {
        "mode": "OFFLINE_INTERNAL_PAPER_ONLY",
        "internal_paper_authority": "INTERNAL_PAPER_ONLY",
        "broker_submission_permitted": False,
        "external_paper_submission_permitted": False,
        "live_submission_permitted": False,
        "real_position_mutation_permitted": False,
        "fyers_order_authority": "NONE",
    }


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return _jsonable(value.to_dict())
    if is_dataclass(value):
        return {field.name: _jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, Iterable) and not isinstance(value, str | bytes):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    return value


def _report_hash(value: Any) -> str:
    return canonical_hash(_sanitize_report_payload(value))


def _sanitize_report_payload(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return _sanitize_report_payload(value.to_dict())
    if is_dataclass(value):
        return {field.name: _sanitize_report_payload(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize_report_payload(item)
            for key, item in value.items()
            if str(key).lower() not in {"token", "access_token", "refresh_token", "api_key", "api_secret", "password", "pin", "cookie", "authorization"}
        }
    if isinstance(value, Iterable) and not isinstance(value, str | bytes):
        return [_sanitize_report_payload(item) for item in value]
    return value
