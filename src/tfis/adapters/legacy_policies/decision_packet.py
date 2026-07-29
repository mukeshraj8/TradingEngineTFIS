from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from tfis.decision import TFISDecisionEngine
from tfis.domain import (
    AuditEvidence,
    CalculatedDecisionEvidence,
    DecisionEvidenceCompleteness,
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
    PriceContextEvidence,
    ProvenancedValue,
    Segment,
    SelectedContractEvidence,
    SessionEvidence,
    TFISContractIdentity,
    TFISDecision,
    TFISDecisionEvidencePacket,
    TFISDirection,
    TFISExecutionSide,
    TFISProductType,
    TFISRuntimeInput,
    TFISTradeResult,
    TimeWindowEvidence,
    validate_decision_evidence_packet,
)
from tfis.importers import load_strategy_rule
from tfis.paper import EventEnvelope, OptionChainContract, OptionChainSnapshotEvent, PaperEventType
from tfis.paper.contract_selection import S23PaperContractSelectionRequest, S23PaperContractSelectionResult, S23PaperContractSelector
from tfis.strategy import StrategyEvaluator

from .captured_shadow import CapturedDecisionCase, load_captured_jsonl_cases
from .composition import LegacyPolicyRegistryFactory, policy_selection_for_strategy


SCHEMA_VERSION = "tfis.decision_evidence_packet.v1"
ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True, slots=True)
class DecisionPacketParityResult:
    packet_id: str
    completeness: DecisionEvidenceCompleteness
    legacy_trade_result: TFISTradeResult
    generic_trade_result: TFISTradeResult
    compared_fields: Mapping[str, tuple[Any, Any]]
    mismatches: Mapping[str, tuple[Any, Any]]

    @property
    def passed(self) -> bool:
        return not self.mismatches


@dataclass(frozen=True, slots=True)
class DecisionPacketPerformance:
    serialized_size_bytes: int
    serialization_seconds: float
    deserialization_seconds: float
    validation_seconds: float
    parity_evaluation_seconds: float
    option_chain_candidate_count: int
    scale_risk: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "serialized_size_bytes": self.serialized_size_bytes,
            "serialization_seconds": self.serialization_seconds,
            "deserialization_seconds": self.deserialization_seconds,
            "validation_seconds": self.validation_seconds,
            "parity_evaluation_seconds": self.parity_evaluation_seconds,
            "option_chain_candidate_count": self.option_chain_candidate_count,
            "scale_risk": self.scale_risk,
        }


