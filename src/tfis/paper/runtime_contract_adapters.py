from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from typing import Any

from tfis.domain import (
    Segment,
    StrategyRule,
    TFISContractIdentity,
    TFISDecision,
    TFISDirection,
    TFISExecutionSide,
    TFISFormulaTrace,
    TFISOptionChainContext,
    TFISPolicyResult,
    TFISProductType,
    TFISRuntimeInput,
    TFISTradeResult,
    product_type_from_segment,
)

from .live_decision import S23PaperLiveDecisionResult, S23PaperTradeDecisionSummary
from .runtime_input_derivation import (
    PaperDecisionReferencePacket,
    PaperMarketReferencePacket,
    PaperMonthlyStatusReferencePacket,
)


class PaperRuntimeContractAdapterError(ValueError):
    """Raised by strict generic runtime-contract adapter paths."""


def runtime_input_from_decision_reference_packet(
    *,
    strategy_rule: StrategyRule,
    reference_packet: PaperDecisionReferencePacket,
    evaluation_id: str | None = None,
    evaluated_at: datetime | None = None,
    account_id: str | None = None,
    session_date: date | None = None,
    session_label: str | None = None,
    timezone: str = "Asia/Calcutta",
    price_source: str | None = None,
    cmp: float | None = None,
    configuration_version: str | None = None,
) -> TFISRuntimeInput:
    timestamp = evaluated_at or datetime.now()
    product_type = product_type_from_segment(strategy_rule.segment)
    monthly_levels = reference_packet.monthly_status_levels
    market_levels = reference_packet.market_reference_levels
    option_values = dict(reference_packet.option_reference_values)
    runtime_overrides = dict(reference_packet.runtime_value_overrides or {})
    runtime_values = {**option_values, **runtime_overrides}
    return TFISRuntimeInput(
        evaluation_id=evaluation_id or _default_evaluation_id(strategy_rule, timestamp),
        evaluated_at=timestamp,
        strategy_code=strategy_rule.strategy_code,
        strategy_version=configuration_version,
        strategy_branch=reference_packet.strategy_branch or strategy_rule.unique_code,
        symbol=strategy_rule.symbol,
        segment=strategy_rule.segment,
        product_type=product_type,
        account_id=account_id,
        lots=reference_packet.lots,
        quantity=reference_packet.quantity,
        session_date=session_date or reference_packet.monthly_status_reference_date or timestamp.date(),
        session_label=session_label,
        timezone=timezone,
        price_source=price_source,
        cmp=cmp,
        contract=None,
        monthly_status=None,
        monthly_status_evidence={
            "instrument_group": reference_packet.instrument_group,
            "levels": asdict(monthly_levels),
            "source": reference_packet.monthly_status_source,
            "threshold_version": reference_packet.monthly_status_threshold_version,
            "reference_date": reference_packet.monthly_status_reference_date,
        },
        market_structure_references=asdict(market_levels),
        current_week_references={
            "CWH": monthly_levels.CWH,
            "CWL": monthly_levels.CWL,
            "PWH": monthly_levels.PWH,
            "PWL": monthly_levels.PWL,
        },
        current_month_references={
            "CMH": monthly_levels.CMH,
            "CML": monthly_levels.CML,
            "PMH": monthly_levels.PMH,
            "PML": monthly_levels.PML,
        },
        gap_context={
            "strategy_branch": reference_packet.strategy_branch or strategy_rule.unique_code,
            "runtime_value_overrides": runtime_overrides,
        },
        option_chain_context=(
            TFISOptionChainContext(reference_values=option_values)
            if product_type
            in {TFISProductType.OPTION_BUYING, TFISProductType.OPTION_SELLING}
            else None
        ),
        data_quality={
            "reference_packet_present": True,
            "option_reference_value_count": len(option_values),
            "market_reference_value_count": len(asdict(market_levels)),
        },
        provenance={
            "source_workbook_rule": reference_packet.source_workbook_rule,
            "workbook_row_number": reference_packet.workbook_row_number,
            "adapter": "paper_runtime_contract_adapters.runtime_input_from_decision_reference_packet",
        },
        configuration_snapshot={
            "strategy_rule": {
                "strategy_code": strategy_rule.strategy_code,
                "unique_code": strategy_rule.unique_code,
                "symbol": strategy_rule.symbol,
                "segment": strategy_rule.segment.value,
                "parameters": dict(strategy_rule.parameters or {}),
                "entry_formula": strategy_rule.entry_formula,
                "target_formula": strategy_rule.target_formula,
                "stoploss_formula": strategy_rule.stoploss_formula,
            }
        },
        configuration_version=configuration_version,
        runtime_values=runtime_values,
        product_specific={
            "fsl_price": reference_packet.fsl_price,
            "source_workbook_rule": reference_packet.source_workbook_rule,
            "workbook_row_number": reference_packet.workbook_row_number,
        },
    )


