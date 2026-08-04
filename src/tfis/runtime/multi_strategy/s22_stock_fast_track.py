from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping

from tfis.execution_intent.pricing import normalize_executable_price
from tfis.fyers_read_only import FyersReadOnlyAdapter, FyersReadOnlyStatus
from tfis.persistence import canonical_hash
from tfis.runtime.multi_strategy.live_contract_selection import HistoricalContractSelectionResult
from tfis.runtime.multi_strategy.registry import EnabledStrategyInstance


RULE_MATRIX_VERSION = "s22_source_closure_accepted_v1"
ENTRY_RULE_ID = "S22.ENTRY_ORPT_RC.001"
CONTRACT_RULE_ID = "S22.CONTRACT_SELECTION.001"
TARGET_SL_RULE_ID = "S22.TARGET_SL.001"
MONTHLY_STATUS_RULE_ID = "MONTHLY_STATUS.GENERIC.ENGINE.001"
IST_ORPT = time(9, 24, 59, 400000)
IST_RC = time(9, 29, 59, 400000)


@dataclass(frozen=True, slots=True)
class S22BranchPlanSpec:
    branch_id: str
    monthly_statuses: tuple[str, ...]
    option_type: str
    source_cells: tuple[str, ...]
    workbook_row_id: str
    base_entry_reference: str
    base_entry_discount_pct: Decimal
    target_discount_pct: Decimal
    original_sl_reference: str
    original_sl_reference_pct: Decimal
    original_sl_entry_pct: Decimal
    revised_entry_reference: str
    revised_entry_operator: str
    revised_sl_pct: Decimal
    base_entry_formula: str
    target_formula: str
    original_sl_formula: str
    revised_entry_formula: str
    revised_sl_formula: str


BRANCH_SPECS: dict[str, S22BranchPlanSpec] = {
    "BULL_CALL": S22BranchPlanSpec(
        branch_id="BULL_CALL",
        monthly_statuses=("BULL", "BULL_CF"),
        option_type="CALL",
        source_cells=("AB6 OS!D131:M132", "AB14!F42:BG42"),
        workbook_row_id="S22A",
        base_entry_reference="OPT_PRV_4DLL",
        base_entry_discount_pct=Decimal("10"),
        target_discount_pct=Decimal("60"),
        original_sl_reference="OPT_PRV_2DHH",
        original_sl_reference_pct=Decimal("7"),
        original_sl_entry_pct=Decimal("60"),
        revised_entry_reference="OPT_PRV_4DLL",
        revised_entry_operator="MIN",
        revised_sl_pct=Decimal("7"),
        base_entry_formula="OPT:PRV:4DLL - 10%",
        target_formula="CE Entry - 60%",
        original_sl_formula="Min(CE Entry + 60%, OPT:PRV:2DHH + 7%)",
        revised_entry_formula="Min(SPT:PRV:4DLL, 09:29:59 AM LL) with branch strike/premium/entry recalculation",
        revised_sl_formula="09:29:59 AM HH + 7%",
    ),
    "BULL_PUT": S22BranchPlanSpec(
        branch_id="BULL_PUT",
        monthly_statuses=("BULL", "BULL_CF"),
        option_type="PUT",
        source_cells=("AB6 OS!F134:M135", "AB14!G43:BG43"),
        workbook_row_id="S22B",
        base_entry_reference="OPT_PRV_2DLL",
        base_entry_discount_pct=Decimal("10"),
        target_discount_pct=Decimal("60"),
        original_sl_reference="OPT_PRV_3DHH",
        original_sl_reference_pct=Decimal("10"),
        original_sl_entry_pct=Decimal("60"),
        revised_entry_reference="OPT_PRV_2DHH",
        revised_entry_operator="MAX",
        revised_sl_pct=Decimal("10"),
        base_entry_formula="OPT:PRV:2DLL - 10%",
        target_formula="PE Entry - 60%",
        original_sl_formula="Min(PE Entry + 60%, OPT:PRV:3DHH + 10%)",
        revised_entry_formula="Max(SPT:PRV:2DHH, 09:29:59 AM LL) with branch strike/premium/entry recalculation",
        revised_sl_formula="09:29:59 AM HH + 10%",
    ),
    "BEAR_CALL": S22BranchPlanSpec(
        branch_id="BEAR_CALL",
        monthly_statuses=("BEAR", "BEAR_CF"),
        option_type="CALL",
        source_cells=("AB6 OS!D137:M138", "AB14!F45:BG45"),
        workbook_row_id="S22D",
        base_entry_reference="OPT_PRV_2DLL",
        base_entry_discount_pct=Decimal("10"),
        target_discount_pct=Decimal("60"),
        original_sl_reference="OPT_PRV_3DHH",
        original_sl_reference_pct=Decimal("10"),
        original_sl_entry_pct=Decimal("60"),
        revised_entry_reference="OPT_PRV_2DLL",
        revised_entry_operator="MIN",
        revised_sl_pct=Decimal("10"),
        base_entry_formula="OPT:PRV:2DLL - 10%",
        target_formula="CE Entry - 60%",
        original_sl_formula="Min(CE Entry + 60%, OPT:PRV:3DHH + 10%)",
        revised_entry_formula="Min(SPT:PRV:2DLL, 09:29:59 AM LL) with branch strike/premium/entry recalculation",
        revised_sl_formula="09:29:59 AM HH + 10%",
    ),
    "BEAR_PUT": S22BranchPlanSpec(
        branch_id="BEAR_PUT",
        monthly_statuses=("BEAR", "BEAR_CF"),
        option_type="PUT",
        source_cells=("AB6 OS!F140:M141", "AB14!G46:BG46"),
        workbook_row_id="S22E",
        base_entry_reference="OPT_PRV_4DLL",
        base_entry_discount_pct=Decimal("10"),
        target_discount_pct=Decimal("60"),
        original_sl_reference="OPT_PRV_2DHH",
        original_sl_reference_pct=Decimal("7"),
        original_sl_entry_pct=Decimal("60"),
        revised_entry_reference="OPT_PRV_4DHH",
        revised_entry_operator="MAX",
        revised_sl_pct=Decimal("7"),
        base_entry_formula="OPT:PRV:4DLL - 10%",
        target_formula="PE Entry - 60%",
        original_sl_formula="Min(PE Entry + 60%, OPT:PRV:2DHH + 7%)",
        revised_entry_formula="Max(SPT:PRV:4DHH, 09:29:59 AM LL) with branch strike/premium/entry recalculation",
        revised_sl_formula="09:29:59 AM HH + 7%",
    ),
}