def build_s23_synthetic_golden_packet() -> TFISDecisionEvidencePacket:
    rule = _strategy_rule("S23", "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT")
    evaluated_at = datetime(2026, 7, 29, 9, 29, 59, tzinfo=ZoneInfo("Asia/Kolkata"))
    market = MarketLevels(
        d2hh=22500.0,
        d2ll=21900.0,
        d3hh=22600.0,
        d3ll=22000.0,
        current_day_high=22400.0,
        current_day_low=22100.0,
    )
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
    selected_identity = TFISContractIdentity(
        symbol="NIFTY_20260806_22350_PE",
        exchange="NSE",
        segment=Segment.OPTIONS_SELL,
        product_type=TFISProductType.OPTION_SELLING,
        expiry=expiry,
        strike=float(plan.start_strike),
        option_type=OptionType.PUT.value,
        metadata={"ltp": float(plan.ideal_premium), "oi": 999999.0},
    )
    selected_candidate = _candidate(
        selected_identity,
        option_type=OptionType.PUT,
        expiry=expiry,
        ltp=plan.ideal_premium,
        bid=plan.ideal_premium - 1.0,
        ask=plan.ideal_premium + 1.0,
        oi=999999.0,
        quote_timestamp=evaluated_at,
    )
    policy_selection = policy_selection_for_strategy(rule.strategy_code).policy_selection
    return TFISDecisionEvidencePacket(
        identity=IdentityEvidence(
            packet_schema_version=SCHEMA_VERSION,
            packet_id="SYNTHETIC_GOLDEN:S23:NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT:2026-07-29T09:29:59+05:30",
            evaluation_id="phase2d1-synthetic-golden-s23-bear-put",
            strategy_instance_id=rule.unique_code,
            strategy_unique_code=rule.unique_code,
            strategy_branch=rule.unique_code,
            configuration_version="phase2d1-synthetic-golden",
            configuration_hash="synthetic-s23-bear-put-v1",
            trading_date=evaluated_at.date(),
            evaluation_timestamp=evaluated_at,
            event_timestamp=evaluated_at,
            processing_timestamp=evaluated_at + timedelta(seconds=1),
        ),
        session=SessionEvidence(
            exchange="NSE",
            segment=Segment.OPTIONS_SELL,
            timezone="Asia/Kolkata",
            time_window=TimeWindowEvidence(
                market_start=time(9, 15),
                market_end=time(15, 30),
                orpt_time=time(9, 24, 59),
                rc_time=time(9, 29, 59),
                evaluation_trigger="SYNTHETIC_GOLDEN_OFFLINE",
                evaluation_reason="Complete packet contract proof.",
            ),
        ),
        instrument_product=InstrumentProductEvidence(
            underlying_identity="NSE:NIFTY",
            price_source_identity="synthetic:nifty_spot",
            product_type=TFISProductType.OPTION_SELLING,
            contract_identity=selected_identity,
            expiry=expiry,
            rollover_context="T_MINUS_1_NEXT_WEEKLY_IF_EXPIRY_RISK",
            contract_availability=EvidenceAvailability.AVAILABLE,
        ),
        monthly_status=MonthlyStatusEvidence(
            previous_persisted_status=MonthlyStatus.BEAR,
            resolved_current_status=MonthlyStatus.BEAR,
            status_evidence="synthetic monthly-status packet evidence",
            pmh=_pv(24900),
            pml=_pv(24000),
            pwh=_pv(24680),
            pwl=_pv(23840),
            cwh=_pv(24550),
            cwl=_pv(23820),
            cmh=_pv(24750),
            cml=_pv(23950),
            parameter_a_pct=_pv("0.75"),
            parameter_b_pct=_pv("0.75"),
            parameter_c_pct=_pv("0.15"),
            transition_condition="NO_TRANSITION",
            transition_reason="Synthetic packet preserves BEAR status.",
            status_quality="VALID",
        ),
        market_structure=MarketStructureEvidence(
            prv_1d_hh=_na(),
            prv_1d_ll=_na(),
            prv_2d_hh=_pv(market.d2hh),
            prv_2d_ll=_pv(market.d2ll),
            prv_3d_hh=_pv(market.d3hh),
            prv_3d_ll=_pv(market.d3ll),
            prv_4d_hh=_na(),
            prv_4d_ll=_na(),
            included_candle_dates=(date(2026, 7, 24), date(2026, 7, 27), date(2026, 7, 28)),
            current_day_high=_pv(market.current_day_high),
            current_day_low=_pv(market.current_day_low),
            source_contract="synthetic:nifty_spot",
            quality="VALID",
            provenance=EvidenceProvenance.SYNTHETIC,
        ),
        price_context=PriceContextEvidence(
            cmp=_pv(22400),
            cmp_source="synthetic:nifty_spot",
            event_timestamp=evaluated_at,
            freshness_seconds=Decimal("0"),
            bid=_pv(22399.5),
            ask=_pv(22400.5),
            ltp=_pv(22400),
        ),
        gap_missed_entry=GapMissedEntryEvidence(
            opening_price=_pv(22300),
            reference_price=_pv(22400),
            orpt_observation=_pv(22448),
            rc_observation=_pv(22440),
            gap_classification="NO_GAP",
            missed_entry_classification="NOT_MISSED",
            recalculation_branch="NOT_APPLICABLE",
            formulas=("S23_ORPT_RC_SYNTHETIC",),
            intermediate_values=(("orpt_high", _pv(22455)), ("rc_low", _pv(22435))),
        ),
        option_product_references=OptionProductReferenceEvidence(
            option_reference_values=tuple(
                (key, _pv(value))
                for key, value in sorted(runtime_values["OPT_LEVELS"].items())
            ),
            expiry_candidates=(expiry,),
            strike_range_start=_pv(plan.start_strike),
            strike_range_end=_pv(plan.end_strike),
            ideal_premium=_pv(plan.ideal_premium),
            minimum_premium=_pv(plan.minimum_premium),
            minimum_oi=_pv(rule.minimum_oi),
            expiries_to_check=1,
            availability=EvidenceAvailability.AVAILABLE,
        ),
        option_chain=OptionChainEvidence(
            candidates=(selected_candidate,),
            rejected_candidate_reasons=(),
            availability=EvidenceAvailability.AVAILABLE,
        ),
        selected_contract=SelectedContractEvidence(
            selected_identity=selected_identity,
            selection_reason="Selected first strike meeting ideal premium in rule-sheet search order.",
            selected_quote=selected_candidate,
            rejected_candidate_reasons=(),
            availability=EvidenceAvailability.AVAILABLE,
        ),
        calculated_decision=CalculatedDecisionEvidence(
            entry=_pv(plan.entry_price),
            targets=(_pv(plan.target_price),),
            msl=_pv(plan.stoploss_price),
            tsl_plan=_not_applicable(),
            aps_plan=_not_applicable(),
            lots=_pv(1),
            quantity=_pv(50),
            direction=TFISDirection.SHORT,
            execution_side=TFISExecutionSide.SELL,
            trade_result=TFISTradeResult.TRADE,
            final_reason="Synthetic golden packet expected TRADE.",
        ),
        audit=AuditEvidence(
            policy_keys=tuple(
                sorted(
                    {
                        "product": policy_selection.product,
                        "entry": policy_selection.entry,
                        "gap": policy_selection.gap,
                        "missed_entry": policy_selection.missed_entry,
                        "contract_selection": policy_selection.contract_selection,
                        "target": policy_selection.target,
                        "msl": policy_selection.msl,
                    }.items()
                )
            ),
            requirement_ids=("AB16-ENTRY", "AB16-CONTRACT", "AB16-TARGET", "AB16-MSL"),
            formula_expressions=(
                ("start_strike", rule.start_strike_formula),
                ("end_strike", rule.end_strike_formula),
                ("entry", rule.entry_formula),
                ("target", rule.target_formula),
                ("stoploss", rule.stoploss_formula),
            ),
            intermediate_values=(
                ("start_strike", _pv(plan.start_strike)),
                ("end_strike", _pv(plan.end_strike)),
                ("ideal_premium", _pv(plan.ideal_premium)),
                ("minimum_premium", _pv(plan.minimum_premium)),
            ),
            data_quality_warnings=(),
            evidence_classifications=(EvidenceProvenance.SYNTHETIC,),
            compatibility_payload={"label": "SYNTHETIC_GOLDEN"},
        ),
    )