def runtime_input_from_decision_reference_packet_strict(
    *,
    strategy_rule: StrategyRule,
    reference_packet: PaperDecisionReferencePacket,
    evaluation_id: str | None = None,
    evaluated_at: datetime | None = None,
    account_id: str | None = None,
    session_date: date | None = None,
    session_label: str | None = None,
    timezone: str = "Asia/Calcutta",
    price_source: str | None = None,
    cmp: float | None = None,
    configuration_version: str | None = None,
) -> TFISRuntimeInput:
    _validate_reference_packet_strategy_identity(
        strategy_rule=strategy_rule,
        reference_packet=reference_packet,
    )
    return runtime_input_from_decision_reference_packet(
        strategy_rule=strategy_rule,
        reference_packet=reference_packet,
        evaluation_id=evaluation_id,
        evaluated_at=evaluated_at,
        account_id=account_id,
        session_date=session_date,
        session_label=session_label,
        timezone=timezone,
        price_source=price_source,
        cmp=cmp,
        configuration_version=configuration_version,
    )


def legacy_reference_packet_from_runtime_input(
    runtime_input: TFISRuntimeInput,
) -> PaperDecisionReferencePacket:
    monthly_levels = dict(runtime_input.monthly_status_evidence.get("levels") or {})
    product_specific = dict(runtime_input.product_specific)
    option_context = runtime_input.option_chain_context
    option_values = (
        dict(option_context.reference_values)
        if option_context is not None
        else {
            key: value
            for key, value in runtime_input.runtime_values.items()
            if str(key).upper().startswith("OPT_")
        }
    )
    runtime_overrides = dict(runtime_input.gap_context.get("runtime_value_overrides") or {})
    reference_date = runtime_input.monthly_status_evidence.get("reference_date")
    if isinstance(reference_date, str):
        reference_date = date.fromisoformat(reference_date)
    return PaperDecisionReferencePacket(
        instrument_group=str(
            runtime_input.monthly_status_evidence.get("instrument_group")
            or runtime_input.symbol
        ),
        monthly_status_levels=PaperMonthlyStatusReferencePacket(
            PMH=float(monthly_levels["PMH"]),
            PML=float(monthly_levels["PML"]),
            CMH=float(monthly_levels["CMH"]),
            CML=float(monthly_levels["CML"]),
            PWH=float(monthly_levels["PWH"]),
            PWL=float(monthly_levels["PWL"]),
            CWH=float(monthly_levels["CWH"]),
            CWL=float(monthly_levels["CWL"]),
        ),
        market_reference_levels=PaperMarketReferencePacket(
            d2hh=_optional_float(runtime_input.market_structure_references.get("d2hh")),
            d2ll=_optional_float(runtime_input.market_structure_references.get("d2ll")),
            d3hh=_optional_float(runtime_input.market_structure_references.get("d3hh")),
            d3ll=_optional_float(runtime_input.market_structure_references.get("d3ll")),
            d4hh=_optional_float(runtime_input.market_structure_references.get("d4hh")),
            d4ll=_optional_float(runtime_input.market_structure_references.get("d4ll")),
        ),
        option_reference_values={
            str(key).upper(): float(value) for key, value in option_values.items()
        },
        lots=int(runtime_input.lots or 0),
        quantity=int(runtime_input.quantity or 0),
        strategy_branch=runtime_input.strategy_branch,
        source_workbook_rule=_optional_text(product_specific.get("source_workbook_rule")),
        workbook_row_number=_optional_int(product_specific.get("workbook_row_number")),
        fsl_price=_optional_float(product_specific.get("fsl_price")),
        monthly_status_source=str(
            runtime_input.monthly_status_evidence.get("source") or "tfis_reference_packet"
        ),
        monthly_status_threshold_version=str(
            runtime_input.monthly_status_evidence.get("threshold_version") or "v1"
        ),
        runtime_value_overrides=runtime_overrides or None,
        monthly_status_reference_date=reference_date if isinstance(reference_date, date) else None,
    )