def build_s22_stock_historical_selection(
    *,
    repo_root: Path,
    instance: EnabledStrategyInstance,
    adapter: FyersReadOnlyAdapter,
    session_date: date,
    now: datetime,
) -> HistoricalContractSelectionResult:
    selection_report = _load_symbol_selection(repo_root=repo_root, symbol=instance.symbol)
    selected_contract = selection_report.get("selected_contract")
    selected_branch = str(selection_report.get("selected_branch") or "")
    monthly_status = str(selection_report.get("monthly_status") or "")
    if not isinstance(selected_contract, Mapping) or not selected_branch:
        return HistoricalContractSelectionResult(
            status="BLOCKED_CHAIN_STATE_NOT_RECOVERABLE",
            evidence="S22_ACTUAL_CHAIN_SELECTION_UNAVAILABLE",
            recovery_mode="HISTORICAL_RECONSTRUCTION_BLOCKED",
            strategy_instance_id=instance.strategy_instance_id,
            selected_contract=None,
            selected_branch=selected_branch or None,
            selected_option_type=None,
            selected_expiry=None,
            selected_strike=None,
            entry=None,
            target=None,
            original_sl=None,
            monthly_status=monthly_status or None,
            quote=None,
            option_history_status=None,
            candidate_count=0,
            rejected_candidates=(),
            plan_payload={
                "strategy_instance_id": instance.strategy_instance_id,
                "selection_source": "S22_ACTUAL_CHAIN_REPORT_MISSING",
            },
            unresolved_gap="S22_ACTUAL_CHAIN_SELECTION_UNAVAILABLE",
        )

    branch_spec = BRANCH_SPECS.get(selected_branch)
    if branch_spec is None:
        return HistoricalContractSelectionResult(
            status="BLOCKED_CHAIN_STATE_NOT_RECOVERABLE",
            evidence="S22_BRANCH_UNSUPPORTED",
            recovery_mode="HISTORICAL_RECONSTRUCTION_BLOCKED",
            strategy_instance_id=instance.strategy_instance_id,
            selected_contract=None,
            selected_branch=selected_branch,
            selected_option_type=str(selected_contract.get("option_type") or ""),
            selected_expiry=str(selected_contract.get("expiry") or ""),
            selected_strike=str(selected_contract.get("strike") or ""),
            entry=None,
            target=None,
            original_sl=None,
            monthly_status=monthly_status or None,
            quote=None,
            option_history_status=None,
            candidate_count=0,
            rejected_candidates=(),
            plan_payload={
                "strategy_instance_id": instance.strategy_instance_id,
                "selection_source": "S22_BRANCH_UNSUPPORTED",
                "selected_branch": selected_branch,
            },
            unresolved_gap=f"UNSUPPORTED_BRANCH:{selected_branch}",
        )

    underlying_history = adapter.fetch_historical_candles(
        symbol=f"NSE:{instance.symbol}-EQ",
        resolution="D",
        range_from=session_date - date.resolution * 90,
        range_to=session_date,
        exclude_incomplete_after=now,
    )
    option_daily_history = adapter.fetch_historical_candles(
        symbol=str(selected_contract["symbol"]),
        resolution="D",
        range_from=session_date - date.resolution * 45,
        range_to=session_date,
        exclude_incomplete_after=now,
    )
    quote_result = adapter.fetch_quotes((str(selected_contract["symbol"]),))

    if underlying_history.status is not FyersReadOnlyStatus.SUCCESS:
        return _history_blocked(instance, selected_contract, selected_branch, monthly_status, "UNDERLYING_HISTORY_UNAVAILABLE", underlying_history.status.value)
    if option_daily_history.status is not FyersReadOnlyStatus.SUCCESS:
        return _history_blocked(instance, selected_contract, selected_branch, monthly_status, "SELECTED_OPTION_HISTORY_UNAVAILABLE", option_daily_history.status.value)

    underlying_refs = _underlying_references(underlying_history.payload.candles)
    option_refs = _selected_option_references(option_daily_history.payload.candles)
    raw_values = _plan_values(branch_spec=branch_spec, option_refs=option_refs)
    normalized_values = {
        key: normalize_executable_price(value, Decimal(str(selected_contract.get("tick_size") or "0.05")))
        for key, value in raw_values.items()
    }
    quote_payload = _quote_payload(quote_result=quote_result, now=now)
    plan_payload = {
        "schema_version": "tfis.s22_stock_fast_track_plan.v1",
        "strategy_instance_id": instance.strategy_instance_id,
        "strategy_definition_id": instance.strategy_definition_id,
        "rule_matrix_version": RULE_MATRIX_VERSION,
        "monthly_status_rule_id": MONTHLY_STATUS_RULE_ID,
        "contract_selection_rule_id": CONTRACT_RULE_ID,
        "entry_rule_id": ENTRY_RULE_ID,
        "target_sl_rule_id": TARGET_SL_RULE_ID,
        "symbol": instance.symbol,
        "monthly_status": monthly_status,
        "selected_branch": selected_branch,
        "selected_contract": dict(selected_contract),
        "source_cells": list(branch_spec.source_cells),
        "workbook_row_id": branch_spec.workbook_row_id,
        "formula_catalog": {
            "base_entry": branch_spec.base_entry_formula,
            "target": branch_spec.target_formula,
            "original_sl": branch_spec.original_sl_formula,
            "revised_entry": branch_spec.revised_entry_formula,
            "revised_sl": branch_spec.revised_sl_formula,
        },
        "market_references": {key: str(value) for key, value in underlying_refs.items()},
        "selected_option_references": {key: str(value) for key, value in option_refs.items()},
        "raw_prices": {key: str(value) for key, value in raw_values.items()},
        "normalized_prices": {key: str(value) for key, value in normalized_values.items()},
        "orpt_time": IST_ORPT.isoformat(),
        "rc_time": IST_RC.isoformat(),
        "selection_source": "ACTUAL_CHAIN_REPORT_PLUS_FYERS_HISTORY",
        "selection_report_path": str((repo_root / "reports" / "contract_selection" / "actual_strike_set_contract.json").resolve()),
        "evaluated_contracts": [dict(selected_contract)],
        "rejected_candidates": list(_load_rejections(repo_root=repo_root, symbol=instance.symbol)),
        "candidate_count": _candidate_count(repo_root=repo_root, symbol=instance.symbol),
        "quote": quote_payload,
        "evidence_origin": {
            "contract_selection": "ACTUAL_LISTED_CHAIN_SELECTOR",
            "underlying_history": "FYERS_READ_ONLY_DAILY_HISTORY",
            "selected_option_history": "FYERS_READ_ONLY_DAILY_HISTORY",
            "current_quote": "FYERS_READ_ONLY_QUOTES",
            "historical_reconstruction": "OPTION_INTRADAY_HISTORY_TO_BE_EVALUATED_SEPARATELY",
        },
        "current_eligibility": "PENDING_INTRADAY_RECONSTRUCTION",
    }
    plan_payload["plan_hash"] = canonical_hash({k: v for k, v in plan_payload.items() if k != "plan_hash"})

    return HistoricalContractSelectionResult(
        status="SELECTED_CONTRACT_RECONSTRUCTED",
        evidence="ACTUAL_CHAIN_REPORT_PLUS_FYERS_HISTORY",
        recovery_mode="HISTORICALLY_RECONSTRUCTED",
        strategy_instance_id=instance.strategy_instance_id,
        selected_contract=str(selected_contract["symbol"]),
        selected_branch=selected_branch,
        selected_option_type=str(selected_contract.get("option_type") or ""),
        selected_expiry=str(selected_contract.get("expiry") or ""),
        selected_strike=str(selected_contract.get("strike") or ""),
        entry=str(normalized_values["base_entry"]),
        target=str(normalized_values["target"]),
        original_sl=str(normalized_values["original_sl"]),
        monthly_status=monthly_status,
        quote=quote_payload,
        option_history_status=option_daily_history.status.value,
        candidate_count=_candidate_count(repo_root=repo_root, symbol=instance.symbol),
        rejected_candidates=tuple(_load_rejections(repo_root=repo_root, symbol=instance.symbol)),
        plan_payload=plan_payload,
        unresolved_gap=None,
    )


