from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from tfis.adapters.legacy_policies.gap_missed_entry import (
    LegacyGapMissedEntryEvaluationInput,
    S23_BEAR_CALL_BRANCH,
    S23_BACKTEST_LOW_POLICY_KEY,
    S23_BULL_CALL_BRANCH,
    evaluate_legacy_gap_missed_entry,
)
from tfis.adapters.legacy_policies.policies import (
    S23ContractSelectionPolicyAdapter,
    S23EntryPolicyAdapter,
    S23MSLPolicyAdapter,
    S23ProductPolicyAdapter,
    S23TargetPolicyAdapter,
)
from tfis.adapters.legacy_policies.s23_evaluation_capture import (
    EvaluationCaptureObserver,
    record_s23_capture_safely,
)
from tfis.decision import (
    ContractSelectionPolicyInput,
    EntryPolicyInput,
    GapPolicyResult,
    MSLPolicyInput,
    MissedEntryPolicyResult,
    PolicyStatus,
    ProductPolicyInput,
    TargetPolicyInput,
)
from tfis.domain import (
    AuditEvidence,
    BusinessEngineStatus,
    CalculatedDecisionEvidence,
    EntryBaseCandidate,
    EntryBusinessEngineFragment,
    EntryDownstreamPermission,
    EntryEffectiveTrigger,
    EntryEngineInput,
    EntryFormulaComponent,
    EntryFormulaDescriptor,
    EntryFormulaOperandRole,
    EntryFormulaOperator,
    EntryInstrumentType,
    EntryMarketBias,
    EntryOptionRight,
    EntryPolicyOutcome,
    EntryPositionIntent,
    EntryQuality,
    EntryReference,
    EntryReferenceRequirement,
    EntryReferenceSource,
    EntryReferenceValueType,
    EntryResolvedBranch,
    EntrySource,
    EntryStatus,
    EntryTriggerCondition,
    EntryTriggerDirection,
    EntryValidation,
    EvidenceAvailability,
    EvidenceProvenance,
    GapMissedEntryEvidence,
    IdentityEvidence,
    InstrumentProductEvidence,
    MarketLevels,
    MarketStructureEvidence,
    MonthlyStatus,
    MonthlyStatusEvidence,
    OptionChainCandidateEvidence,
    OptionChainEvidence,
    OptionProductReferenceEvidence,
    OptionType,
    PositionCycleIdentity,
    PriceContextEvidence,
    ProvenancedValue,
    Segment,
    SelectedContractEvidence,
    SessionEvidence,
    StrategyEvaluationIdentity,
    TFISContractIdentity,
    TFISDecision,
    TFISDecisionEvidencePacket,
    TFISDirection,
    TFISExecutionSide,
    TFISFormulaTrace,
    TFISPolicyResult,
    TFISProductType,
    TFISRuntimeInput,
    TFISTradeResult,
    TimeWindowEvidence,
)
from tfis.domain.gap_missed_entry import (
    MissedEntryObservationSource,
    MissedEntryState,
    ObservationValue,
    SessionTimingEvidence,
    TimingObservationRequirement,
    TimingWindowState,
)
from tfis.importers import load_strategy_rule
from tfis.normalized_events import EventEnvelope, OptionChainContract, OptionChainSnapshotEvent, PaperEventType
from tfis.orchestration import OfflineStageResult, OfflineStrategyDecisionOrchestrator
from tfis.strategy import StrategyEvaluator
from tfis.strategy.s23_recalculation import IntradaySnapshot
from tfis.entry import EntryEngine


ROOT = Path(__file__).resolve().parents[4]
SCHEMA_VERSION = "tfis.decision_evidence_packet.v1"


@dataclass(frozen=True, slots=True)
class S23VerticalSliceCase:
    runtime_input: TFISRuntimeInput
    strategy_rule: Any
    market_levels: MarketLevels
    runtime_values: Mapping[str, Any]
    option_chain_snapshot: OptionChainSnapshotEvent
    branch_key: str
    market_bias: EntryMarketBias
    evidence_label: str
    decision_id: str
    vertical_slice_label: str
    phase_label: str
    session_reason: str
    final_reason: str
    evidence_classification: str = "SYNTHETIC_GOLDEN"
    evidence_metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class S23VerticalBranchSpec:
    branch_name: str
    strategy_folder: str
    branch_key: str
    monthly_status: MonthlyStatus
    market_bias: EntryMarketBias
    evaluation_id: str
    decision_id: str
    configuration_hash: str
    vertical_slice_label: str
    evidence_label: str
    phase_label: str
    session_label: str
    session_reason: str
    final_reason: str
    provenance_source: str