def packet_from_captured_case(case: CapturedDecisionCase) -> TFISDecisionEvidencePacket:
    expected = dict(case.expected_legacy_decision)
    event_time = case.capture_timestamp
    option_candidate = None
    selected_identity = None
    if case.selected_contract_quote is not None:
        selected_identity = TFISContractIdentity(
            symbol=case.selected_contract_quote.symbol,
            exchange="NSE",
            segment=Segment.OPTIONS_SELL,
            product_type=TFISProductType.OPTION_SELLING,
            expiry=case.selected_contract_quote.expiry,
            strike=case.selected_contract_quote.strike,
            option_type=case.selected_contract_quote.option_type.value if case.selected_contract_quote.option_type else None,
            metadata={
                "ltp": case.selected_contract_quote.ltp,
                "oi": case.selected_contract_quote.oi,
            },
        )
        option_candidate = _candidate(
            selected_identity,
            option_type=case.selected_contract_quote.option_type,
            expiry=case.selected_contract_quote.expiry,
            ltp=case.selected_contract_quote.ltp,
            bid=case.selected_contract_quote.bid,
            ask=case.selected_contract_quote.ask,
            oi=case.selected_contract_quote.oi,
            quote_timestamp=case.selected_contract_quote.envelope.effective_timestamp,
            provenance=EvidenceProvenance.CAPTURED,
        )
    candidates = tuple(
        _candidate(
            TFISContractIdentity(
                symbol=item.symbol,
                exchange="NSE",
                segment=Segment.OPTIONS_SELL,
                product_type=TFISProductType.OPTION_SELLING,
                expiry=item.expiry,
                strike=item.strike,
                option_type=item.option_type.value if item.option_type else None,
                metadata={"ltp": item.ltp, "oi": item.oi},
            ),
            option_type=item.option_type,
            expiry=item.expiry,
            ltp=item.ltp,
            bid=item.bid,
            ask=item.ask,
            oi=item.oi,
            quote_timestamp=case.option_chain_snapshot.envelope.effective_timestamp,
            provenance=EvidenceProvenance.CAPTURED,
        )
        for item in (case.option_chain_snapshot.contracts if case.option_chain_snapshot else ())
    )
    if option_candidate is not None and not candidates:
        candidates = (option_candidate,)
    return TFISDecisionEvidencePacket(
        identity=IdentityEvidence(
            packet_schema_version=SCHEMA_VERSION,
            packet_id=f"CAPTURED_PARTIAL:{case.case_id}",
            evaluation_id=f"phase2d1-{case.case_id}",
            strategy_instance_id=case.strategy_instance,
            strategy_unique_code=case.strategy_instance,
            strategy_branch=case.strategy_instance,
            configuration_version="phase2d1-captured-import",
            configuration_hash="captured-import-partial",
            trading_date=event_time.date(),
            evaluation_timestamp=event_time,
            event_timestamp=event_time,
            processing_timestamp=event_time,
        ),
        session=SessionEvidence(
            exchange="NSE",
            segment=Segment.OPTIONS_SELL,
            timezone=str(case.runtime_inputs.get("timezone") or "Asia/Kolkata"),
            time_window=TimeWindowEvidence(
                market_start=time(9, 15),
                market_end=time(15, 30),
                orpt_time=time(9, 24, 59),
                rc_time=time(9, 29, 59),
                evaluation_trigger="CAPTURED_JSONL_IMPORT",
                evaluation_reason="Existing Phase 2D captured case converted to packet.",
            ),
        ),
        instrument_product=InstrumentProductEvidence(
            underlying_identity="NSE:NIFTY",
            price_source_identity=str(case.runtime_inputs.get("source_id") or "captured_jsonl"),
            product_type=TFISProductType.OPTION_SELLING,
            contract_identity=selected_identity,
            expiry=selected_identity.expiry if selected_identity else None,
            rollover_context="CAPTURED_PARTIAL",
            contract_availability=EvidenceAvailability.AVAILABLE if selected_identity else EvidenceAvailability.UNAVAILABLE,
        ),
        monthly_status=MonthlyStatusEvidence(
            previous_persisted_status=case.monthly_status,
            resolved_current_status=case.monthly_status,
            status_evidence="captured monthly-status event",
            pmh=_unavailable(),
            pml=_unavailable(),
            pwh=_unavailable(),
            pwl=_unavailable(),
            cwh=_unavailable(),
            cwl=_unavailable(),
            cmh=_unavailable(),
            cml=_unavailable(),
            parameter_a_pct=_unavailable(),
            parameter_b_pct=_unavailable(),
            parameter_c_pct=_unavailable(),
            transition_condition="CAPTURED_RESULT_ONLY",
            transition_reason="Raw monthly-status transition inputs not present in captured fixture.",
            status_quality="PARTIAL",
        ),
        market_structure=MarketStructureEvidence(
            prv_1d_hh=_unavailable(),
            prv_1d_ll=_unavailable(),
            prv_2d_hh=_unavailable(),
            prv_2d_ll=_unavailable(),
            prv_3d_hh=_unavailable(),
            prv_3d_ll=_unavailable(),
            prv_4d_hh=_unavailable(),
            prv_4d_ll=_unavailable(),
            included_candle_dates=(),
            current_day_high=_pv(case.current_day_references.get("rc_high"), provenance=EvidenceProvenance.CAPTURED) if case.current_day_references.get("rc_high") is not None else _unavailable(),
            current_day_low=_pv(case.current_day_references.get("rc_low"), provenance=EvidenceProvenance.CAPTURED) if case.current_day_references.get("rc_low") is not None else _unavailable(),
            source_contract="captured_jsonl",
            quality="PARTIAL",
            provenance=EvidenceProvenance.CAPTURED,
        ),
        price_context=PriceContextEvidence(
            cmp=_pv(case.current_day_references.get("rc_close"), provenance=EvidenceProvenance.CAPTURED) if case.current_day_references.get("rc_close") is not None else _unavailable(),
            cmp_source="captured_rc_close",
            event_timestamp=event_time,
            freshness_seconds=Decimal("0"),
            bid=_unavailable(),
            ask=_unavailable(),
            ltp=_unavailable(),
        ),
        gap_missed_entry=GapMissedEntryEvidence(
            opening_price=_unavailable(),
            reference_price=_unavailable(),
            orpt_observation=_pv(case.orpt_rc_evidence.get("orpt", {}).get("close"), provenance=EvidenceProvenance.CAPTURED) if case.orpt_rc_evidence.get("orpt") else _unavailable(),
            rc_observation=_pv(case.orpt_rc_evidence.get("rc", {}).get("close"), provenance=EvidenceProvenance.CAPTURED) if case.orpt_rc_evidence.get("rc") else _unavailable(),
            gap_classification="CAPTURED_PARTIAL",
            missed_entry_classification="CAPTURED_PARTIAL",
            recalculation_branch=str(case.orpt_rc_evidence.get("status") or "UNKNOWN"),
            formulas=(),
            intermediate_values=(),
        ),
        option_product_references=OptionProductReferenceEvidence(
            option_reference_values=(),
            expiry_candidates=(case.option_chain_snapshot.expiry,) if case.option_chain_snapshot else (),
            strike_range_start=_pv(expected.get("start_strike"), provenance=EvidenceProvenance.CAPTURED) if expected.get("start_strike") is not None else _unavailable(),
            strike_range_end=_pv(expected.get("end_strike"), provenance=EvidenceProvenance.CAPTURED) if expected.get("end_strike") is not None else _unavailable(),
            ideal_premium=_pv(expected.get("ideal_premium"), provenance=EvidenceProvenance.CAPTURED) if expected.get("ideal_premium") is not None else _unavailable(),
            minimum_premium=_pv(expected.get("minimum_premium"), provenance=EvidenceProvenance.CAPTURED) if expected.get("minimum_premium") is not None else _unavailable(),
            minimum_oi=_unavailable(),
            expiries_to_check=1,
            availability=EvidenceAvailability.AVAILABLE if case.option_chain_snapshot else EvidenceAvailability.UNAVAILABLE,
        ),
        option_chain=OptionChainEvidence(
            candidates=candidates,
            rejected_candidate_reasons=(),
            availability=EvidenceAvailability.AVAILABLE if candidates else EvidenceAvailability.UNAVAILABLE,
        ),
        selected_contract=SelectedContractEvidence(
            selected_identity=selected_identity,
            selection_reason="Captured selected contract quote." if selected_identity else "Selected contract quote absent.",
            selected_quote=option_candidate,
            rejected_candidate_reasons=(),
            availability=EvidenceAvailability.AVAILABLE if selected_identity else EvidenceAvailability.UNAVAILABLE,
        ),
        calculated_decision=CalculatedDecisionEvidence(
            entry=_pv(expected.get("planned_entry_price"), provenance=EvidenceProvenance.CAPTURED) if expected.get("planned_entry_price") is not None else _unavailable(),
            targets=(_pv(expected.get("target_price"), provenance=EvidenceProvenance.CAPTURED),) if expected.get("target_price") is not None else (),
            msl=_pv(expected.get("stoploss_price"), provenance=EvidenceProvenance.CAPTURED) if expected.get("stoploss_price") is not None else _unavailable(),
            tsl_plan=_not_applicable(),
            aps_plan=_not_applicable(),
            lots=_pv(expected.get("lots"), provenance=EvidenceProvenance.CAPTURED) if expected.get("lots") is not None else _unavailable(),
            quantity=_pv(expected.get("quantity"), provenance=EvidenceProvenance.CAPTURED) if expected.get("quantity") is not None else _unavailable(),
            direction=TFISDirection.SHORT,
            execution_side=TFISExecutionSide.SELL,
            trade_result=TFISTradeResult.TRADE,
            final_reason="Captured trade plan output.",
        ),
        audit=AuditEvidence(
            policy_keys=(),
            requirement_ids=tuple(str(expected.get(key)) for key in ("source_workbook_rule", "workbook_row_number") if expected.get(key) is not None),
            formula_expressions=(),
            intermediate_values=(),
            data_quality_warnings=case.missing_fields,
            evidence_classifications=(EvidenceProvenance.CAPTURED,),
            compatibility_payload={"source_file": case.source_file.as_posix()},
        ),
    )