def decision_from_live_decision_result(
    *,
    result: S23PaperLiveDecisionResult,
    strategy_rule: StrategyRule | None = None,
    evaluation_id: str | None = None,
    decision_id: str | None = None,
    decided_at: datetime | None = None,
) -> TFISDecision:
    return decision_from_trade_decision_summary(
        summary=result.summary,
        strategy_rule=strategy_rule,
        evaluation_id=evaluation_id,
        decision_id=decision_id,
        decided_at=decided_at,
        explanation=result.explanation,
        compatibility_payload=result.to_dict(),
    )


def decision_from_trade_decision_summary(
    *,
    summary: S23PaperTradeDecisionSummary,
    strategy_rule: StrategyRule | None = None,
    evaluation_id: str | None = None,
    decision_id: str | None = None,
    decided_at: datetime | None = None,
    explanation: dict[str, Any] | None = None,
    compatibility_payload: dict[str, Any] | None = None,
) -> TFISDecision:
    timestamp = decided_at or datetime.combine(summary.session_date, datetime.min.time())
    product_type = (
        product_type_from_segment(strategy_rule.segment)
        if strategy_rule is not None
        else TFISProductType.OPTION_SELLING
    )
    selected_instrument = _selected_instrument(summary, product_type)
    trade_result = _trade_result(summary)
    rejection_code = summary.contract_selection_failure_code or summary.order_placement_block_reason
    formula_traces = _formula_traces(explanation)
    entry_trace = formula_traces.get("entry") or TFISFormulaTrace(
        name="entry",
        result=summary.planned_entry_price,
        evidence={"source": "decision_summary"},
    )
    return TFISDecision(
        evaluation_id=evaluation_id or f"{summary.strategy_code}:{summary.session_date.isoformat()}",
        decision_id=decision_id or f"{summary.strategy_code}:{summary.strategy_branch}:{summary.status}",
        decided_at=timestamp,
        strategy_code=summary.strategy_code,
        strategy_branch=summary.strategy_branch,
        monthly_status_branch=summary.monthly_status,
        trade_result=trade_result,
        product_type=product_type,
        direction=TFISDirection.SHORT if selected_instrument is not None else None,
        execution_side=TFISExecutionSide.SELL if selected_instrument is not None else None,
        selected_instrument=selected_instrument,
        entry_calculation=entry_trace,
        gap_result=dict((explanation or {}).get("orpt_rc_timing") or {}),
        missed_entry_result=dict((explanation or {}).get("orpt_rc_timing") or {}),
        lots=summary.lots,
        quantity=summary.quantity,
        target_policy=TFISPolicyResult(
            policy_name="target",
            result=summary.target_price,
            formula_trace=formula_traces.get("target"),
        ),
        msl_policy=TFISPolicyResult(
            policy_name="msl",
            result=summary.stoploss_price,
            formula_trace=formula_traces.get("stoploss"),
            evidence={"fsl_price": summary.fsl_price},
        ),
        tsl_policy=TFISPolicyResult(policy_name="tsl", result=None),
        aps_policy=TFISPolicyResult(policy_name="aps", result=None),
        final_exit_rule={
            "governance_event_types": summary.governance_event_types,
            "resume_event_type": summary.resume_event_type,
        },
        rejection_reason_code=rejection_code,
        rejection_reason=summary.order_placement_block_reason
        or summary.contract_selection_reason,
        intermediate_calculation_evidence={
            "market_levels": summary.market_levels,
            "runtime_values": summary.runtime_values,
            "required_market_aliases": summary.required_market_aliases,
            "required_option_aliases": summary.required_option_aliases,
            "checkpoint_labels": summary.checkpoint_labels,
            "ranked_candidates": summary.ranked_candidates,
            "rejected_candidate_counts": summary.rejected_candidate_counts,
            "formula_traces": {key: value.to_dict() for key, value in formula_traces.items()},
        },
        data_versions={
            "monthly_status_trigger": summary.monthly_status_trigger,
            "monthly_status_notes": summary.monthly_status_notes,
        },
        configuration_versions={
            "source_workbook_rule": summary.source_workbook_rule,
            "workbook_row_number": summary.workbook_row_number,
        },
        compatibility_payload=compatibility_payload or {"summary": asdict(summary)},
    )