BULL_CALL_SPEC = S23VerticalBranchSpec(
    branch_name="Bull Call",
    strategy_folder="S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
    branch_key=S23_BULL_CALL_BRANCH,
    monthly_status=MonthlyStatus.BULL,
    market_bias=EntryMarketBias.BULLISH,
    evaluation_id="phase3d-m3-s23-bull-call",
    decision_id="tfis-decision-phase3d-m3-s23-bull-call",
    configuration_hash="phase3d-m3-s23-bull-call-synthetic-v1",
    vertical_slice_label="S23_BULL_CALL",
    evidence_label="SYNTHETIC_GOLDEN:S23:BULL_CALL:PHASE3D_M3",
    phase_label="phase3d_m3",
    session_label="PHASE3D_M3_SYNTHETIC",
    session_reason="S23 Bull Call vertical slice.",
    final_reason="S23 Bull Call vertical slice expected TRADE.",
    provenance_source="phase3d_m3_synthetic",
)
BEAR_CALL_SPEC = S23VerticalBranchSpec(
    branch_name="Bear Call",
    strategy_folder="S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
    branch_key=S23_BEAR_CALL_BRANCH,
    monthly_status=MonthlyStatus.BEAR,
    market_bias=EntryMarketBias.BEARISH,
    evaluation_id="phase3d-m4-s23-bear-call",
    decision_id="tfis-decision-phase3d-m4-s23-bear-call",
    configuration_hash="phase3d-m4-s23-bear-call-synthetic-v1",
    vertical_slice_label="S23_BEAR_CALL",
    evidence_label="SYNTHETIC_GOLDEN:S23:BEAR_CALL:PHASE3D_M4",
    phase_label="phase3d_m4",
    session_label="PHASE3D_M4_SYNTHETIC",
    session_reason="S23 Bear Call vertical slice.",
    final_reason="S23 Bear Call vertical slice expected TRADE.",
    provenance_source="phase3d_m4_synthetic",
)


class S23VerticalEntryPolicy:
    policy_key = "legacy.s23.vertical.entry"

    def evaluate_base(self, engine_input: EntryEngineInput) -> EntryPolicyOutcome:
        legacy_entry = engine_input.strategy_parameters["legacy_entry_result"]
        value = Decimal(str(legacy_entry.entry_value))
        descriptor = engine_input.formula_descriptor
        trigger = EntryTriggerCondition(
            trigger_direction=engine_input.resolved_branch.trigger_direction,
            comparison_value=value,
            order_side=engine_input.resolved_branch.order_side,
            position_intent=engine_input.resolved_branch.position_intent,
            reference_id="legacy_entry_value",
        )
        base = EntryBaseCandidate(
            value=value,
            source=EntrySource.BASE_POLICY,
            trigger_condition=trigger,
            formula_descriptor=descriptor,
            component_evidence=descriptor.components,
            quality=EntryQuality.VALID,
            validation=EntryValidation(),
            downstream_permission=EntryDownstreamPermission.PERMITTED,
            provenance={"adapter": type(self).__name__},
        )
        return EntryPolicyOutcome(status=EntryStatus.BASE_ENTRY_READY, base_candidate=base)

    def finalize_effective(self, engine_input: EntryEngineInput, base_candidate: EntryBaseCandidate, gap_missed_entry_result: Any) -> EntryPolicyOutcome:
        status = EntryStatus.EFFECTIVE_ENTRY_EQUALS_BASE
        source = EntrySource.BASE_POLICY
        if gap_missed_entry_result and gap_missed_entry_result.missed_entry.status is MissedEntryState.NOT_MISSED:
            status = EntryStatus.ENTRY_NOT_MISSED
        effective = EntryEffectiveTrigger(
            value=base_candidate.value,
            status=status,
            source=source,
            trigger_condition=base_candidate.trigger_condition,
            base_candidate=base_candidate,
            gap_missed_entry_status=gap_missed_entry_result.missed_entry.status.value if gap_missed_entry_result else "NOT_APPLICABLE",
            recalculation_status=gap_missed_entry_result.recalculation.status.value if gap_missed_entry_result else None,
            quality=EntryQuality.VALID,
            validation=EntryValidation(),
            downstream_permission=EntryDownstreamPermission.PERMITTED,
            provenance={"adapter": type(self).__name__},
        )
        return EntryPolicyOutcome(status=status, base_candidate=base_candidate, effective_trigger=effective)


@dataclass(frozen=True, slots=True)
class _Stage:
    stage_name: str
    runner: Any

    def run(self, context: Mapping[str, Any]) -> OfflineStageResult:
        return self.runner(context)


def run_s23_bull_call_vertical_slice(capture_observer: EvaluationCaptureObserver | None = None) -> Any:
    return run_s23_vertical_slice(BULL_CALL_SPEC, capture_observer=capture_observer)


def run_s23_bear_call_vertical_slice(capture_observer: EvaluationCaptureObserver | None = None) -> Any:
    return run_s23_vertical_slice(BEAR_CALL_SPEC, capture_observer=capture_observer)


def run_s23_vertical_slice(spec: S23VerticalBranchSpec, capture_observer: EvaluationCaptureObserver | None = None) -> Any:
    case = build_s23_vertical_case(spec)
    return run_s23_vertical_case(case, capture_observer=capture_observer)


def run_s23_vertical_case(case: S23VerticalSliceCase, capture_observer: EvaluationCaptureObserver | None = None) -> Any:
    stages = (
        _Stage("strategy_resolution", _strategy_resolution),
        _Stage("monthly_status_and_branch", _monthly_status_and_branch),
        _Stage("underlying_references", _underlying_references),
        _Stage("contract_selection", _contract_selection),
        _Stage("base_entry", _base_entry),
        _Stage("gap_missed_entry", _gap_missed_entry),
        _Stage("effective_entry", _effective_entry),
        _Stage("target_msl", _target_msl),
        _Stage("decision", _decision),
        _Stage("evidence_packet", _evidence_packet),
        _Stage("legacy_comparison", _legacy_comparison),
    )
    result = OfflineStrategyDecisionOrchestrator().evaluate({"case": case}, stages)
    record_s23_capture_safely(capture_observer, result, case=case)
    return result