def captured_cases_to_packets(paths: Iterable[str | Path]) -> tuple[TFISDecisionEvidencePacket, ...]:
    return tuple(packet_from_captured_case(case) for case in load_captured_jsonl_cases(paths))


def runtime_input_from_packet(packet: TFISDecisionEvidencePacket) -> TFISRuntimeInput:
    rule = _strategy_rule_for_packet(packet)
    chain = option_chain_snapshot_from_packet(packet)
    option_values = {
        key: float(value.value)
        for key, value in packet.option_product_references.option_reference_values
        if value.availability is EvidenceAvailability.AVAILABLE and value.value is not None
    }
    return TFISRuntimeInput(
        evaluation_id=packet.identity.evaluation_id,
        evaluated_at=packet.identity.evaluation_timestamp,
        strategy_code=rule.strategy_code,
        strategy_version=packet.identity.configuration_version,
        strategy_branch=rule.unique_code,
        symbol=rule.symbol,
        segment=rule.segment,
        product_type=packet.instrument_product.product_type,
        account_id=None,
        lots=_int_value(packet.calculated_decision.lots),
        quantity=_int_value(packet.calculated_decision.quantity),
        session_date=packet.identity.trading_date,
        session_label="phase2d1-decision-evidence-packet",
        timezone=packet.session.timezone,
        price_source=packet.price_context.cmp_source,
        cmp=_float_value(packet.price_context.cmp),
        contract=None,
        monthly_status=packet.monthly_status.resolved_current_status,
        monthly_status_evidence={"packet_id": packet.identity.packet_id},
        market_structure_references=_market_structure_mapping(packet),
        current_week_references={},
        current_month_references={},
        gap_context={"orpt_rc_timing": {"status": packet.gap_missed_entry.recalculation_branch, "reason": packet.gap_missed_entry.missed_entry_classification}},
        option_chain_context=None,
        data_quality={"packet_validation": validate_decision_evidence_packet(packet).completeness.value},
        provenance={"packet_id": packet.identity.packet_id},
        configuration_snapshot={"strategy_unique_code": rule.unique_code},
        configuration_version=packet.identity.configuration_version,
        runtime_values={"OPT_LEVELS": option_values},
        product_specific={
            "option_chain_snapshot": chain,
            "expiry_date": packet.instrument_product.expiry,
        },
        strategy_family_id=(
            "OPTION_SELLING"
            if packet.instrument_product.product_type is TFISProductType.OPTION_SELLING
            else None
        ),
        strategy_definition_id=packet.identity.strategy_unique_code,
        strategy_instance_id=packet.identity.strategy_instance_id,
        resolved_configuration_hash=packet.identity.configuration_hash,
    )