def decision_from_trade_decision_summary_strict(
    *,
    summary: S23PaperTradeDecisionSummary,
    product_type: TFISProductType,
    direction: TFISDirection,
    execution_side: TFISExecutionSide,
    selected_instrument_segment: Segment,
    strategy_rule: StrategyRule | None = None,
    expected_strategy_code: str | None = None,
    expected_strategy_branch: str | None = None,
    evaluation_id: str | None = None,
    decision_id: str | None = None,
    decided_at: datetime | None = None,
    explanation: dict[str, Any] | None = None,
    compatibility_payload: dict[str, Any] | None = None,
) -> TFISDecision:
    _validate_summary_strategy_identity(
        summary=summary,
        strategy_rule=strategy_rule,
        expected_strategy_code=expected_strategy_code,
        expected_strategy_branch=expected_strategy_branch,
    )
    expected_product_type = product_type_from_segment(selected_instrument_segment)
    if expected_product_type is not product_type:
        raise PaperRuntimeContractAdapterError(
            "selected_instrument_segment does not match explicit product_type"
        )
    timestamp = decided_at or datetime.combine(summary.session_date, datetime.min.time())
    selected_instrument = _selected_instrument(
        summary,
        product_type,
        segment=selected_instrument_segment,
    )
    trade_result = _trade_result(summary)
    rejection_code = summary.contract_selection_failure_code or summary.order_placement_block_reason
    formula_traces = _formula_traces(explanation)
    entry_trace = formula_traces.get("entry") or TFISFormulaTrace(
        name="entry",
        result=summary.planned_entry_price,
        evidence={"source": "decision_summary"},
    )
    successful = trade_result in {TFISTradeResult.TRADE, TFISTradeResult.CARRY_FORWARD}
    selection_evidence = {
        "selection_reason": summary.contract_selection_reason,
        "contract_selection_failure_code": summary.contract_selection_failure_code,
        "order_placement_block_reason": summary.order_placement_block_reason,
    }
    return TFISDecision(
        evaluation_id=evaluation_id or f"{summary.strategy_code}:{summary.session_date.isoformat()}",
        decision_id=decision_id or f"{summary.strategy_code}:{summary.strategy_branch}:{summary.status}",
        decided_at=timestamp,
        strategy_code=summary.strategy_code,
        strategy_branch=summary.strategy_branch,
        monthly_status_branch=summary.monthly_status,
        trade_result=trade_result,
        product_type=product_type,
        direction=direction if selected_instrument is not None else None,
        execution_side=execution_side if selected_instrument is not None else None,
        selected_instrument=selected_instrument,
        entry_calculation=entry_trace,
        gap_result=dict((explanation or {}).get("orpt_rc_timing") or {}),
        missed_entry_result=dict((explanation or {}).get("orpt_rc_timing") or {}),
        lots=summary.lots,
        quantity=summary.quantity,
        target_policy=TFISPolicyResult(
            policy_name="target",
            result=summary.target_price,
            formula_trace=formula_traces.get("target"),
        ),
        msl_policy=TFISPolicyResult(
            policy_name="msl",
            result=summary.stoploss_price,
            formula_trace=formula_traces.get("stoploss"),
            evidence={"fsl_price": summary.fsl_price},
        ),
        tsl_policy=TFISPolicyResult(policy_name="tsl", result=None),
        aps_policy=TFISPolicyResult(policy_name="aps", result=None),
        final_exit_rule={
            "governance_event_types": summary.governance_event_types,
            "resume_event_type": summary.resume_event_type,
        },
        rejection_reason_code=None if successful else rejection_code,
        rejection_reason=(
            None
            if successful
            else summary.order_placement_block_reason
            or summary.contract_selection_reason
        ),
        intermediate_calculation_evidence={
            "market_levels": summary.market_levels,
            "runtime_values": summary.runtime_values,
            "required_market_aliases": summary.required_market_aliases,
            "required_option_aliases": summary.required_option_aliases,
            "checkpoint_labels": summary.checkpoint_labels,
            "ranked_candidates": summary.ranked_candidates,
            "rejected_candidate_counts": summary.rejected_candidate_counts,
            "selection": selection_evidence,
            "formula_traces": {key: value.to_dict() for key, value in formula_traces.items()},
        },
        data_versions={
            "monthly_status_trigger": summary.monthly_status_trigger,
            "monthly_status_notes": summary.monthly_status_notes,
        },
        configuration_versions={
            "source_workbook_rule": summary.source_workbook_rule,
            "workbook_row_number": summary.workbook_row_number,
        },
        compatibility_payload=compatibility_payload or {"summary": asdict(summary)},
    )