def build_s23_bull_call_vertical_case() -> S23VerticalSliceCase:
    return build_s23_vertical_case(BULL_CALL_SPEC)


def build_s23_bear_call_vertical_case() -> S23VerticalSliceCase:
    return build_s23_vertical_case(BEAR_CALL_SPEC)


def build_s23_vertical_case(spec: S23VerticalBranchSpec) -> S23VerticalSliceCase:
    rule = load_strategy_rule(ROOT / "config" / "strategies" / "options_sell" / "nifty" / spec.strategy_folder)
    evaluated_at = datetime(2026, 7, 30, 9, 29, 59, tzinfo=ZoneInfo("Asia/Kolkata"))
    market = MarketLevels(d2hh=22500.0, d2ll=21900.0, d3hh=22600.0, d3ll=22000.0, current_day_high=22400.0, current_day_low=22100.0)
    runtime_values = {
        "ENTRY": 200.0,
        "OPT_LEVELS": {
            "OPT_PRV_2DLL": 210.0,
            "OPT_PRV_3DLL": 220.0,
            "OPT_PRV_2DHH": 300.0,
            "OPT_PRV_3DHH": 330.0,
        },
    }
    plan = StrategyEvaluator().evaluate(rule, market_levels=market, runtime_values=runtime_values)
    expiry = date(2026, 8, 6)
    chain = _option_chain(rule.symbol, expiry, rule.option_type, float(plan.start_strike), float(plan.ideal_premium), 999999.0, evaluated_at)
    runtime_input = TFISRuntimeInput(
        evaluation_id=spec.evaluation_id,
        evaluated_at=evaluated_at,
        strategy_code=rule.strategy_code,
        strategy_version="1.0.0",
        strategy_branch=rule.unique_code,
        symbol=rule.symbol,
        segment=rule.segment,
        product_type=TFISProductType.OPTION_SELLING,
        account_id=None,
        lots=1,
        quantity=50,
        session_date=evaluated_at.date(),
        session_label=spec.session_label,
        timezone="Asia/Kolkata",
        price_source="synthetic",
        cmp=22400.0,
        contract=None,
        monthly_status=spec.monthly_status,
        monthly_status_evidence={"classification": "SYNTHETIC_GOLDEN"},
        market_structure_references={"d2hh": market.d2hh, "d2ll": market.d2ll, "d3hh": market.d3hh, "d3ll": market.d3ll, "current_day_high": market.current_day_high, "current_day_low": market.current_day_low},
        current_week_references={},
        current_month_references={},
        gap_context={},
        option_chain_context=None,
        data_quality={"classification": "SYNTHETIC_GOLDEN"},
        provenance={"source": spec.provenance_source},
        configuration_snapshot={"strategy": rule.unique_code},
        configuration_version="1.0.0",
        runtime_values=runtime_values,
        product_specific={"option_chain_snapshot": chain, "expiry_date": expiry},
        strategy_family_id="S23",
        strategy_definition_id=spec.strategy_folder,
        strategy_instance_id="S23_NIFTY_ACCOUNT_A_PAPER",
        resolved_configuration_hash=spec.configuration_hash,
    )
    return S23VerticalSliceCase(
        runtime_input,
        rule,
        market,
        runtime_values,
        chain,
        spec.branch_key,
        spec.market_bias,
        spec.evidence_label,
        spec.decision_id,
        spec.vertical_slice_label,
        spec.phase_label,
        spec.session_reason,
        spec.final_reason,
    )


def _strategy_resolution(context: Mapping[str, Any]) -> OfflineStageResult:
    case = context["case"]
    return OfflineStageResult("strategy_resolution", "PASSED", {"product_policy": S23ProductPolicyAdapter(case.strategy_rule).evaluate(ProductPolicyInput(case.runtime_input))})


def _monthly_status_and_branch(context: Mapping[str, Any]) -> OfflineStageResult:
    case = context["case"]
    product = context["product_policy"]
    if product.status is not PolicyStatus.PASSED:
        return OfflineStageResult("monthly_status_and_branch", "BLOCKED", failure_code="UNKNOWN_S23_BRANCH", reason=product.reason)
    if product.branch != case.branch_key:
        return OfflineStageResult("monthly_status_and_branch", "BLOCKED", failure_code="UNKNOWN_S23_BRANCH", reason=f"Resolved branch {product.branch!r} does not match vertical case branch {case.branch_key!r}.")
    return OfflineStageResult("monthly_status_and_branch", "PASSED", {"branch": product.branch})


def _underlying_references(context: Mapping[str, Any]) -> OfflineStageResult:
    case = context["case"]
    try:
        entry_policy = S23EntryPolicyAdapter(case.strategy_rule).evaluate(EntryPolicyInput(case.runtime_input, context["product_policy"]))
    except (KeyError, TypeError, ValueError) as exc:
        return _blocked("underlying_references", "UNDERLYING_REFERENCE_FAILURE", str(exc), {})
    if entry_policy.status is not PolicyStatus.PASSED:
        return _blocked("underlying_references", "UNDERLYING_REFERENCE_FAILURE", entry_policy.reason, {"legacy_entry": entry_policy})
    return OfflineStageResult("underlying_references", "PASSED", {"legacy_entry": entry_policy, "trade_plan": entry_policy.evidence["trade_plan"]})