def evaluate_packet_with_legacy(packet: TFISDecisionEvidencePacket) -> tuple[Any, S23PaperContractSelectionResult]:
    rule = _strategy_rule_for_packet(packet)
    market = _market_levels(packet)
    runtime_values = {
        "OPT_LEVELS": {
            key: float(value.value)
            for key, value in packet.option_product_references.option_reference_values
            if value.availability is EvidenceAvailability.AVAILABLE and value.value is not None
        }
    }
    plan = StrategyEvaluator().evaluate(rule, market_levels=market, runtime_values=runtime_values)
    selector_result = S23PaperContractSelector().select(
        S23PaperContractSelectionRequest(
            underlying_symbol=rule.symbol,
            expiry_date=packet.instrument_product.expiry,
            option_type=rule.option_type,
            start_strike=float(plan.start_strike),
            end_strike=float(plan.end_strike),
            ideal_premium=float(plan.ideal_premium),
            minimum_premium=float(plan.minimum_premium),
            minimum_oi=float(rule.minimum_oi),
        ),
        option_chain_snapshot_from_packet(packet),
    )
    return plan, selector_result


def evaluate_packet_with_generic(packet: TFISDecisionEvidencePacket) -> TFISDecision:
    rule = _strategy_rule_for_packet(packet)
    composition = policy_selection_for_strategy(rule.strategy_code)
    registry = LegacyPolicyRegistryFactory().build(rule)
    return TFISDecisionEngine(registry.compose(composition.policy_selection)).evaluate(
        runtime_input_from_packet(packet)
    )