def _selected_instrument(
    summary: S23PaperTradeDecisionSummary,
    product_type: TFISProductType,
    *,
    segment: Segment | None = None,
) -> TFISContractIdentity | None:
    if summary.selected_contract_symbol is None:
        return None
    expiry = (
        date.fromisoformat(summary.selected_contract_expiry)
        if summary.selected_contract_expiry
        else None
    )
    return TFISContractIdentity(
        symbol=summary.selected_contract_symbol,
        segment=segment,
        product_type=product_type,
        expiry=expiry,
        strike=summary.selected_contract_strike,
        option_type=summary.selected_contract_option_type,
        metadata={
            "ltp": summary.selected_contract_ltp,
            "oi": summary.selected_contract_oi,
            "selection_reason": summary.contract_selection_reason,
        },
    )


def _trade_result(summary: S23PaperTradeDecisionSummary) -> TFISTradeResult:
    if summary.status == "READY" and summary.mode.upper() == "CARRY_FORWARD_RESUME":
        return TFISTradeResult.CARRY_FORWARD
    if summary.status == "READY":
        return TFISTradeResult.TRADE
    if summary.order_placement_blocked or summary.contract_selection_failure_code:
        return TFISTradeResult.REJECTED
    if summary.status == "NO_GO":
        return TFISTradeResult.NO_TRADE
    return TFISTradeResult.UNKNOWN


def _formula_traces(explanation: dict[str, Any] | None) -> dict[str, TFISFormulaTrace]:
    traces: dict[str, TFISFormulaTrace] = {}
    for item in (explanation or {}).get("formulas", ()) or ():
        name = str(item.get("name") or "")
        if not name:
            continue
        traces[name] = TFISFormulaTrace(
            name=name,
            formula=item.get("formula"),
            resolved_formula=item.get("resolved_formula"),
            result=item.get("result"),
            evidence=dict(item),
        )
    return traces


def _default_evaluation_id(strategy_rule: StrategyRule, evaluated_at: datetime) -> str:
    return f"{strategy_rule.strategy_code}:{strategy_rule.unique_code}:{evaluated_at.isoformat()}"


def _validate_reference_packet_strategy_identity(
    *,
    strategy_rule: StrategyRule,
    reference_packet: PaperDecisionReferencePacket,
) -> None:
    packet_branch = _optional_text(reference_packet.strategy_branch)
    if packet_branch is not None and packet_branch != strategy_rule.unique_code:
        raise PaperRuntimeContractAdapterError(
            "reference_packet.strategy_branch does not match strategy_rule.unique_code"
        )


def _validate_summary_strategy_identity(
    *,
    summary: S23PaperTradeDecisionSummary,
    strategy_rule: StrategyRule | None,
    expected_strategy_code: str | None,
    expected_strategy_branch: str | None,
) -> None:
    expected_code = expected_strategy_code or (
        strategy_rule.strategy_code if strategy_rule is not None else None
    )
    expected_branch = expected_strategy_branch or (
        strategy_rule.unique_code if strategy_rule is not None else None
    )
    if expected_code is not None and summary.strategy_code != expected_code:
        raise PaperRuntimeContractAdapterError(
            "summary.strategy_code does not match expected strategy code"
        )
    if expected_branch is not None and summary.strategy_branch != expected_branch:
        raise PaperRuntimeContractAdapterError(
            "summary.strategy_branch does not match expected strategy branch"
        )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