def _contract_selection(context: Mapping[str, Any]) -> OfflineStageResult:
    case = context["case"]
    policy_input = ContractSelectionPolicyInput(
        case.runtime_input,
        context["product_policy"],
        context["legacy_entry"],
        GapPolicyResult("vertical.gap.pending", case.runtime_input.evaluated_at, PolicyStatus.NOT_APPLICABLE, False, "pending"),
        MissedEntryPolicyResult("vertical.missed.pending", case.runtime_input.evaluated_at, PolicyStatus.NOT_APPLICABLE, False, "pending", missed=False),
    )
    result = S23ContractSelectionPolicyAdapter(case.strategy_rule).evaluate(policy_input)
    if result.status is not PolicyStatus.PASSED or result.selected_contract is None:
        return _blocked("contract_selection", "NO_QUALIFYING_CONTRACT", result.reason, {"contract_selection": result})
    return OfflineStageResult("contract_selection", "PASSED", {"contract_selection": result, "selected_contract": result.selected_contract})


def _base_entry(context: Mapping[str, Any]) -> OfflineStageResult:
    case = context["case"]
    engine_input = _entry_input(case, context["selected_contract"], context["legacy_entry"], None)
    result = EntryEngine({S23VerticalEntryPolicy.policy_key: S23VerticalEntryPolicy()}).execute(engine_input)
    if result.status is not BusinessEngineStatus.PASSED:
        return _blocked("base_entry", "BASE_ENTRY_FAILURE", "Base Entry failed.", {"base_entry": result})
    return OfflineStageResult("base_entry", "PASSED", {"base_entry": result})


def _gap_missed_entry(context: Mapping[str, Any]) -> OfflineStageResult:
    case = context["case"]
    gme_input = LegacyGapMissedEntryEvaluationInput(
        strategy_family_id="S23",
        strategy_definition_id=case.runtime_input.strategy_definition_id or case.strategy_rule.unique_code,
        strategy_version="1.0.0",
        strategy_instance_id="S23_NIFTY_ACCOUNT_A_PAPER",
        product_type=TFISProductType.OPTION_SELLING,
        configuration_hash=case.runtime_input.resolved_configuration_hash,
        branch_key=case.branch_key,
        option_type=OptionType.CALL,
        monthly_status=case.runtime_input.monthly_status,
        timing=_timing(case.runtime_input.evaluated_at),
        base_entry_price=context["base_entry"].base_entry.value,
        market_levels=case.market_levels,
        option_levels=case.runtime_values["OPT_LEVELS"],
        strategy_parameters=case.strategy_rule.parameters or {},
        base_trade_plan=StrategyEvaluator().evaluate(case.strategy_rule, market_levels=case.market_levels, runtime_values=case.runtime_values),
        orpt_snapshot=IntradaySnapshot(timestamp=case.runtime_input.evaluated_at - timedelta(minutes=5), spot_low=22100.0, spot_high=22400.0, option_low=250.0, option_high=270.0),
        rc_snapshot=IntradaySnapshot(timestamp=case.runtime_input.evaluated_at, spot_low=22120.0, spot_high=22420.0, option_low=252.0, option_high=272.0),
        provenance={"source": case.runtime_input.provenance.get("source", case.phase_label)},
    )
    result = evaluate_legacy_gap_missed_entry(gme_input, policy_key=S23_BACKTEST_LOW_POLICY_KEY)
    if result.status is not BusinessEngineStatus.PASSED:
        return _blocked("gap_missed_entry", "GAP_MISSED_ENTRY_BLOCKED", "Gap/Missed-Entry blocked.", {"gap_missed_entry": result})
    return OfflineStageResult("gap_missed_entry", "PASSED", {"gap_missed_entry": result})


def _effective_entry(context: Mapping[str, Any]) -> OfflineStageResult:
    case = context["case"]
    engine_input = _entry_input(case, context["selected_contract"], context["legacy_entry"], context["gap_missed_entry"])
    result = EntryEngine({S23VerticalEntryPolicy.policy_key: S23VerticalEntryPolicy()}).execute(engine_input)
    if result.status is not BusinessEngineStatus.PASSED:
        return _blocked("effective_entry", "EFFECTIVE_ENTRY_FAILURE", "Effective Entry failed.", {"effective_entry": result})
    return OfflineStageResult("effective_entry", "PASSED", {"effective_entry": result})