def _history_blocked(
    instance: EnabledStrategyInstance,
    selected_contract: Mapping[str, Any],
    selected_branch: str,
    monthly_status: str,
    gap: str,
    status: str,
) -> HistoricalContractSelectionResult:
    return HistoricalContractSelectionResult(
        status="BLOCKED_CHAIN_STATE_NOT_RECOVERABLE",
        evidence="S22_HISTORY_UNAVAILABLE",
        recovery_mode="HISTORICAL_RECONSTRUCTION_BLOCKED",
        strategy_instance_id=instance.strategy_instance_id,
        selected_contract=str(selected_contract.get("symbol") or ""),
        selected_branch=selected_branch,
        selected_option_type=str(selected_contract.get("option_type") or ""),
        selected_expiry=str(selected_contract.get("expiry") or ""),
        selected_strike=str(selected_contract.get("strike") or ""),
        entry=None,
        target=None,
        original_sl=None,
        monthly_status=monthly_status or None,
        quote=None,
        option_history_status=status,
        candidate_count=0,
        rejected_candidates=(),
        plan_payload={
            "strategy_instance_id": instance.strategy_instance_id,
            "selection_source": "S22_HISTORY_UNAVAILABLE",
            "status": status,
        },
        unresolved_gap=gap,
    )


def _candidate_count(*, repo_root: Path, symbol: str) -> int:
    detailed = _load_symbol_detailed_report(repo_root=repo_root, symbol=symbol)
    if isinstance(detailed.get("actual_candidate_strikes"), list):
        return len(detailed["actual_candidate_strikes"])
    return 1