def run_decision_packet_parity(packet: TFISDecisionEvidencePacket) -> DecisionPacketParityResult:
    validation = validate_decision_evidence_packet(packet)
    legacy_plan = None
    legacy_selection = None
    if validation.is_full:
        legacy_plan, legacy_selection = evaluate_packet_with_legacy(packet)
    generic = evaluate_packet_with_generic(packet) if validation.is_full else None
    compared: dict[str, tuple[Any, Any]] = {}
    if validation.is_full and legacy_plan is not None and legacy_selection is not None and generic is not None:
        compared = {
            "trade_result": (TFISTradeResult.TRADE, generic.trade_result),
            "entry": (legacy_plan.entry_price, generic.entry_calculation.result if generic.entry_calculation else None),
            "target": (legacy_plan.target_price, generic.target_policy.result if generic.target_policy else None),
            "msl": (legacy_plan.stoploss_price, generic.msl_policy.result if generic.msl_policy else None),
            "selected_strike": (legacy_selection.strike, generic.selected_instrument.strike if generic.selected_instrument else None),
            "selected_premium_ltp": (legacy_selection.premium_used, generic.selected_instrument.metadata.get("ltp") if generic.selected_instrument else None),
            "selected_oi": (legacy_selection.oi_used, generic.selected_instrument.metadata.get("oi") if generic.selected_instrument else None),
            "direction": (TFISDirection.SHORT, generic.direction),
            "execution_side": (TFISExecutionSide.SELL, generic.execution_side),
        }
    mismatches = {key: value for key, value in compared.items() if _norm(value[0]) != _norm(value[1])}
    return DecisionPacketParityResult(
        packet_id=packet.identity.packet_id,
        completeness=validation.completeness,
        legacy_trade_result=TFISTradeResult.TRADE if legacy_plan is not None else TFISTradeResult.REJECTED,
        generic_trade_result=generic.trade_result if generic is not None else TFISTradeResult.REJECTED,
        compared_fields=compared,
        mismatches=mismatches,
    )