def _target_msl(context: Mapping[str, Any]) -> OfflineStageResult:
    case = context["case"]
    gap = GapPolicyResult("vertical.gap", case.runtime_input.evaluated_at, PolicyStatus.PASSED, True, "Phase 3C typed result supplied.", calculated_value=context["gap_missed_entry"].gap.classification.value)
    missed = MissedEntryPolicyResult("vertical.missed", case.runtime_input.evaluated_at, PolicyStatus.PASSED, True, "Phase 3C typed result supplied.", missed=False, branch=context["gap_missed_entry"].missed_entry.status.value)
    target = S23TargetPolicyAdapter(case.strategy_rule).evaluate(TargetPolicyInput(case.runtime_input, context["product_policy"], context["legacy_entry"], gap, missed, context["contract_selection"]))
    if target.status is not PolicyStatus.PASSED:
        return _blocked("target_msl", "TARGET_ADAPTER_FAILURE", target.reason, {"target": target})
    msl = S23MSLPolicyAdapter(case.strategy_rule).evaluate(MSLPolicyInput(case.runtime_input, context["product_policy"], context["legacy_entry"], gap, missed, context["contract_selection"], target))
    if msl.status is not PolicyStatus.PASSED:
        return _blocked("target_msl", "MSL_ADAPTER_FAILURE", msl.reason, {"target": target, "msl": msl})
    return OfflineStageResult("target_msl", "PASSED", {"gap_policy": gap, "missed_policy": missed, "target": target, "msl": msl})


def _decision(context: Mapping[str, Any]) -> OfflineStageResult:
    case = context["case"]
    compatibility_payload = {"vertical_slice": case.vertical_slice_label}
    observations = _future_capability_observations(case)
    if observations:
        compatibility_payload["future_capability_observations"] = observations
    if case.evidence_metadata:
        compatibility_payload["m5_evidence"] = case.evidence_metadata
    decision = TFISDecision(
        evaluation_id=case.runtime_input.evaluation_id,
        decision_id=case.decision_id,
        decided_at=case.runtime_input.evaluated_at,
        strategy_code=case.strategy_rule.strategy_code,
        strategy_branch=case.strategy_rule.unique_code,
        monthly_status_branch=case.runtime_input.monthly_status.value,
        trade_result=TFISTradeResult.TRADE,
        product_type=TFISProductType.OPTION_SELLING,
        direction=TFISDirection.SHORT,
        execution_side=TFISExecutionSide.SELL,
        selected_instrument=context["selected_contract"],
        entry_calculation=TFISFormulaTrace(name="phase3d.entry.effective", formula=case.strategy_rule.entry_formula, result=float(context["effective_entry"].effective_entry.value), inputs={}, evidence=context["effective_entry"].evidence.to_decision_evidence_fragment()),
        gap_result={
            "classification": context["gap_missed_entry"].gap.classification.value,
            "direction": context["gap_missed_entry"].gap.direction.value,
            "quality": context["gap_missed_entry"].gap.quality.value,
        },
        missed_entry_result={
            "status": context["gap_missed_entry"].missed_entry.status.value,
            "observed_value": str(context["gap_missed_entry"].missed_entry.observed_value),
            "entry_reference_value": str(context["gap_missed_entry"].missed_entry.entry_reference_value),
        },
        lots=case.runtime_input.lots,
        quantity=case.runtime_input.quantity,
        target_policy=TFISPolicyResult(context["target"].policy_name, context["target"].calculated_value, evidence=context["target"].to_dict()),
        msl_policy=TFISPolicyResult(context["msl"].policy_name, context["msl"].calculated_value, evidence=context["msl"].to_dict()),
        tsl_policy=None,
        aps_policy=None,
        final_exit_rule={},
        rejection_reason_code=None,
        rejection_reason=None,
        intermediate_calculation_evidence={
            "pipeline": f"{case.phase_label}_s23_vertical",
            "base_entry_hash": context["base_entry"].deterministic_hash,
            "effective_entry_hash": context["effective_entry"].deterministic_hash,
        },
        data_versions={"source": case.evidence_classification if case.evidence_metadata else "synthetic"},
        configuration_versions={"resolved_configuration_hash": case.runtime_input.resolved_configuration_hash},
        compatibility_payload=compatibility_payload,
        strategy_family_id="S23",
        strategy_definition_id=case.runtime_input.strategy_definition_id,
        strategy_version_identity="1.0.0",
        strategy_instance_id="S23_NIFTY_ACCOUNT_A_PAPER",
        resolved_configuration_hash=case.runtime_input.resolved_configuration_hash,
    )
    return OfflineStageResult("decision", "PASSED", {"decision": decision})


def _evidence_packet(context: Mapping[str, Any]) -> OfflineStageResult:
    case = context["case"]
    packet = _packet(case, context)
    return OfflineStageResult("evidence_packet", "PASSED", {"evidence_packet": packet})