def _load_rejections(*, repo_root: Path, symbol: str) -> list[Mapping[str, Any]]:
    detailed = _load_symbol_detailed_report(repo_root=repo_root, symbol=symbol)
    branch_candidates = detailed.get("branch_candidates")
    if not isinstance(branch_candidates, list):
        return []
    rejections: list[Mapping[str, Any]] = []
    for branch in branch_candidates:
        if not isinstance(branch, Mapping):
            continue
        for attempt in branch.get("expiry_attempts") or ():
            if not isinstance(attempt, Mapping):
                continue
            for item in attempt.get("rejected_candidates") or ():
                if isinstance(item, Mapping):
                    rejections.append(dict(item))
    return rejections


def _load_symbol_selection(*, repo_root: Path, symbol: str) -> Mapping[str, Any]:
    payload = json.loads((repo_root / "reports" / "contract_selection" / "actual_strike_set_contract.json").read_text(encoding="utf-8"))
    symbols = payload.get("symbols") if isinstance(payload, Mapping) else None
    if not isinstance(symbols, Mapping):
        return {}
    target = symbols.get(symbol)
    return target if isinstance(target, Mapping) else {}


def _load_symbol_detailed_report(*, repo_root: Path, symbol: str) -> Mapping[str, Any]:
    report_path = repo_root / "reports" / "contract_selection" / f"{symbol.lower()}_actual_chain_selection.json"
    if not report_path.exists():
        return {}
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, Mapping) else {}