def option_chain_snapshot_from_packet(packet: TFISDecisionEvidencePacket) -> OptionChainSnapshotEvent:
    return OptionChainSnapshotEvent(
        envelope=EventEnvelope(
            event_type=PaperEventType.OPTION_CHAIN_SNAPSHOT,
            session_date=packet.identity.trading_date,
            effective_timestamp=packet.identity.event_timestamp,
            captured_at=packet.identity.processing_timestamp,
            timezone=packet.session.timezone,
            source_type="decision_evidence_packet",
            source_id=packet.identity.packet_id,
            synthetic_fixture=any(item is EvidenceProvenance.SYNTHETIC for item in packet.audit.evidence_classifications),
            normalized_by="phase2d1-packet",
        ),
        underlying_symbol=packet.instrument_product.underlying_identity.split(":")[-1],
        expiry=packet.instrument_product.expiry,
        contracts=tuple(
            OptionChainContract(
                symbol=item.contract_identity.symbol,
                option_type=item.option_type,
                strike=_float_value(item.strike),
                expiry=item.expiry,
                bid=_float_value(item.bid),
                ask=_float_value(item.ask),
                ltp=_float_value(item.ltp),
                oi=_float_value(item.oi),
            )
            for item in packet.option_chain.candidates
        ),
    )


def measure_decision_packet(packet: TFISDecisionEvidencePacket) -> DecisionPacketPerformance:
    start = perf_counter()
    serialized = packet.to_json()
    serialization_seconds = perf_counter() - start
    start = perf_counter()
    TFISDecisionEvidencePacket.from_json(serialized)
    deserialization_seconds = perf_counter() - start
    start = perf_counter()
    validate_decision_evidence_packet(packet)
    validation_seconds = perf_counter() - start
    start = perf_counter()
    run_decision_packet_parity(packet)
    parity_seconds = perf_counter() - start
    candidate_count = len(packet.option_chain.candidates)
    scale_risk = "LOW"
    if candidate_count > 500:
        scale_risk = "HIGH_OPTION_CHAIN_SIZE"
    elif candidate_count > 100:
        scale_risk = "MODERATE_OPTION_CHAIN_SIZE"
    return DecisionPacketPerformance(
        serialized_size_bytes=len(serialized.encode("utf-8")),
        serialization_seconds=serialization_seconds,
        deserialization_seconds=deserialization_seconds,
        validation_seconds=validation_seconds,
        parity_evaluation_seconds=parity_seconds,
        option_chain_candidate_count=candidate_count,
        scale_risk=scale_risk,
    )