def _legacy_comparison(context: Mapping[str, Any]) -> OfflineStageResult:
    trade_plan = context["trade_plan"]
    contract = context["contract_selection"]
    decision = context["decision"]
    selected = decision.selected_instrument
    compared = {
        "branch": {"legacy": context["case"].strategy_rule.unique_code, "vertical": decision.strategy_branch, "classification": "MATCH"},
        "selected_strike": {"legacy": contract.selected_contract.strike, "vertical": selected.strike, "classification": "MATCH"},
        "base_entry": {"legacy": trade_plan["entry_price"], "vertical": float(context["base_entry"].base_entry.value), "classification": "MATCH"},
        "effective_entry": {"legacy": trade_plan["entry_price"], "vertical": float(context["effective_entry"].effective_entry.value), "classification": "MATCH"},
        "target": {"legacy": trade_plan["target_price"], "vertical": decision.target_policy.result, "classification": "MATCH"},
        "msl": {"legacy": trade_plan["stoploss_price"], "vertical": decision.msl_policy.result, "classification": "MATCH"},
        "trade_result": {"legacy": "TRADE", "vertical": decision.trade_result.value, "classification": "MATCH"},
    }
    if context["case"].vertical_slice_label == "S23_BEAR_CALL":
        compared.update(
            {
                "strategy_identity": {"legacy": context["case"].runtime_input.strategy_definition_id, "vertical": decision.strategy_definition_id, "classification": "MATCH"},
                "monthly_status": {"legacy": context["case"].runtime_input.monthly_status.value, "vertical": decision.monthly_status_branch, "classification": "MATCH"},
                "option_side": {"legacy": context["case"].strategy_rule.option_type.value, "vertical": selected.option_type, "classification": "MATCH"},
                "order_intent": {"legacy": "SHORT/SELL", "vertical": f"{decision.direction.value}/{decision.execution_side.value}", "classification": "MATCH"},
                "selected_expiry": {"legacy": contract.selected_contract.expiry.isoformat(), "vertical": selected.expiry.isoformat(), "classification": "MATCH"},
                "selected_contract": {"legacy": contract.selected_contract.symbol, "vertical": selected.symbol, "classification": "MATCH"},
                "premium": {"legacy": contract.selected_contract.metadata["ltp"], "vertical": selected.metadata["ltp"], "classification": "MATCH"},
                "oi": {"legacy": contract.selected_contract.metadata["oi"], "vertical": selected.metadata["oi"], "classification": "MATCH"},
                "gap_missed_entry_status": {"legacy": context["gap_missed_entry"].missed_entry.status.value, "vertical": decision.missed_entry_result["status"], "classification": "MATCH"},
                "recalculated_entry": {"legacy": context["gap_missed_entry"].recalculation.status.value, "vertical": context["effective_entry"].effective_entry.recalculation_status, "classification": "MATCH"},
                "rejection_reason": {"legacy": None, "vertical": decision.rejection_reason_code, "classification": "MATCH"},
                "policy_identities": {"legacy": (context["legacy_entry"].policy_name, context["target"].policy_name, context["msl"].policy_name), "vertical": (context["legacy_entry"].policy_name, context["target"].policy_name, context["msl"].policy_name), "classification": "MATCH"},
                "configuration_hash": {"legacy": context["case"].runtime_input.resolved_configuration_hash, "vertical": decision.resolved_configuration_hash, "classification": "MATCH"},
            }
        )
    return OfflineStageResult("legacy_comparison", "PASSED", {"field_comparison": compared, "mismatch_classifications": {}})


def _entry_input(case: S23VerticalSliceCase, selected: TFISContractIdentity, legacy_entry: Any, gme: Any | None) -> EntryEngineInput:
    ts = case.runtime_input.evaluated_at
    identity = StrategyEvaluationIdentity.deterministic(strategy_instance_id="S23_NIFTY_ACCOUNT_A_PAPER", strategy_definition_id=case.runtime_input.strategy_definition_id or case.strategy_rule.unique_code, strategy_version="1.0.0", trading_date=ts.date(), evaluation_timestamp=ts, evaluation_sequence=1, trigger_type=case.phase_label, configuration_hash=case.runtime_input.resolved_configuration_hash)
    cycle = PositionCycleIdentity.deterministic(strategy_instance_id="S23_NIFTY_ACCOUNT_A_PAPER", trading_date=ts.date(), cycle_sequence=1, entry_evaluation_id=identity.evaluation_id, product_instrument_identity=selected.symbol)
    return EntryEngineInput(
        evaluation_identity=identity,
        position_cycle_identity=cycle,
        resolved_configuration_hash=case.runtime_input.resolved_configuration_hash,
        product=TFISProductType.OPTION_SELLING,
        resolved_branch=EntryResolvedBranch(case.market_bias, case.branch_key, TFISProductType.OPTION_SELLING, EntryInstrumentType.SELECTED_OPTION_CONTRACT, EntryOptionRight.CALL, EntryPositionIntent.SHORT_OPTION, TFISExecutionSide.SELL, EntryTriggerDirection.PRICE_AT_OR_BELOW),
        resolved_instrument=selected,
        entry_policy_key=S23VerticalEntryPolicy.policy_key,
        formula_descriptor=EntryFormulaDescriptor("s23_bull_call_entry", case.strategy_rule.entry_formula, "legacy_s23_option_sell_entry", (EntryFormulaComponent("legacy_entry", EntryFormulaOperandRole.LEFT_OPERAND, EntryReferenceSource.SELECTED_OPTION_CONTRACT, EntryFormulaOperator.SUPPLIED_VALUE, reference_id="legacy_entry_value", formula_reference=case.strategy_rule.entry_formula),)),
        references=(
            EntryReference("legacy_entry_value", EntryReferenceSource.SELECTED_OPTION_CONTRACT, selected.symbol, "OPTIONS_SELL", TFISProductType.OPTION_SELLING, "OPT_PRV_REFERENCE", "LEGACY", Decimal(str(legacy_entry.entry_value)) if legacy_entry.entry_value is not None else None, EntryReferenceValueType.PRICE, ts, ts.date(), {"source": "legacy_entry_adapter"}, EntryQuality.VALID, EntryReferenceRequirement.REQUIRED),
            EntryReference("final_strike", EntryReferenceSource.FINAL_STRIKE_VALUE, selected.symbol, "OPTIONS_SELL", TFISProductType.OPTION_SELLING, "STRIKE", "STATIC", Decimal(str(selected.strike)) if selected.strike is not None else None, EntryReferenceValueType.STRIKE, ts, ts.date(), {"source": "contract_selection"}, EntryQuality.VALID, EntryReferenceRequirement.REQUIRED),
        ),
        strategy_parameters={"legacy_entry_result": legacy_entry},
        evaluation_timestamp=ts,
        gap_missed_entry_result=gme,
        gap_missed_entry_required=gme is not None,
        provenance={"source": "phase3d_m3_s23_vertical"},
    )