def _underlying_references(candles: Iterable[Any]) -> dict[str, Decimal]:
    completed = tuple(candles)
    if len(completed) < 4:
        raise ValueError("S22 stock fast-track requires at least four completed underlying daily candles.")
    last2 = completed[-2:]
    last3 = completed[-3:]
    last4 = completed[-4:]
    return {
        "2DHH": Decimal(f"{max(bar.high for bar in last2):.2f}"),
        "2DLL": Decimal(f"{min(bar.low for bar in last2):.2f}"),
        "3DHH": Decimal(f"{max(bar.high for bar in last3):.2f}"),
        "4DHH": Decimal(f"{max(bar.high for bar in last4):.2f}"),
        "4DLL": Decimal(f"{min(bar.low for bar in last4):.2f}"),
    }


def _selected_option_references(candles: Iterable[Any]) -> dict[str, Decimal]:
    completed = tuple(candles)
    if len(completed) < 4:
        raise ValueError("S22 stock fast-track requires at least four completed selected-option daily candles.")
    last2 = completed[-2:]
    last3 = completed[-3:]
    last4 = completed[-4:]
    return {
        "OPT_PRV_2DHH": Decimal(f"{max(bar.high for bar in last2):.4f}"),
        "OPT_PRV_2DLL": Decimal(f"{min(bar.low for bar in last2):.4f}"),
        "OPT_PRV_3DHH": Decimal(f"{max(bar.high for bar in last3):.4f}"),
        "OPT_PRV_3DLL": Decimal(f"{min(bar.low for bar in last3):.4f}"),
        "OPT_PRV_4DHH": Decimal(f"{max(bar.high for bar in last4):.4f}"),
        "OPT_PRV_4DLL": Decimal(f"{min(bar.low for bar in last4):.4f}"),
    }


def _plan_values(
    *,
    branch_spec: S22BranchPlanSpec,
    option_refs: Mapping[str, Decimal],
) -> dict[str, Decimal]:
    base_entry_reference = option_refs[branch_spec.base_entry_reference]
    base_entry = base_entry_reference * (Decimal("1") - (branch_spec.base_entry_discount_pct / Decimal("100")))
    target = base_entry * (Decimal("1") - (branch_spec.target_discount_pct / Decimal("100")))
    original_sl_reference = option_refs[branch_spec.original_sl_reference] * (
        Decimal("1") + (branch_spec.original_sl_reference_pct / Decimal("100"))
    )
    original_sl_entry = base_entry * (Decimal("1") + (branch_spec.original_sl_entry_pct / Decimal("100")))
    original_sl = min(original_sl_entry, original_sl_reference)
    revised_entry_reference = option_refs[branch_spec.revised_entry_reference]
    revised_entry = revised_entry_reference
    revised_sl = original_sl_reference
    return {
        "base_entry": base_entry,
        "target": target,
        "original_sl": original_sl,
        "revised_entry": revised_entry,
        "revised_sl": revised_sl,
    }


def _quote_payload(*, quote_result: Any, now: datetime) -> Mapping[str, Any] | None:
    if quote_result.status is not FyersReadOnlyStatus.SUCCESS or not quote_result.payload:
        return None
    quote = quote_result.payload[0]
    return {
        "symbol": quote.symbol,
        "ltp": str(quote.ltp) if quote.ltp is not None else None,
        "bid": str(quote.bid) if quote.bid is not None else None,
        "ask": str(quote.ask) if quote.ask is not None else None,
        "oi": str(quote.oi) if quote.oi is not None else None,
        "source_timestamp": quote.timestamp.isoformat() if quote.timestamp is not None else None,
        "receipt_timestamp": now.isoformat(),
    }