def write_decision_packet_reports(
    packets: Iterable[TFISDecisionEvidencePacket],
    output_dir: str | Path,
) -> Mapping[str, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    packet_list = tuple(sorted(packets, key=lambda item: item.identity.packet_id))
    results = [run_decision_packet_parity(packet) for packet in packet_list]
    measurements = [measure_decision_packet(packet).to_dict() for packet in packet_list]
    data = {
        "generated_at": "2026-07-29T00:00:00+00:00",
        "packets": [packet.to_dict() for packet in packet_list],
        "validations": [
            {
                "packet_id": packet.identity.packet_id,
                "completeness": validate_decision_evidence_packet(packet).completeness.value,
                "issues": [
                    {
                        "code": issue.code,
                        "message": issue.message,
                        "field_name": issue.field_name,
                    }
                    for issue in validate_decision_evidence_packet(packet).issues
                ],
            }
            for packet in packet_list
        ],
        "parity": [
            {
                "packet_id": result.packet_id,
                "completeness": result.completeness.value,
                "passed": result.passed,
                "compared_fields": {key: [_json_value(left), _json_value(right)] for key, (left, right) in result.compared_fields.items()},
                "mismatches": {key: [_json_value(left), _json_value(right)] for key, (left, right) in result.mismatches.items()},
            }
            for result in results
        ],
        "performance": measurements,
    }
    json_path = directory / "decision_evidence_packet_report.json"
    md_path = directory / "decision_evidence_packet_summary.md"
    packet_path = directory / "s23_synthetic_golden_packet.json"
    json_path.write_text(json.dumps(data, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    golden_packet = next(
        (
            packet
            for packet in packet_list
            if packet.identity.packet_id.startswith("SYNTHETIC_GOLDEN:")
        ),
        packet_list[0],
    )
    packet_path.write_text(golden_packet.to_json() + "\n", encoding="utf-8")
    md_path.write_text(_packet_markdown(results, measurements), encoding="utf-8")
    return {"json": json_path, "markdown": md_path, "golden_packet": packet_path}


def _packet_markdown(results: Iterable[DecisionPacketParityResult], measurements: Iterable[Mapping[str, Any]]) -> str:
    lines = ["# Phase 2D.1 Decision Evidence Packet Report", ""]
    for result, measurement in zip(results, measurements):
        lines.append(f"## {result.packet_id}")
        lines.append("")
        lines.append(f"- completeness: {result.completeness.value}")
        lines.append(f"- parity_passed: {str(result.passed).lower()}")
        lines.append(f"- mismatches: {len(result.mismatches)}")
        lines.append(f"- serialized_size_bytes: {measurement['serialized_size_bytes']}")
        lines.append(f"- option_chain_candidate_count: {measurement['option_chain_candidate_count']}")
        lines.append(f"- scale_risk: {measurement['scale_risk']}")
        lines.append("")
    return "\n".join(lines)


def _strategy_rule_for_packet(packet: TFISDecisionEvidencePacket):
    branch = packet.identity.strategy_unique_code
    if branch.startswith("S21_"):
        return _strategy_rule("S21", branch)
    return _strategy_rule("S23", branch)


def _strategy_rule(strategy_code: str, branch: str):
    if strategy_code == "S21":
        return load_strategy_rule(ROOT / "config" / "strategies" / "options_sell" / "banknifty" / branch)
    folder = branch if branch.startswith("S23_") else f"S23_{branch}"
    return load_strategy_rule(ROOT / "config" / "strategies" / "options_sell" / "nifty" / folder)


def _market_levels(packet: TFISDecisionEvidencePacket) -> MarketLevels:
    return MarketLevels(
        d2hh=_float_value(packet.market_structure.prv_2d_hh),
        d2ll=_float_value(packet.market_structure.prv_2d_ll),
        d3hh=_float_value(packet.market_structure.prv_3d_hh),
        d3ll=_float_value(packet.market_structure.prv_3d_ll),
        d4hh=_float_value(packet.market_structure.prv_4d_hh),
        d4ll=_float_value(packet.market_structure.prv_4d_ll),
        current_day_high=_float_value(packet.market_structure.current_day_high),
        current_day_low=_float_value(packet.market_structure.current_day_low),
    )


def _market_structure_mapping(packet: TFISDecisionEvidencePacket) -> dict[str, float | None]:
    return {
        "d2hh": _float_value(packet.market_structure.prv_2d_hh),
        "d2ll": _float_value(packet.market_structure.prv_2d_ll),
        "d3hh": _float_value(packet.market_structure.prv_3d_hh),
        "d3ll": _float_value(packet.market_structure.prv_3d_ll),
        "d4hh": _float_value(packet.market_structure.prv_4d_hh),
        "d4ll": _float_value(packet.market_structure.prv_4d_ll),
        "current_day_high": _float_value(packet.market_structure.current_day_high),
        "current_day_low": _float_value(packet.market_structure.current_day_low),
    }


def _candidate(
    identity: TFISContractIdentity,
    *,
    option_type: OptionType | None,
    expiry: date | None,
    ltp: float | Decimal | None,
    bid: float | Decimal | None,
    ask: float | Decimal | None,
    oi: float | Decimal | None,
    quote_timestamp: datetime,
    provenance: EvidenceProvenance = EvidenceProvenance.SYNTHETIC,
) -> OptionChainCandidateEvidence:
    return OptionChainCandidateEvidence(
        contract_identity=identity,
        strike=_pv(identity.strike, provenance=provenance),
        option_type=option_type,
        expiry=expiry,
        ltp=_pv(ltp, provenance=provenance) if ltp is not None else _unavailable(),
        bid=_pv(bid, provenance=provenance) if bid is not None else _unavailable(),
        ask=_pv(ask, provenance=provenance) if ask is not None else _unavailable(),
        oi=_pv(oi, provenance=provenance) if oi is not None else _unavailable(),
        quote_timestamp=quote_timestamp,
        quality="VALID" if ltp is not None and oi is not None else "PARTIAL",
        freshness_seconds=Decimal("0"),
    )


def _pv(value: Any, *, provenance: EvidenceProvenance = EvidenceProvenance.SYNTHETIC) -> ProvenancedValue:
    if value is None:
        return _unavailable()
    return ProvenancedValue(
        value=Decimal(str(value)),
        availability=EvidenceAvailability.AVAILABLE,
        provenance=provenance,
        source=provenance.value.lower(),
    )


def _unavailable() -> ProvenancedValue:
    return ProvenancedValue(
        value=None,
        availability=EvidenceAvailability.UNAVAILABLE,
        provenance=EvidenceProvenance.NOT_APPLICABLE,
        source=None,
    )


def _na() -> ProvenancedValue:
    return _not_applicable()


def _not_applicable() -> ProvenancedValue:
    return ProvenancedValue(
        value=None,
        availability=EvidenceAvailability.NOT_APPLICABLE,
        provenance=EvidenceProvenance.NOT_APPLICABLE,
        source=None,
    )


def _float_value(value: ProvenancedValue) -> float | None:
    if value.value is None:
        return None
    return float(value.value)


def _int_value(value: ProvenancedValue) -> int | None:
    if value.value is None:
        return None
    return int(value.value)


def _norm(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    return value


def _json_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    return value