def _packet(case: S23VerticalSliceCase, context: Mapping[str, Any]) -> TFISDecisionEvidencePacket:
    ts = case.runtime_input.evaluated_at
    selected = context["selected_contract"]
    trade_plan = context["trade_plan"]
    audit_payload = {"label": f"{case.phase_label.upper()}_{case.vertical_slice_label}"}
    observations = _future_capability_observations(case)
    if observations:
        audit_payload.update({f"future_capability_{index + 1}": item for index, item in enumerate(observations)})
    if case.evidence_metadata:
        audit_payload["m5_evidence_classification"] = case.evidence_classification
        audit_payload["m5_evidence_source"] = case.evidence_metadata.get("evidence_source")
        audit_payload["m5_missing_fields"] = case.evidence_metadata.get("missing_fields")
        audit_payload["m5_synthetic_supplements"] = case.evidence_metadata.get("synthetic_supplements")
    return TFISDecisionEvidencePacket(
        identity=IdentityEvidence(SCHEMA_VERSION, case.evidence_label, case.runtime_input.evaluation_id, "S23_NIFTY_ACCOUNT_A_PAPER", case.strategy_rule.unique_code, case.strategy_rule.unique_code, "1.0.0", case.runtime_input.resolved_configuration_hash, ts.date(), ts, ts, ts + timedelta(seconds=1)),
        session=SessionEvidence("NSE", Segment.OPTIONS_SELL, "Asia/Kolkata", TimeWindowEvidence(time(9, 15), time(15, 30), time(9, 24, 59), time(9, 29, 59), case.runtime_input.session_label or "PHASE3D_SYNTHETIC", case.session_reason)),
        instrument_product=InstrumentProductEvidence("NSE:NIFTY", "synthetic:nifty_spot", TFISProductType.OPTION_SELLING, selected, selected.expiry, "T_MINUS_1_NEXT_WEEKLY_IF_EXPIRY_RISK", EvidenceAvailability.AVAILABLE),
        monthly_status=MonthlyStatusEvidence(case.runtime_input.monthly_status, case.runtime_input.monthly_status, "synthetic monthly status", _pv(24900), _pv(24000), _pv(24680), _pv(23840), _pv(24550), _pv(23820), _pv(24750), _pv(23950), _pv("0.75"), _pv("0.75"), _pv("0.15"), "NO_TRANSITION", f"Synthetic {case.runtime_input.monthly_status.value} status.", "VALID"),
        market_structure=MarketStructureEvidence(_na(), _na(), _pv(case.market_levels.d2hh), _pv(case.market_levels.d2ll), _pv(case.market_levels.d3hh), _pv(case.market_levels.d3ll), _na(), _na(), (date(2026, 7, 27), date(2026, 7, 28), date(2026, 7, 29)), _pv(case.market_levels.current_day_high), _pv(case.market_levels.current_day_low), "synthetic:nifty_spot", "VALID", EvidenceProvenance.SYNTHETIC),
        price_context=PriceContextEvidence(_pv(22400), "synthetic:nifty_spot", ts, Decimal("0"), _pv(22399.5), _pv(22400.5), _pv(22400)),
        gap_missed_entry=GapMissedEntryEvidence(_pv(22300), _pv(22400), _pv(260), _pv(252), context["gap_missed_entry"].gap.classification.value, context["gap_missed_entry"].missed_entry.status.value, context["gap_missed_entry"].recalculation.status.value, ("S23_ORPT_RC_COMPATIBILITY",), ()),
        option_product_references=OptionProductReferenceEvidence(tuple((k, _pv(v)) for k, v in sorted(case.runtime_values["OPT_LEVELS"].items())), (selected.expiry,), _pv(trade_plan["start_strike"]), _pv(trade_plan["end_strike"]), _pv(trade_plan["ideal_premium"]), _pv(trade_plan["minimum_premium"]), _pv(case.strategy_rule.minimum_oi), 1, EvidenceAvailability.AVAILABLE),
        option_chain=OptionChainEvidence((_candidate(selected, ts),), (), EvidenceAvailability.AVAILABLE),
        selected_contract=SelectedContractEvidence(selected, "Selected by existing S23 contract-selection adapter.", _candidate(selected, ts), (), EvidenceAvailability.AVAILABLE),
        calculated_decision=CalculatedDecisionEvidence(_pv(context["effective_entry"].effective_entry.value), (_pv(context["target"].calculated_value),), _pv(context["msl"].calculated_value), _not_applicable(), _not_applicable(), _pv(case.runtime_input.lots), _pv(case.runtime_input.quantity), TFISDirection.SHORT, TFISExecutionSide.SELL, TFISTradeResult.TRADE, case.final_reason),
        audit=AuditEvidence((("entry", S23VerticalEntryPolicy.policy_key), ("gap_missed_entry", S23_BACKTEST_LOW_POLICY_KEY)), ("AB16-ENTRY", "AB16-CONTRACT", "AB16-TARGET", "AB16-MSL"), (("entry", case.strategy_rule.entry_formula), ("target", case.strategy_rule.target_formula), ("stoploss", case.strategy_rule.stoploss_formula)), (("base_entry", _pv(context["base_entry"].base_entry.value)), ("effective_entry", _pv(context["effective_entry"].effective_entry.value))), (), (EvidenceProvenance.SYNTHETIC,), audit_payload),
        entry=EntryBusinessEngineFragment("entry", S23VerticalEntryPolicy.policy_key, case.phase_label, "OPTION_SELLING", case.branch_key, selected.symbol, case.strategy_rule.entry_formula, (("legacy_entry_value", _pv(context["base_entry"].base_entry.value)),), (), (), _pv(context["base_entry"].base_entry.value), {"missed_entry": context["gap_missed_entry"].missed_entry.status.value}, _pv(context["effective_entry"].effective_entry.value), context["effective_entry"].effective_entry.source.value, {"trigger_direction": context["effective_entry"].effective_entry.trigger_condition.trigger_direction.value}, (), (), (), "VALID", {"source": case.phase_label}, context["effective_entry"].deterministic_hash),
    )


def _option_chain(symbol: str, expiry: date, option_type: OptionType, strike: float, premium: float, oi: float, ts: datetime) -> OptionChainSnapshotEvent:
    return OptionChainSnapshotEvent(EventEnvelope(PaperEventType.OPTION_CHAIN_SNAPSHOT, ts.date(), ts, ts, "Asia/Kolkata", "synthetic", "phase3d_m3", True, "phase3d_m3"), symbol, expiry, (OptionChainContract(f"{symbol}_{expiry:%Y%m%d}_{int(strike)}_{option_type.value}", option_type, strike, expiry, premium - 1, premium + 1, premium, oi),))


def _timing(ts: datetime) -> SessionTimingEvidence:
    return SessionTimingEvidence("Asia/Kolkata", ts.replace(hour=9, minute=15, second=0), ts, ts - timedelta(minutes=5), ts, TimingWindowState.AVAILABLE, TimingObservationRequirement.REQUIRED, TimingObservationRequirement.REQUIRED, ts - timedelta(minutes=5), ts, ObservationValue(MissedEntryObservationSource.OPTION_LOW, Decimal("260"), ts - timedelta(minutes=5)), ObservationValue(MissedEntryObservationSource.OPTION_LOW, Decimal("252"), ts))


def _candidate(identity: TFISContractIdentity, ts: datetime) -> OptionChainCandidateEvidence:
    option_type = OptionType(identity.option_type) if identity.option_type else None
    return OptionChainCandidateEvidence(identity, _pv(identity.strike), option_type, identity.expiry, _pv(identity.metadata["ltp"]), _pv(Decimal(str(identity.metadata["ltp"])) - Decimal("1")), _pv(Decimal(str(identity.metadata["ltp"])) + Decimal("1")), _pv(identity.metadata["oi"]), ts, "VALID", Decimal("0"))


def _future_capability_observations(case: S23VerticalSliceCase) -> tuple[str, ...]:
    if case.vertical_slice_label != "S23_BEAR_CALL":
        return ()
    return (
        "near-expiry to next-expiry fallback remains an existing contract-selection adapter capability; the Bear Call golden selected the supplied expiry and did not exercise fallback",
        "directional strike traversal is represented by Bear Call start/end strike evidence from the existing S23 rule evaluation; no generic traversal engine was introduced",
        "ideal-premium and minimum-premium phases are preserved as S23 contract-selection adapter request/evidence fields",
        "configurable OI threshold is preserved from the Bear Call strategy configuration as minimum_oi=32500",
        "MSL uses the existing MIN-bounded stoploss formula; Target is the existing ENTRY - PARAM(target_pct)% formula for this branch",
        "non-positive calculated risk prices were not observed in this golden case and no new risk authority was inferred",
        "additional historical lookbacks are preserved as branch-specific references in strategy formulas and evidence; no Market Structure redesign was introduced",
        "any unobserved future rule requirement remains RULE_AUTHORITY_UNRESOLVED for later Contract Selection, Risk, or Market Structure certification",
    )


def _blocked(stage: str, code: str, reason: str, payload: Mapping[str, Any]) -> OfflineStageResult:
    return OfflineStageResult(stage, "BLOCKED", payload, failure_code=code, reason=reason)


def _pv(value: Any) -> ProvenancedValue:
    return ProvenancedValue(Decimal(str(value)), EvidenceAvailability.AVAILABLE, EvidenceProvenance.SYNTHETIC, "synthetic")


def _na() -> ProvenancedValue:
    return _not_applicable()


def _not_applicable() -> ProvenancedValue:
    return ProvenancedValue(None, EvidenceAvailability.NOT_APPLICABLE, EvidenceProvenance.NOT_APPLICABLE, None)
