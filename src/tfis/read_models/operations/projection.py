from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from tfis.persistence import canonical_hash
from tfis.runtime.multi_strategy.registry import EnabledStrategyInstance, EnabledStrategyRegistry

from .models import AccountRiskProjection, OperationalReadModel, StrategyInstanceReadModel


REPO_ROOT = Path(__file__).resolve().parents[4]

MONTHLY_DERIVATION_REPORTS: dict[str, tuple[str, ...]] = {
    "S21_BANKNIFTY_INTERNAL_PAPER_A": (
        "reports/fast_track_development/today_s21_result.json",
        "reports/historical_reconstruction/s21_historical_selection.json",
        "reports/s21_complete/s21_natural_branch_selection.json",
    ),
    "S22_RELIANCE_INTERNAL_PAPER_A": (
        "reports/s22_reliance/s22_reliance_monthly_status.json",
        "reports/fast_track_development/today_s22_result.json",
    ),
    "S23_NIFTY_INTERNAL_PAPER_A": (
        "reports/fast_track_development/today_s23_result.json",
        "reports/historical_reconstruction/s23_historical_selection.json",
    ),
}


STATE_LABELS: dict[str, str] = {
    "NORMAL_ENTRY_STILL_VALID": "Entry Available",
    "RC_ENTRY_STILL_VALID": "RC Entry Available",
    "RC_WAITING": "Waiting For RC",
    "PROCESSED_INTERNAL_PAPER": "Internal Paper Order Processed",
    "FILLED_INTERNAL": "Filled - Internal Paper",
    "OPEN_PROTECTED": "Open and Protected",
    "OPEN_UNPROTECTED": "Open and Unprotected",
    "HISTORICAL_RECONSTRUCTION": "Reconstructed from Market History",
    "NO_ORDER": "No Order",
    "VALIDATION_REJECTED": "Validation Blocked",
    "DETERMINISTIC_TIMING_SUPPLEMENT": "Deterministic Timing Supplement",
    "FIXTURE_BACKED": "Fixture Backed",
    "AVAILABLE": "Available",
    "HEALTHY": "Healthy",
    "DEGRADED": "Degraded",
    "DEGRADED_EVIDENCE": "Evidence Limited",
    "ACTIVE": "Active",
    "INTERNAL_PAPER_CONTROLLED": "Internal Paper Controlled",
    "READ_ONLY_OR_INTERNAL": "Read Only / Internal",
    "CARRIED": "Carried",
    "FRESH": "Fresh",
    "NO_POSITION": "No Position",
    "PROTECTED": "Protected",
    "MISSING_PROTECTION": "Protection Missing",
    "ACCEPTED": "Accepted",
    "REJECTED": "Rejected",
    "WARNING": "Warning",
    "CRITICAL": "Critical",
}

FAMILY_LABELS: dict[str, str] = {
    "OPTION_SELLING": "Option Selling",
    "OPTION_BUYING": "Option Buying",
    "FUTURES": "Futures",
    "EQUITY": "Equity",
    "COMMODITY": "Commodity",
    "CURRENCY": "Currency",
}


def _default_account_display_name(account_reference: str) -> str:
    value = str(account_reference or "")
    if value == "INTERNAL_PAPER_ACCOUNT_A":
        return "FYERS Read-Only Internal Paper Account"
    if value == "DEVELOPMENT_INTERNAL_PAPER_ACCOUNT_A":
        return "FYERS Read-Only Development Internal Paper Account"
    return value


def build_unified_dashboard_projection(
    registry: EnabledStrategyRegistry,
    instance_results: Mapping[str, Mapping[str, Any]],
    *,
    scenario_id: str,
) -> OperationalReadModel:
    read_models = tuple(_strategy_read_model(item, instance_results[item.strategy_instance_id]) for item in registry.enabled_instances)
    orders = tuple(
        row
        for item in registry.enabled_instances
        for row in (_order_row(item, instance_results[item.strategy_instance_id]),)
        if _include_order_row(row)
    )
    positions = tuple(
        row
        for item in registry.enabled_instances
        for row in (_position_row(item, instance_results[item.strategy_instance_id]),)
        if _include_position_row(row)
    )
    alerts = tuple(alert for model in read_models for alert in model.operations.get("alerts", ()))
    blocked = [model.identity["strategy_instance_id"] for model in read_models if str(model.state["runtime_stage"]).startswith("BLOCKED")]
    strategy_instances = _strategy_instance_rows(read_models)
    strategy_status_counts = _strategy_status_counts(strategy_instances)
    strategy_definitions = _strategy_definition_summaries(read_models, strategy_instances)
    accounts = (_account_projection(registry, read_models, positions, orders),)
    risk = _risk_projection(accounts[0], positions, orders, alerts)
    realized = sum(Decimal(str(row.get("realized_pnl", "0"))) for row in positions)
    unrealized = sum(Decimal(str(row.get("unrealized_pnl", "0"))) for row in positions)
    state_labels = {key: {"label": value} for key, value in STATE_LABELS.items()}
    strategy_families = _strategy_family_summaries(read_models, positions)
    historical_trades = _historical_trade_rows(read_models, positions)
    decision_explanations = _build_decision_explanations(read_models, instance_results)
    navigation = _navigation_model(strategy_definitions=strategy_definitions, strategy_status_counts=strategy_status_counts)
    strategy_filter_options = _strategy_filter_options(strategy_instances, strategy_definitions)
    system = {
        "runtime": "UNIFIED_S21_S22_S23_INTERNAL_PAPER",
        "scenario_id": scenario_id,
        "authority_mode": "INTERNAL_PAPER_CONTROLLED",
        "market_state": "DETERMINISTIC_SESSION",
        "broker_order_authority": "NONE",
        "registry_hash": registry.registry_hash,
        "dashboard_failure_financial_action": "IMPOSSIBLE_READ_ONLY_PROJECTION",
        "projection_mode": "READ_ONLY_OPERATOR_PLATFORM",
        "projection_version": "dashboard_v3",
        "generated_at": "2026-08-04T23:20:00+05:30",
        "trading_date": "2026-08-04",
        "session": registry.session_scope["trading_session_id"],
    }
    command_centre = _command_centre_model(
        registry=registry,
        read_models=read_models,
        strategy_definitions=strategy_definitions,
        strategy_status_counts=strategy_status_counts,
        orders=orders,
        positions=positions,
        alerts=alerts,
        realized=realized,
        unrealized=unrealized,
        blocked=blocked,
        account=accounts[0],
        risk=risk,
    )
    analytics = _build_analytics_model(
        read_models=read_models,
        positions=positions,
        account=accounts[0],
        blocked=blocked,
        realized=realized,
        unrealized=unrealized,
    )
    settings = {
        "accounts": {
            "editable_mode": "INTERNAL_PAPER_LOCAL_ONLY",
            "credential_exposure": "PROHIBITED",
            "versioned_write_required": True,
            "audit_required": True,
        },
        "brokers": {"external_order_authority": "NONE", "read_only_sessions": True},
        "strategies": {
            "families_supported": list(FAMILY_LABELS.values()),
            "frontend_business_calculation": False,
        },
        "dashboard_preferences": {"theme_toggle": True, "saved_filters": "NOT_IMPLEMENTED"},
    }
    audit = (
        {
            "operator": "SYSTEM",
            "timestamp": "2026-08-04T16:45:00+05:30",
            "command": "BUILD_UNIFIED_INTERNAL_PAPER_PROJECTION",
            "scope": "S21,S22,S23",
            "reason": "deterministic certification",
            "preview": True,
            "result": "SNAPSHOT_CREATED",
            "previous_state": "NO_UNIFIED_PROJECTION",
            "new_state": "UNIFIED_PROJECTION_READY",
            "evidence_hash": canonical_hash({"scenario_id": scenario_id, "registry": registry.registry_hash}),
        },
    )
    return OperationalReadModel(
        schema_version="tfis.operations.unified_read_model.v3",
        system=system,
        navigation=navigation,
        command_centre=command_centre,
        strategy_families=tuple(strategy_families),
        strategy_definitions=tuple(strategy_definitions),
        strategy_instances=tuple(strategy_instances),
        strategy_status_counts=strategy_status_counts,
        strategy_filter_options=strategy_filter_options,
        strategies=read_models,
        accounts=accounts,
        risk=risk,
        orders=orders,
        positions=positions,
        historical_trades=tuple(historical_trades),
        analytics=analytics,
        decision_explanations=tuple(decision_explanations),
        state_labels=state_labels,
        settings=settings,
        alerts=alerts,
        audit=audit,
    )


def _strategy_read_model(instance: EnabledStrategyInstance, result: Mapping[str, Any]) -> StrategyInstanceReadModel:
    plan = dict(result["plan"])
    execution = dict(result["execution"])
    position = dict(result["position"])
    accounting = dict(result["accounting"])
    operations = dict(result["operations"])
    strategy_code = instance.strategy_definition_id.split("_", 1)[0]
    family_code = str(instance.product or "OPTION_SELLING").upper()
    segment_code = str(instance.underlying.get("instrument_type") or "UNKNOWN").upper()
    family_label = FAMILY_LABELS.get(family_code, family_code.replace("_", " ").title())
    segment_label = {
        "INDEX": "Index Options",
        "STOCK": "Stock Options",
    }.get(segment_code, segment_code.replace("_", " ").title())
    strategy_display_name = str(instance.source_reports.get("display_name") or _pretty_strategy_name(instance.strategy_definition_id))
    supported_instruments_count = int(instance.source_reports.get("supported_instruments_count") or 1)
    account_display_name = str(
        instance.source_reports.get("account_display_name")
        or instance.source_reports.get("account_label")
        or _default_account_display_name(instance.account_reference)
    )
    health = result["health"]
    plan.update(
        {
            "plan_status_label": _operator_label(plan.get("plan_status")),
            "block_reason_label": _operator_label(plan.get("block_reason")),
            "evidence_quality_label": _operator_label(instance.evidence_quality),
            "segment": segment_label,
            "family": family_label,
        }
    )
    execution.update(
        {
            "order_state_label": _operator_label(execution.get("order_state")),
            "fill_state_label": _operator_label(execution.get("fill_state")),
            "risk_result_label": _operator_label(execution.get("risk_result")),
            "opening_context_label": _operator_label(execution.get("opening_context")),
            "mode_label": _operator_label(instance.authority_mode),
        }
    )
    position.update(
        {
            "health_label": _operator_label(position.get("health")),
            "protection_status_label": _operator_label(position.get("protection_status")),
            "fresh_or_carried_label": _operator_label(position.get("fresh_or_carried")),
            "side": _side_from_branch(plan.get("branch")),
        }
    )
    accounting.update(
        {
            "realized_pnl_tone": _pnl_tone(accounting.get("realized_pnl")),
            "unrealized_pnl_tone": _pnl_tone(accounting.get("unrealized_pnl")),
        }
    )
    operations.update(
        {
            "alert_count": len(operations.get("alerts", ())),
            "authority_mode_label": _operator_label(instance.authority_mode),
        }
    )
    return StrategyInstanceReadModel(
        identity={
            "account": instance.account_reference,
            "account_display_name": account_display_name,
            "strategy": strategy_code,
            "strategy_definition_id": instance.strategy_definition_id,
            "strategy_display_name": strategy_display_name,
            "version": instance.strategy_version,
            "instance": instance.strategy_instance_id,
            "strategy_instance_id": instance.strategy_instance_id,
            "instrument": instance.symbol,
            "supported_instruments_count": supported_instruments_count,
            "product": instance.product,
            "product_label": family_label,
            "segment": segment_code,
            "segment_label": segment_label,
            "exchange": instance.underlying.get("exchange"),
            "session": result["trading_session_id"],
            "broker": _broker_name(instance.market_data_source),
            "configured_lots": int(instance.configured_quantity.get("lots", 0) or 0),
            "lot_size": int(instance.configured_quantity.get("lot_size", 0) or 0),
            "margin_limit_pct": int(instance.risk_allocation.get("max_margin_usage_pct", 0) or 0),
        },
        state={
            "enabled": instance.enabled,
            "enabled_label": "Enabled" if instance.enabled else "Disabled",
            "runtime_stage": result["runtime_stage"],
            "runtime_stage_label": _operator_label(result["runtime_stage"]),
            "monthly_status": plan["monthly_status"],
            "monthly_status_label": _operator_label(plan["monthly_status"]),
            "branch": plan["branch"],
            "branch_label": _operator_label(plan["branch"]),
            "evidence_quality": instance.evidence_quality,
            "evidence_quality_label": _operator_label(instance.evidence_quality),
            "last_update": result["last_update"],
            "health": health,
            "health_label": _operator_label(health),
            "current_action": execution["order_state"],
            "current_action_label": _operator_label(execution["order_state"]),
            "entry_eligibility": result["runtime_stage"],
            "entry_eligibility_label": _operator_label(result["runtime_stage"]),
        },
        plan=plan,
        execution=execution,
        position=position,
        accounting=accounting,
        operations=operations,
    )


def _build_analytics_model(
    *,
    read_models: tuple[StrategyInstanceReadModel, ...],
    positions: tuple[Mapping[str, Any], ...],
    account: AccountRiskProjection,
    blocked: list[str],
    realized: Decimal,
    unrealized: Decimal,
) -> dict[str, Any]:
    position_totals = [Decimal(str(row.get("realized_pnl", "0"))) + Decimal(str(row.get("unrealized_pnl", "0"))) for row in positions]
    settled_totals = [value for value, row in zip(position_totals, positions, strict=False) if not str(row.get("health", "")).startswith("OPEN")]
    winners = [value for value in settled_totals if value > 0]
    losers = [value for value in settled_totals if value < 0]
    breakeven = sum(1 for value in settled_totals if value == 0)
    open_positions = sum(1 for row in positions if str(row.get("health", "")).startswith("OPEN"))
    average_winner = _average_decimal(winners)
    average_loser = _average_decimal(losers)
    total_wins = sum(winners, Decimal("0"))
    total_losses = abs(sum(losers, Decimal("0")))
    decisive_trades = len(winners) + len(losers)
    win_rate = (Decimal(len(winners)) / Decimal(decisive_trades) * Decimal("100")) if decisive_trades else Decimal("0")
    payoff_ratio = abs(average_winner / average_loser) if average_winner and average_loser else Decimal("0")
    profit_factor = (total_wins / total_losses) if total_losses else Decimal("0")
    expectancy = (
        (win_rate / Decimal("100")) * average_winner
        + ((Decimal("100") - win_rate) / Decimal("100")) * average_loser
        if decisive_trades
        else Decimal("0")
    )
    strategy_wise_pnl = {
        model.identity["strategy"]: _format_decimal(
            Decimal(str(model.accounting.get("realized_pnl", "0"))) + Decimal(str(model.accounting.get("unrealized_pnl", "0")))
        )
        for model in read_models
    }
    instrument_wise_pnl = {
        row["instrument"]: _format_decimal(Decimal(str(row.get("realized_pnl", "0"))) + Decimal(str(row.get("unrealized_pnl", "0"))))
        for row in positions
    }
    call_vs_put = Counter(_contract_side_from_branch(str(model.state.get("branch") or "")) for model in read_models)
    bull_vs_bear = Counter(_market_bias_from_branch(str(model.state.get("branch") or "")) for model in read_models)
    normal_vs_rc = Counter("RC" if "RC" in str(model.execution.get("risk_result") or "") or "RC" in str(model.state.get("runtime_stage") or "") else "NORMAL" for model in read_models)
    fresh_vs_carried = Counter(str(row.get("fresh_or_carried") or "UNKNOWN") for row in positions)
    exit_reasons = Counter(str(row.get("technical_details", {}).get("eod_action") or "OPEN") for row in positions)
    account_risk_matrix = {
        model.identity["strategy_instance_id"]: {
            "decision": "ACCEPTED_INTENT" if model.execution.get("risk_result") == "ACCEPTED" else "BLOCKED_ACCOUNT",
            "risk_result": model.execution.get("risk_result"),
            "account": model.identity.get("account"),
            "instrument": model.identity.get("instrument"),
            "margin_limit_pct": model.identity.get("margin_limit_pct"),
        }
        for model in read_models
    }
    return {
        "source": "TradeFact/PnLFact/read projections only",
        "total_daily_pnl": _format_decimal(realized + unrealized),
        "cumulative_pnl": _format_decimal(realized + unrealized),
        "strategy_wise_pnl": strategy_wise_pnl,
        "account_wise_pnl": {account.display_name: _format_decimal(realized + unrealized)},
        "instrument_wise_pnl": instrument_wise_pnl,
        "call_vs_put": dict(call_vs_put),
        "bull_vs_bear": dict(bull_vs_bear),
        "normal_vs_rc": dict(normal_vs_rc),
        "fresh_vs_carried": dict(fresh_vs_carried),
        "exit_reasons": dict(exit_reasons),
        "wins_losses_breakeven_open": {
            "wins": len(winners),
            "losses": len(losers),
            "breakeven": breakeven,
            "open": open_positions,
        },
        "win_rate": _format_decimal(win_rate),
        "average_winner": _format_decimal(average_winner),
        "average_loser": _format_decimal(average_loser),
        "payoff_ratio": _format_decimal(payoff_ratio),
        "profit_factor": _format_decimal(profit_factor),
        "expectancy": _format_decimal(expectancy),
        "drawdown": _format_decimal(total_losses),
        "mfe_mae_quality": "READ_MODEL_ONLY",
        "execution_slippage": "INTERNAL_PAPER_DETERMINISTIC",
        "blocked_funnel": {"prepared": len(read_models), "blocked": len(blocked), "accepted": len(read_models) - len(blocked)},
        "account_risk_matrix": account_risk_matrix,
        "mutates_trading_state": False,
    }


def _average_decimal(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _format_decimal(value: Decimal | int | float | str) -> str:
    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    return f"{decimal_value.quantize(Decimal('0.01'))}"


def _contract_side_from_branch(branch: str) -> str:
    if "CALL" in branch:
        return "CALL"
    if "PUT" in branch:
        return "PUT"
    return "UNKNOWN"


def _market_bias_from_branch(branch: str) -> str:
    if "BULL" in branch:
        return "BULL"
    if "BEAR" in branch:
        return "BEAR"
    return "UNKNOWN"


def _account_projection(
    registry: EnabledStrategyRegistry,
    read_models: tuple[StrategyInstanceReadModel, ...],
    positions: tuple[Mapping[str, Any], ...],
    orders: tuple[Mapping[str, Any], ...],
) -> AccountRiskProjection:
    accepted = tuple(model.identity["strategy_instance_id"] for model in read_models if model.execution["risk_result"] == "ACCEPTED")
    rejected = tuple(model.identity["strategy_instance_id"] for model in read_models if model.execution["risk_result"] != "ACCEPTED")
    margin_pct = min(70, len(accepted) * 18)
    alerts = tuple(
        {"severity": "CRITICAL", "code": "MISSING_PROTECTION", "strategy_instance_id": row["strategy_instance_id"]}
        for row in positions
        if row["health"].startswith("OPEN") and row["protection_status"] != "PROTECTED"
    )
    account_cfg = registry.accounts[0]
    display_name = str(
        account_cfg.get("display_name")
        or account_cfg.get("operator_account_name")
        or account_cfg.get("broker_account_display_name")
        or _default_account_display_name(str(account_cfg.get("account_reference", "INTERNAL_PAPER_ACCOUNT_A")))
    )
    return AccountRiskProjection(
        account_reference=str(account_cfg.get("account_reference", "INTERNAL_PAPER_ACCOUNT_A")),
        display_name=display_name,
        status="DEGRADED" if alerts else "ACTIVE",
        limits={
            **registry.risk,
            "starting_capital": account_cfg.get("starting_capital", 1000000),
            "simulated_balance": account_cfg.get("simulated_balance", 1000000),
            "available_margin": account_cfg.get("available_margin", 460000),
            "reserved_margin": account_cfg.get("reserved_margin", 0),
            "environment": "INTERNAL_PAPER",
            "data_only_or_trading": "TRADING_SIMULATION",
            "read_only_or_order_authorised": "READ_ONLY_OR_INTERNAL_PAPER",
            "default_account": True,
            "broker": account_cfg.get("broker", "INTERNAL_PAPER"),
            "display_name": display_name,
        },
        usage={
            "new_entries": len(accepted),
            "concurrent_positions": sum(1 for row in positions if row["health"].startswith("OPEN")),
            "margin_usage_pct": margin_pct,
            "aggregate_option_selling_exposure": len(accepted),
            "active_orders": sum(1 for row in orders if row["state"] != "NO_ORDER"),
            "used_margin": int(Decimal(str(account_cfg.get("starting_capital", 1000000))) * Decimal(margin_pct) / Decimal("100")),
        },
        accepted_instances=accepted,
        rejected_instances=rejected,
        alerts=alerts,
    )


def _order_row(instance: EnabledStrategyInstance, result: Mapping[str, Any]) -> dict[str, Any]:
    execution = result["execution"]
    position = result["position"]
    contract = execution.get("selected_contract") or position.get("selected_contract") or result["plan"]["selected_contract"]
    entry_time = result["operations"].get("entry_time") or (
        result["last_update"] if str(execution.get("order_state") or "") not in {"", "NO_ORDER"} else None
    )
    exit_time = result["operations"].get("exit_time")
    side = _side_from_branch(result["plan"]["branch"])
    warning = execution["failure"] or next((item.get("code") for item in result["operations"].get("alerts", ()) if item.get("severity") in {"WARNING", "CRITICAL"}), None)
    return {
        "time": result["last_update"],
        "entry_time": entry_time,
        "exit_time": exit_time,
        "account": instance.account_reference,
        "account_display_name": str(
            result.get("identity", {}).get("account_display_name")
            or instance.source_reports.get("account_display_name")
            or _default_account_display_name(instance.account_reference)
        ),
        "order_name": f"{instance.symbol} {side} Entry",
        "strategy": instance.strategy_definition_id.split("_", 1)[0],
        "strategy_display_name": str(instance.source_reports.get("display_name") or _pretty_strategy_name(instance.strategy_definition_id)),
        "strategy_instance_id": instance.strategy_instance_id,
        "instrument": instance.symbol,
        "contract": contract,
        "side": side,
        "lots": int(instance.configured_quantity.get("lots", 0)),
        "lot_size": int(instance.configured_quantity.get("lot_size", 0)),
        "purpose": execution["order_purpose"],
        "purpose_label": _operator_label(execution["order_purpose"]),
        "quantity": position["quantity"],
        "price": execution["effective_entry"],
        "target": position["target"],
        "active_sl": position["active_protection"],
        "status": execution["order_state"],
        "status_label": _operator_label(execution["order_state"]),
        "mode": _operator_label(instance.authority_mode),
        "warning_or_error": warning,
        "actions": "Explain Decision",
        "technical_details": {
            "client_order_id": f"client-order:{canonical_hash(instance.strategy_instance_id)[:24]}",
            "position_cycle_id": position["position_cycle"],
            "generation": execution["protection_generation"],
            "margin_reservation": "SIMULATED_ONLY",
            "validation_trace": execution["execution_intent"],
            "internal_response": execution["latest_event"],
            "raw_state": execution["order_state"],
            "failure": execution["failure"],
        },
        "instance": instance.strategy_instance_id,
        "position_cycle": position["position_cycle"],
        "execution_contract": contract,
        "generation": execution["protection_generation"],
        "requested_quantity": position["quantity"],
        "filled_quantity": execution["filled_quantity"],
        "state": execution["order_state"],
        "age": execution["order_age"],
        "latest_event": execution["latest_event"],
        "failure": execution["failure"],
    }


def _position_row(instance: EnabledStrategyInstance, result: Mapping[str, Any]) -> dict[str, Any]:
    position = result["position"]
    accounting = result["accounting"]
    age = _position_age_from_session(result["trading_session_id"])
    contract = position["selected_contract"] or result["execution"]["selected_contract"] or result["plan"]["selected_contract"]
    entry_time = position.get("entry_time") or (
        result["last_update"] if str(position.get("health") or "").startswith("OPEN") else None
    )
    exit_time = position.get("exit_time")
    return {
        "account": instance.account_reference,
        "account_display_name": str(
            result.get("identity", {}).get("account_display_name")
            or instance.source_reports.get("account_display_name")
            or _default_account_display_name(instance.account_reference)
        ),
        "position_name": f"{instance.symbol} {_side_from_branch(result['plan']['branch'])} Position",
        "strategy": instance.strategy_definition_id.split("_", 1)[0],
        "strategy_display_name": str(instance.source_reports.get("display_name") or _pretty_strategy_name(instance.strategy_definition_id)),
        "strategy_instance_id": instance.strategy_instance_id,
        "instrument": instance.symbol,
        "contract": contract,
        "position_contract": contract,
        "side": _side_from_branch(result["plan"]["branch"]),
        "lots": int(instance.configured_quantity.get("lots", 0)),
        "lot_size": int(instance.configured_quantity.get("lot_size", 0)),
        "fresh_or_carried": position["fresh_or_carried"],
        "fresh_or_carried_label": _operator_label(position["fresh_or_carried"]),
        "quantity": position["quantity"],
        "average_entry": position["average_entry"],
        "entry_time": entry_time,
        "exit_time": exit_time,
        "mark": position["mark"],
        "target": position["target"],
        "active_sl": position["active_protection"],
        "protection_status": position["protection_status"],
        "protection_label": _operator_label(position["protection_status"]),
        "realized_pnl": accounting["realized_pnl"],
        "unrealized_pnl": accounting["unrealized_pnl"],
        "exit_deadline": position["exit_deadline"],
        "health": position["health"],
        "health_label": _operator_label(position["health"]),
        "status": position["health"],
        "status_label": _operator_label(position["health"]),
        "age": age,
        "technical_details": {
            "position_cycle_id": position["position_cycle"],
            "fills": execution_fill_summary(result),
            "protection_generations": result["execution"]["protection_generation"],
            "target_sl_timeline": result["execution"]["latest_event"],
            "carry_status": position["carried_state"],
            "eod_action": position["exit_reason"],
            "mark_source": result["plan"]["evidence_quality"],
            "accounting_detail": accounting["accounting_quality"],
            "evidence_quality": result["plan"]["evidence_quality"],
        },
    }


def _include_order_row(row: Mapping[str, Any]) -> bool:
    state = str(row.get("state") or "")
    return state not in {"", "NO_ORDER", "FILLED_INTERNAL"}


def _include_position_row(row: Mapping[str, Any]) -> bool:
    return str(row.get("health") or "").startswith("OPEN")


def _strategy_family_summaries(read_models: tuple[StrategyInstanceReadModel, ...], positions: tuple[Mapping[str, Any], ...]) -> list[dict[str, Any]]:
    grouped: dict[str, list[StrategyInstanceReadModel]] = defaultdict(list)
    for model in read_models:
        grouped[model.identity["product_label"]].append(model)
    summaries: list[dict[str, Any]] = []
    for family_label in [
        "Option Selling",
        "Option Buying",
        "Futures",
        "Equity",
        "Commodity",
        "Currency",
    ]:
        items = grouped.get(family_label, [])
        pnl = sum(Decimal(str(item.accounting["realized_pnl"])) + Decimal(str(item.accounting["unrealized_pnl"])) for item in items) if items else Decimal("0")
        health_counts = Counter(item.state["health"] for item in items)
        summaries.append(
            {
                "family": family_label,
                "strategy_count": len({item.identity["strategy"] for item in items}),
                "instrument_count": len(items),
                "active_positions": sum(1 for row in positions if row["strategy_instance_id"] in {item.identity["strategy_instance_id"] for item in items} and row["health"].startswith("OPEN")),
                "blocked": sum(1 for item in items if str(item.state["runtime_stage"]).startswith("BLOCKED")),
                "no_trade": sum(1 for item in items if item.execution["order_state"] == "NO_ORDER"),
                "open_positions": sum(1 for row in positions if row["strategy_instance_id"] in {item.identity["strategy_instance_id"] for item in items} and row["health"].startswith("OPEN")),
                "daily_pnl": str(pnl),
                "health": "Healthy" if not health_counts.get("DEGRADED_EVIDENCE") else "Evidence Limited",
                "evidence_quality": ", ".join(sorted({item.state["evidence_quality_label"] for item in items})) if items else "Not enabled",
                "scalability_demo": family_label == "Option Selling",
            }
        )
    return summaries


def _risk_projection(
    account: AccountRiskProjection,
    positions: tuple[Mapping[str, Any], ...],
    orders: tuple[Mapping[str, Any], ...],
    alerts: tuple[Mapping[str, Any], ...],
) -> dict[str, Any]:
    used_margin = account.usage.get("used_margin", 0)
    available_margin = account.limits.get("available_margin", 460000)
    reserved_margin = account.limits.get("reserved_margin", 0)
    worst_position = min(positions, key=lambda item: Decimal(str(item["realized_pnl"])) + Decimal(str(item["unrealized_pnl"])), default=None)
    return {
        "aggregate": {
            "available_margin": available_margin,
            "reserved_margin": reserved_margin,
            "used_margin": used_margin,
            "margin_usage_pct": account.usage["margin_usage_pct"],
            "daily_loss_limit": account.limits["daily_loss_limit"],
            "open_positions": sum(1 for row in positions if row["health"].startswith("OPEN")),
            "pending_orders": sum(1 for row in orders if row["state"] not in {"NO_ORDER", "REJECTED_INTERNAL"}),
            "unprotected_positions": sum(1 for row in positions if row["protection_status"] != "PROTECTED"),
            "rejected_intents": len(account.rejected_instances),
            "risk_state": _operator_label(account.status),
        },
        "per_account": [
            {
                "account": account.display_name,
                "account_reference": account.account_reference,
                "available_margin": available_margin,
                "reserved_margin": reserved_margin,
                "used_margin": used_margin,
                "margin_usage_pct": account.usage["margin_usage_pct"],
                "daily_loss_limit": account.limits["daily_loss_limit"],
                "remaining_capacity": max(0, 100 - int(account.usage["margin_usage_pct"])),
                "status": _operator_label(account.status),
                "warnings": [item.get("code") for item in alerts],
            }
        ],
        "worst_position": {
            "instrument": worst_position["instrument"] if worst_position else None,
            "contract": worst_position["contract"] if worst_position else None,
            "pnl": (
                str(Decimal(str(worst_position["realized_pnl"])) + Decimal(str(worst_position["unrealized_pnl"])))
                if worst_position
                else None
            ),
        },
    }


def _historical_trade_rows(read_models: tuple[StrategyInstanceReadModel, ...], positions: tuple[Mapping[str, Any], ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model, position in zip(read_models, positions):
        rows.append(
            {
                "strategy": model.identity["strategy"],
                "account": model.identity["account_display_name"],
                "instrument": model.identity["instrument"],
                "contract": model.plan["selected_contract"],
                "entry_time": model.state["last_update"],
                "exit_time": None if position["health"].startswith("OPEN") else model.state["last_update"],
                "side": position["side"],
                "quantity": position["quantity"],
                "entry_price": position["average_entry"],
                "exit_price": None if position["health"].startswith("OPEN") else position["mark"],
                "exit_reason": position["technical_details"]["eod_action"],
                "gross_pnl": str(Decimal(str(position["realized_pnl"])) + Decimal(str(position["unrealized_pnl"]))),
                "charges": "PROVISIONAL_INTERNAL_PAPER",
                "net_pnl": str(Decimal(str(position["realized_pnl"])) + Decimal(str(position["unrealized_pnl"]))),
                "evidence_quality": model.state["evidence_quality_label"],
                "explanation_completeness": "Limited" if model.state["evidence_quality"] == "DETERMINISTIC_TIMING_SUPPLEMENT" else "Available",
                "trade_story": {
                    "decision_reason": model.state["branch_label"],
                    "selected_contract": model.plan["selected_contract"],
                    "entry": model.execution["effective_entry"],
                    "fills": model.execution["filled_quantity"],
                    "protection": position["protection_label"],
                    "exit": position["technical_details"]["eod_action"],
                    "accounting": model.accounting["accounting_quality"],
                    "evidence": model.state["evidence_quality_label"],
                    "explanation_snapshot": model.read_model_hash,
                    "timeline_anchor": model.state["last_update"],
                },
            }
        )
    return rows


def _strategy_instance_rows(read_models: tuple[StrategyInstanceReadModel, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in read_models:
        rows.append(
            {
                "strategy_instance_id": model.identity["strategy_instance_id"],
                "strategy_definition_id": model.identity["strategy_definition_id"],
                "strategy_code": model.identity["strategy"],
                "strategy_display_name": model.identity["strategy_display_name"],
                "family": model.identity["product_label"],
                "segment": model.identity["segment_label"],
                "instrument": model.identity["instrument"],
                "enabled": model.state["enabled"],
                "enabled_label": model.state["enabled_label"],
                "account": model.identity["account"],
                "account_display_name": model.identity["account_display_name"],
                "monthly_status": model.state["monthly_status"],
                "branch": model.state["branch"],
                "current_stage": model.state["runtime_stage"],
                "selected_contract": model.plan["selected_contract"],
                "entry": model.plan["base_entry"],
                "position": model.position["health"],
                "position_label": model.position["health_label"],
                "fresh_or_carried": model.position["fresh_or_carried"],
                "realized_pnl": model.accounting["realized_pnl"],
                "unrealized_pnl": model.accounting["unrealized_pnl"],
                "health": model.state["health"],
                "health_label": model.state["health_label"],
                "evidence": model.state["evidence_quality"],
                "evidence_label": model.state["evidence_quality_label"],
                "last_update": model.state["last_update"],
                "alerts": tuple(model.operations.get("alerts", ())),
                "has_alerts": bool(model.operations.get("alerts")),
                "entry_available": _is_entry_available(model),
                "blocked": _is_blocked(model),
                "no_trade": _is_no_trade(model),
                "qualified": _is_qualified(model),
            }
        )
    return rows


def _strategy_definition_summaries(
    read_models: tuple[StrategyInstanceReadModel, ...],
    strategy_instances: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped_models: dict[str, list[StrategyInstanceReadModel]] = defaultdict(list)
    grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for model in read_models:
        grouped_models[model.identity["strategy_definition_id"]].append(model)
    for row in strategy_instances:
        grouped_rows[str(row["strategy_definition_id"])].append(row)
    summaries: list[dict[str, Any]] = []
    for definition_id, models in grouped_models.items():
        rows = grouped_rows[definition_id]
        first = models[0]
        health_values = {str(item["health"]) for item in rows}
        evidence_values = {str(item["evidence_label"]) for item in rows}
        accounts = sorted({str(item["account"]) for item in rows})
        instruments = sorted({str(item["instrument"]) for item in rows})
        margin_used_pct = sum(_estimated_margin_usage_pct(item) for item in rows)
        summaries.append(
            {
                "strategy_definition_id": definition_id,
                "strategy_code": first.identity["strategy"],
                "display_name": first.identity["strategy_display_name"],
                "family": first.identity["product_label"],
                "segment": first.identity["segment_label"],
                "supported_count": max(int(first.identity.get("supported_instruments_count") or 0), len(instruments)),
                "enabled_count": len(rows),
                "prepared_count": sum(1 for item in rows if str(item["current_stage"]).strip()),
                "qualified_count": sum(1 for item in rows if item["qualified"]),
                "entry_available_count": sum(1 for item in rows if item["entry_available"]),
                "open_count": sum(1 for item in rows if str(item["position"]).startswith("OPEN")),
                "carried_count": sum(1 for item in rows if item["fresh_or_carried"] == "CARRIED"),
                "blocked_count": sum(1 for item in rows if item["blocked"]),
                "no_trade_count": sum(1 for item in rows if item["no_trade"]),
                "realized_pnl": str(sum(Decimal(str(item["realized_pnl"])) for item in rows)),
                "unrealized_pnl": str(sum(Decimal(str(item["unrealized_pnl"])) for item in rows)),
                "margin_used": margin_used_pct,
                "margin_usage_pct": margin_used_pct,
                "health": _aggregate_health(health_values),
                "evidence_quality": ", ".join(sorted(evidence_values)),
                "last_update": max(str(item["last_update"]) for item in rows),
                "accounts": accounts,
                "supported_instruments": instruments[:12],
                "instance_ids": [str(item["strategy_instance_id"]) for item in rows],
            }
        )
    return sorted(summaries, key=lambda item: (str(item["family"]), str(item["strategy_code"]), str(item["display_name"])))


def _strategy_status_counts(strategy_instances: list[dict[str, Any]]) -> dict[str, Any]:
    def counts_for(rows: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "all": len(rows),
            "enabled": sum(1 for item in rows if item["enabled"]),
            "entry_available": sum(1 for item in rows if item["entry_available"]),
            "open_positions": sum(1 for item in rows if str(item["position"]).startswith("OPEN")),
            "carried": sum(1 for item in rows if item["fresh_or_carried"] == "CARRIED"),
            "blocked": sum(1 for item in rows if item["blocked"]),
            "no_trade": sum(1 for item in rows if item["no_trade"]),
            "missing_evidence": sum(1 for item in rows if str(item["evidence"]).upper() in {"DEGRADED_EVIDENCE", "DETERMINISTIC_TIMING_SUPPLEMENT"}),
            "alerts": sum(1 for item in rows if item["has_alerts"]),
        }

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in strategy_instances:
        grouped[str(item["strategy_definition_id"])].append(item)
    return {
        "global": counts_for(strategy_instances),
        "by_definition": {definition_id: counts_for(rows) for definition_id, rows in sorted(grouped.items())},
    }


def _strategy_filter_options(
    strategy_instances: list[dict[str, Any]],
    strategy_definitions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "definitions": [
            {
                "strategy_definition_id": item["strategy_definition_id"],
                "strategy_code": item["strategy_code"],
                "display_name": item["display_name"],
            }
            for item in strategy_definitions
        ],
        "accounts": sorted({str(item.get("account_display_name") or item["account"]) for item in strategy_instances}),
        "monthly_statuses": sorted({str(item["monthly_status"]) for item in strategy_instances if item["monthly_status"]}),
        "branches": sorted({str(item["branch"]) for item in strategy_instances if item["branch"]}),
        "stages": sorted({str(item["current_stage"]) for item in strategy_instances if item["current_stage"]}),
        "health": sorted({str(item["health"]) for item in strategy_instances if item["health"]}),
        "evidence": sorted({str(item["evidence"]) for item in strategy_instances if item["evidence"]}),
        "status_groups": [
            {"key": "all", "label": "All"},
            {"key": "enabled", "label": "Enabled"},
            {"key": "entry_available", "label": "Entry Available"},
            {"key": "open_positions", "label": "Open Positions"},
            {"key": "carried", "label": "Carried"},
            {"key": "blocked", "label": "Blocked"},
            {"key": "no_trade", "label": "No Trade"},
            {"key": "missing_evidence", "label": "Missing Evidence"},
            {"key": "alerts", "label": "Alerts"},
        ],
        "sort_fields": [
            {"key": "realized_pnl", "label": "Realized P&L"},
            {"key": "unrealized_pnl", "label": "Unrealized P&L"},
            {"key": "current_stage", "label": "Current Stage"},
            {"key": "last_update", "label": "Last Update"},
            {"key": "instrument", "label": "Instrument"},
        ],
        "page_sizes": [10, 20, 50],
        "densities": ["compact", "detailed"],
        "saved_views_supported": True,
        "export_supported": True,
    }


def _load_monthly_derivation(*, instance_id: str, result: Mapping[str, Any]) -> dict[str, Any]:
    payload = _extract_monthly_payload(result)
    source = "runtime_result"
    source_path = None
    if payload is None:
        for relative_path in MONTHLY_DERIVATION_REPORTS.get(instance_id, ()):
            target = REPO_ROOT / relative_path
            try:
                payload = _extract_monthly_payload(json.loads(target.read_text(encoding="utf-8")))
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                payload = None
            if payload is not None:
                source = "report_fallback"
                source_path = relative_path
                break
    return _normalize_monthly_derivation(payload, source=source, source_path=source_path)


def _extract_monthly_payload(node: Any) -> Mapping[str, Any] | None:
    if isinstance(node, Mapping):
        references = node.get("source_monthly_references") or node.get("monthly_references")
        if node.get("monthly_status") is not None and isinstance(references, Mapping):
            return node
        for key in ("selection", "monthly_status_evidence", "monthly_status", "result", "payload"):
            value = node.get(key)
            if isinstance(value, Mapping):
                extracted = _extract_monthly_payload(value)
                if extracted is not None:
                    return extracted
        for value in node.values():
            extracted = _extract_monthly_payload(value)
            if extracted is not None:
                return extracted
    if isinstance(node, list):
        for item in node:
            extracted = _extract_monthly_payload(item)
            if extracted is not None:
                return extracted
    return None


def _normalize_monthly_derivation(
    payload: Mapping[str, Any] | None,
    *,
    source: str,
    source_path: str | None,
) -> dict[str, Any]:
    if payload is None:
        return {
            "available": False,
            "source": source,
            "source_path": source_path,
            "rule_id": "READ_MODEL_MONTHLY_STATUS",
            "workbook_source": "READ_MODEL_DERIVED_RUNTIME_PROJECTION",
            "formula_text": "Monthly Status final output is visible, but a step-by-step derivation packet is not available in this snapshot.",
            "evaluation_timestamp": None,
            "current_window_direct_status": None,
            "borrowed_window_status": None,
            "lookback_used": None,
            "checked_lookback_windows": None,
            "trigger_name": None,
            "threshold_value": None,
            "reason": "No authoritative monthly derivation packet was found for this strategy instance.",
            "references": {},
            "steps": [],
        }
    references = payload.get("source_monthly_references") or payload.get("monthly_references") or {}
    transition = payload.get("transition_evidence") if isinstance(payload.get("transition_evidence"), Mapping) else {}
    trace = transition.get("trace") if isinstance(transition.get("trace"), list) else []
    reason = str(payload.get("reason") or transition.get("notes") or "").strip()
    current_window_direct_status = payload.get("current_window_direct_status")
    borrowed_window_status = payload.get("borrowed_window_status")
    final_status = payload.get("monthly_status")
    lookback_used = payload.get("lookback_used")
    checked_lookback_windows = payload.get("checked_lookback_windows")
    trigger_name = payload.get("trigger_name") or transition.get("trigger_name")
    threshold_value = payload.get("threshold_value") or transition.get("threshold_value")
    normalized = {
        "available": True,
        "source": source,
        "source_path": source_path,
        "rule_id": str(payload.get("source_rule_id") or payload.get("rule_id") or "MONTHLY_STATUS.GENERIC.ENGINE.001"),
        "workbook_source": "MONTHLY_STATUS_ENGINE_AUTHORITY_PACKET",
        "formula_text": "Monthly Status is determined by the generic monthly-status engine using monthly and weekly reference levels, then applying continuation or transition rules to reach one final status.",
        "evaluation_timestamp": payload.get("evaluation_timestamp"),
        "current_window_direct_status": current_window_direct_status,
        "borrowed_window_status": borrowed_window_status,
        "lookback_used": lookback_used,
        "checked_lookback_windows": checked_lookback_windows,
        "trigger_name": trigger_name,
        "threshold_value": threshold_value,
        "reason": reason or "Final Monthly Status was emitted by the generic monthly-status engine.",
        "references": dict(references) if isinstance(references, Mapping) else {},
        "steps": _build_monthly_derivation_steps(
            payload=payload,
            references=references if isinstance(references, Mapping) else {},
            trace=trace,
            reason=reason,
            current_window_direct_status=current_window_direct_status,
            borrowed_window_status=borrowed_window_status,
            final_status=final_status,
            lookback_used=lookback_used,
            checked_lookback_windows=checked_lookback_windows,
            trigger_name=trigger_name,
            threshold_value=threshold_value,
        ),
    }
    return normalized


def _build_monthly_derivation_steps(
    *,
    payload: Mapping[str, Any],
    references: Mapping[str, Any],
    trace: list[Any],
    reason: str,
    current_window_direct_status: Any,
    borrowed_window_status: Any,
    final_status: Any,
    lookback_used: Any,
    checked_lookback_windows: Any,
    trigger_name: Any,
    threshold_value: Any,
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [
        {
            "step": 1,
            "title": "Collect the monthly and weekly reference levels",
            "result": "Reference levels loaded",
            "detail": "TFIS starts by loading the current-month and prior-period levels used by the generic Monthly Status engine.",
            "values": dict(references),
        },
        {
            "step": 2,
            "title": "Check the current month first",
            "result": _status_phrase(current_window_direct_status),
            "detail": (
                "The engine first tries to classify the current month directly from the current month and week structure."
                if current_window_direct_status not in (None, "")
                else "The snapshot does not include a separate direct-status field for the current month."
            ),
            "values": {
                "current_window_direct_status": current_window_direct_status,
            },
        },
    ]
    if trace:
        for index, item in enumerate(trace, start=3):
            if not isinstance(item, Mapping):
                continue
            window_label = item.get("window_label") or (
                f"lookback_{item.get('lookback_index')}" if item.get("lookback_index") not in (None, "") else "current_window"
            )
            steps.append(
                {
                    "step": index,
                    "title": f"Evaluate {str(window_label).replace('_', ' ')} context",
                    "result": _status_phrase(item.get("status")),
                    "detail": str(item.get("notes") or "The engine evaluated this historical context to see whether it can resolve or confirm Monthly Status."),
                    "values": {
                        "trigger_name": item.get("trigger_name"),
                        "threshold_value": item.get("threshold_value"),
                        "used_for_resolution": item.get("used_for_resolution"),
                        "context_month": item.get("context_month_label"),
                        "context_week": item.get("context_week_label"),
                    },
                }
            )
    elif lookback_used:
        steps.append(
            {
                "step": 3,
                "title": "Walk back to the last usable historical context",
                "result": _status_phrase(borrowed_window_status),
                "detail": "Because the current month did not classify cleanly, TFIS borrowed the last usable monthly status from an earlier month/week context.",
                "values": {
                    "borrowed_window_status": borrowed_window_status,
                    "checked_lookback_windows": checked_lookback_windows,
                },
            }
        )
    steps.append(
        {
            "step": len(steps) + 1,
            "title": "Apply the transition or continuation rule",
            "result": _status_phrase(final_status),
            "detail": reason or "The engine applied the monthly transition logic and locked the final Monthly Status for this evaluation.",
            "values": {
                "trigger_name": trigger_name,
                "threshold_value": threshold_value,
                "lookback_used": lookback_used,
            },
        }
    )
    steps.append(
        {
            "step": len(steps) + 1,
            "title": "Emit the final Monthly Status for strategy use",
            "result": _status_phrase(final_status),
            "detail": "This final status is then passed to the strategy so TFIS can decide which branch is even eligible to trade.",
            "values": {
                "monthly_status": final_status,
                "reason": reason,
            },
        }
    )
    return steps


def _status_phrase(value: Any) -> str:
    if value in (None, ""):
        return "Not available in this snapshot"
    return _operator_label(value)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _selection_packet(result: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(result.get("selection"))


def _plan_payload(result: Mapping[str, Any]) -> Mapping[str, Any]:
    selection = _selection_packet(result)
    return _mapping(selection.get("plan_payload"))


def _selection_workbook_source(selection: Mapping[str, Any], plan_payload: Mapping[str, Any]) -> str:
    source_cells = plan_payload.get("source_cells")
    workbook_row_id = plan_payload.get("workbook_row_id")
    parts: list[str] = []
    if workbook_row_id:
        parts.append(f"Workbook row {workbook_row_id}")
    if isinstance(source_cells, list) and source_cells:
        parts.append("Cells " + ", ".join(str(item) for item in source_cells))
    return " / ".join(parts) if parts else "READ_MODEL_DERIVED_RUNTIME_PROJECTION"


def _contract_selection_fact(
    *,
    base_identity: Mapping[str, Any],
    model: StrategyInstanceReadModel,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    selection = _selection_packet(result)
    plan_payload = _plan_payload(result)
    selected_contract_payload = _mapping(plan_payload.get("selected_contract"))
    evaluated_contracts = _list_of_mappings(plan_payload.get("evaluated_contracts")) or _list_of_mappings(
        selection.get("evaluated_contracts")
    )
    rejected_candidates = _list_of_mappings(plan_payload.get("rejected_candidates")) or _list_of_mappings(
        selection.get("rejected_candidates")
    )
    branch_candidates = _list_of_mappings(plan_payload.get("branch_candidates"))
    chosen_branch_candidate = next(
        (
            item
            for item in branch_candidates
            if str(item.get("decision") or "").upper() == "SELECTED"
        ),
        branch_candidates[0] if branch_candidates else {},
    )
    chosen_branch_candidate = _mapping(chosen_branch_candidate)
    selection_quote = _mapping(selection.get("quote"))
    selected_details = {
        "selected_contract": selection.get("selected_contract") or model.plan["selected_contract"],
        "selected_expiry": selection.get("selected_expiry") or selected_contract_payload.get("expiry"),
        "selected_option_type": selection.get("selected_option_type") or selected_contract_payload.get("option_type"),
        "selected_strike": selection.get("selected_strike") or selected_contract_payload.get("strike"),
        "premium": model.plan.get("premium") or selection_quote.get("ltp"),
        "oi": model.plan.get("oi") or selected_contract_payload.get("oi"),
        "qualification_phase": chosen_branch_candidate.get("qualification_phase"),
    }
    return {
        **base_identity,
        "stage": "CONTRACT_SELECTION",
        "rule_id": str(plan_payload.get("contract_selection_rule_id") or "READ_MODEL_SELECTED_CONTRACT"),
        "workbook_source": _selection_workbook_source(selection, plan_payload),
        "formula_text": (
            "TFIS scans actual listed contracts for the allowed expiry set, filters them by option side, strike search range, "
            "OI, and premium thresholds, then freezes one final contract for the strategy instance."
        ),
        "input_values": {
            "monthly_status": selection.get("monthly_status") or model.state["monthly_status"],
            "branch": selection.get("selected_branch") or model.state["branch"],
            "expiry_candidates": model.plan.get("expiry_candidates"),
            "market_references": plan_payload.get("market_references") or model.plan.get("market_references", {}),
            "source_cells": plan_payload.get("source_cells"),
        },
        "intermediate_values": {
            "candidate_count": plan_payload.get("candidate_count") or selection.get("candidate_count"),
            "selection_source": plan_payload.get("selection_source") or selection.get("evidence"),
            "evidence_origin": plan_payload.get("evidence_origin"),
            "formula_catalog": plan_payload.get("formula_catalog"),
            "selected_option_references": plan_payload.get("selected_option_references"),
            "attempted_expiries": chosen_branch_candidate.get("attempted_expiries"),
            "qualification_phase": chosen_branch_candidate.get("qualification_phase"),
        },
        "output_value": selected_details,
        "candidate_evidence": {
            "evaluated_contracts": evaluated_contracts,
            "rejected_candidates": rejected_candidates,
            "branch_candidates": branch_candidates,
            "selection_report_path": plan_payload.get("selection_report_path"),
            "selection_source": plan_payload.get("selection_source") or selection.get("evidence"),
            "source_cells": plan_payload.get("source_cells"),
            "workbook_row_id": plan_payload.get("workbook_row_id"),
            "selected_option_references": plan_payload.get("selected_option_references"),
            "formula_catalog": plan_payload.get("formula_catalog"),
            "evidence_origin": plan_payload.get("evidence_origin"),
            "quote": plan_payload.get("quote") or selection.get("quote"),
        },
    }


def _plan_composition_fact(
    *,
    base_identity: Mapping[str, Any],
    model: StrategyInstanceReadModel,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    plan_payload = _plan_payload(result)
    raw_prices = _mapping(plan_payload.get("raw_prices"))
    normalized_prices = _mapping(plan_payload.get("normalized_prices"))
    formula_catalog = _mapping(plan_payload.get("formula_catalog"))
    return {
        **base_identity,
        "stage": "PLAN_COMPOSITION",
        "rule_id": str(plan_payload.get("entry_rule_id") or "READ_MODEL_PLAN_VALUES"),
        "workbook_source": _selection_workbook_source(_selection_packet(result), plan_payload),
        "formula_text": (
            "Base entry, target, and stop-loss are produced by the backend plan packet. Where available, TFIS also records the "
            "raw workbook output before tick normalization and the normalized trading prices shown to the operator."
        ),
        "input_values": {
            "selected_contract": model.plan["selected_contract"],
            "market_references": plan_payload.get("market_references") or model.plan.get("market_references", {}),
            "selected_option_references": plan_payload.get("selected_option_references"),
        },
        "intermediate_values": {
            "formula_catalog": formula_catalog,
            "raw_prices": raw_prices,
            "normalized_prices": normalized_prices,
        },
        "output_value": {
            "base_entry": model.plan.get("base_entry"),
            "target": model.plan.get("target"),
            "original_sl": model.plan.get("original_sl"),
            "revised_entry": model.plan.get("revised_entry"),
            "revised_sl": model.plan.get("revised_sl"),
            "raw_prices": raw_prices,
            "normalized_prices": normalized_prices,
        },
        "candidate_evidence": {
            "formula_catalog": formula_catalog,
            "source_cells": plan_payload.get("source_cells"),
            "workbook_row_id": plan_payload.get("workbook_row_id"),
        },
    }


def _build_decision_explanations(
    read_models: tuple[StrategyInstanceReadModel, ...],
    instance_results: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for model in read_models:
        instance_id = model.identity["strategy_instance_id"]
        result = instance_results[instance_id]
        timestamp = str(model.state.get("last_update") or "")
        monthly_derivation = _load_monthly_derivation(instance_id=instance_id, result=result)
        base_identity = {
            "strategy_instance_id": instance_id,
            "instrument": model.identity["instrument"],
            "decision_id": f"{instance_id}:{timestamp}",
            "calculation_timestamp": timestamp,
            "evidence_source": "UNIFIED_RUNTIME_PROJECTION",
            "evidence_quality": model.state["evidence_quality"],
            "evidence_mode": "READ_MODEL_DERIVED",
            "rejection_reason": None,
        }
        facts.extend(
            [
                {
                    **base_identity,
                    "stage": "MONTHLY_STATUS",
                    "rule_id": monthly_derivation["rule_id"],
                    "workbook_source": monthly_derivation["workbook_source"],
                    "formula_text": monthly_derivation["formula_text"],
                    "input_values": {
                        "strategy_instance_id": instance_id,
                        "instrument": model.identity["instrument"],
                        "evaluation_timestamp": monthly_derivation["evaluation_timestamp"],
                        "monthly_references": monthly_derivation["references"],
                    },
                    "intermediate_values": {
                        "current_window_direct_status": monthly_derivation["current_window_direct_status"],
                        "borrowed_window_status": monthly_derivation["borrowed_window_status"],
                        "lookback_used": monthly_derivation["lookback_used"],
                        "checked_lookback_windows": monthly_derivation["checked_lookback_windows"],
                        "trigger_name": monthly_derivation["trigger_name"],
                        "threshold_value": monthly_derivation["threshold_value"],
                        "derivation_steps": monthly_derivation["steps"],
                    },
                    "output_value": {
                        "monthly_status": model.state["monthly_status"],
                        "monthly_status_label": model.state["monthly_status_label"],
                        "derivation_summary": monthly_derivation["reason"],
                    },
                    "candidate_evidence": {
                        "derivation": monthly_derivation,
                    },
                },
                {
                    **base_identity,
                    "stage": "BRANCH",
                    "rule_id": "READ_MODEL_BRANCH_SELECTION",
                    "workbook_source": "READ_MODEL_DERIVED_RUNTIME_PROJECTION",
                    "formula_text": "Strategy branch emitted by backend runtime projection; no frontend branch derivation.",
                    "input_values": {"monthly_status": model.state["monthly_status"]},
                    "intermediate_values": {},
                    "output_value": {
                        "branch": model.state["branch"],
                        "branch_label": model.state["branch_label"],
                    },
                    "candidate_evidence": {},
                },
                _contract_selection_fact(base_identity=base_identity, model=model, result=result),
                _plan_composition_fact(base_identity=base_identity, model=model, result=result),
                {
                    **base_identity,
                    "stage": "ENTRY_ELIGIBILITY",
                    "rule_id": "READ_MODEL_ENTRY_STATE",
                    "workbook_source": "READ_MODEL_DERIVED_RUNTIME_PROJECTION",
                    "formula_text": "ORPT, RC, and runtime entry-eligibility state emitted by backend runtime projection.",
                    "input_values": {
                        "orpt": model.plan.get("orpt"),
                        "rc": model.plan.get("rc"),
                    },
                    "intermediate_values": {},
                    "output_value": {
                        "current_entry_state": model.state["runtime_stage"],
                        "orpt_state": model.execution.get("orpt_state"),
                        "rc_state": model.execution.get("rc_state"),
                    },
                    "candidate_evidence": {
                        "reconstruction": {
                            "current_entry_state": model.state["runtime_stage"],
                            "orpt_result": model.execution.get("orpt_state"),
                            "rc_result": model.execution.get("rc_state"),
                        }
                    },
                },
                {
                    **base_identity,
                    "stage": "CURRENT_ACTION",
                    "rule_id": "READ_MODEL_ORDER_POSITION_STATE",
                    "workbook_source": "READ_MODEL_DERIVED_RUNTIME_PROJECTION",
                    "formula_text": "Order and PositionCycle state emitted by backend runtime projection.",
                    "input_values": {
                        "order_state": model.execution.get("order_state"),
                        "position_health": model.position.get("health"),
                    },
                    "intermediate_values": {},
                    "output_value": {
                        "current_action_state": model.execution.get("order_state"),
                        "fill_state": model.execution.get("fill_state"),
                        "position_health": model.position.get("health"),
                        "latest_event": model.execution.get("latest_event"),
                    },
                    "candidate_evidence": {},
                },
            ]
        )
        if result["execution"].get("failure"):
            facts[-1]["rejection_reason"] = result["execution"]["failure"]
    return facts


def _command_centre_model(
    *,
    registry: EnabledStrategyRegistry,
    read_models: tuple[StrategyInstanceReadModel, ...],
    strategy_definitions: list[dict[str, Any]],
    strategy_status_counts: Mapping[str, Any],
    orders: tuple[Mapping[str, Any], ...],
    positions: tuple[Mapping[str, Any], ...],
    alerts: tuple[Mapping[str, Any], ...],
    realized: Decimal,
    unrealized: Decimal,
    blocked: list[str],
    account: AccountRiskProjection,
    risk: Mapping[str, Any],
) -> dict[str, Any]:
    enabled_instruments = len({model.identity["instrument"] for model in read_models})
    critical_alerts = [item for item in alerts if item.get("severity") == "CRITICAL"]
    active_trades = [
        {
            "strategy": row["strategy"],
            "instrument": row["instrument"],
            "contract": row["contract"],
            "status": row["status_label"],
            "protection": row["protection_label"],
            "pnl": str(Decimal(str(row["realized_pnl"])) + Decimal(str(row["unrealized_pnl"]))),
        }
        for row in positions
        if row["health"].startswith("OPEN")
    ]
    pending_actions = []
    for model in read_models:
        if model.operations["alerts"]:
            pending_actions.append(
                {
                    "strategy_instance_id": model.identity["strategy_instance_id"],
                    "instrument": model.identity["instrument"],
                    "action": model.operations["alerts"][0]["code"],
                    "reason": model.operations["alerts"][0]["message"],
                }
            )
    return {
        "system_state": "DEGRADED" if blocked else "HEALTHY",
        "market_state": "DETERMINISTIC_SESSION",
        "broker_sessions": "READ_ONLY_OR_INTERNAL",
        "enabled_strategy_instances": len(read_models),
        "enabled_instruments": enabled_instruments,
        "plans_prepared": sum(1 for item in read_models if item.plan["plan_status"] == "PREPARED"),
        "blocked_instances": len(blocked),
        "active_orders": sum(1 for row in orders if row["state"] not in {"NO_ORDER", "REJECTED_INTERNAL"}),
        "pending_orders": sum(1 for row in orders if row["state"] not in {"NO_ORDER", "REJECTED_INTERNAL"}),
        "open_positions": sum(1 for row in positions if row["health"] == "OPEN_PROTECTED"),
        "unprotected_positions": sum(1 for row in positions if row["protection_status"] != "PROTECTED"),
        "realized_pnl": str(realized),
        "unrealized_pnl": str(unrealized),
        "daily_realized_pnl": str(realized),
        "daily_unrealized_pnl": str(unrealized),
        "margin_usage_pct": account.usage["margin_usage_pct"],
        "entry_available_instances": strategy_status_counts.get("global", {}).get("entry_available", 0),
        "carried_positions": strategy_status_counts.get("global", {}).get("carried", 0),
        "no_trade_instances": strategy_status_counts.get("global", {}).get("no_trade", 0),
        "critical_alerts": len(critical_alerts),
        "broker_data_session": "Read-only / Internal Paper",
        "last_market_update": max((model.state["last_update"] for model in read_models), default=None),
        "account_summary": {
            "account": account.display_name,
            "account_reference": account.account_reference,
            "available_margin": risk["aggregate"]["available_margin"],
            "reserved_margin": risk["aggregate"]["reserved_margin"],
            "used_margin": risk["aggregate"]["used_margin"],
            "risk_state": risk["aggregate"]["risk_state"],
        },
        "critical_alert_rows": [dict(item) for item in critical_alerts[:6]],
        "active_trades": active_trades,
        "pending_actions": pending_actions[:8],
        "strategy_definition_summaries": strategy_definitions,
        "strategy_health": [
            {
                "strategy_instance_id": model.identity["strategy_instance_id"],
                "strategy": model.identity["strategy"],
                "instrument": model.identity["instrument"],
                "health": model.state["health_label"],
                "evidence": model.state["evidence_quality_label"],
                "current_action": model.state["current_action_label"],
            }
            for model in read_models
        ],
        "market_session_timeline": [
            {"time": "09:15", "event": "Market Open", "status": "Observed"},
            {"time": "09:25", "event": "ORPT Window", "status": "Evaluated"},
            {"time": "09:30", "event": "RC Window", "status": "Evaluated"},
            {"time": "15:00", "event": "EOD Decision", "status": "Pending or completed by lifecycle"},
        ],
        "recent_operational_events": [
            {"time": model.state["last_update"], "event": model.execution["latest_event"], "instrument": model.identity["instrument"]}
            for model in read_models
        ],
    }


def _navigation_model(*, strategy_definitions: list[dict[str, Any]], strategy_status_counts: Mapping[str, Any]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    per_definition = strategy_status_counts.get("by_definition", {})
    for item in strategy_definitions:
        grouped[str(item["family"])].append(
            {
                "strategy_definition_id": item["strategy_definition_id"],
                "strategy_code": item["strategy_code"],
                "display_name": item["display_name"],
                "enabled_count": item["enabled_count"],
                "supported_count": item["supported_count"],
                "status_counts": per_definition.get(item["strategy_definition_id"], {}),
            }
        )
    return {
        "operator_mode": [
            "Command Centre",
            "Strategies",
            "Orders",
            "Positions",
            "Accounts",
            "Risk",
            "Historical Trades",
            "Alerts",
            "Audit",
            "Settings",
        ],
        "engineering_mode": [
            "Decision Explorer",
            "Monthly Status",
            "Contract Selection",
            "Manual Validation",
            "Replay",
            "Explanation Library",
            "Diagnostics",
            "Source Trace",
        ],
        "principal_areas": [
            "Command Centre",
            "Strategies",
            "Orders",
            "Positions",
            "Accounts",
            "Risk",
            "Historical Trades",
            "Alerts",
            "Audit",
            "Settings",
        ],
        "strategy_hierarchy": [
            "Strategy Family",
            "Strategy Definition",
            "Strategy Instance",
            "Instrument",
            "Contract",
            "Trade/Position",
        ],
        "strategy_groups": [
            {
                "family": family,
                "definitions": sorted(definitions, key=lambda item: (str(item["strategy_code"]), str(item["display_name"]))),
            }
            for family, definitions in sorted(grouped.items())
        ],
        "product_modes_share_backend_truth": True,
    }


def _is_blocked(model: StrategyInstanceReadModel) -> bool:
    return str(model.plan.get("plan_status") or "").upper() == "BLOCKED" or str(model.state.get("runtime_stage") or "").upper().startswith("BLOCKED")


def _is_qualified(model: StrategyInstanceReadModel) -> bool:
    return bool(model.plan.get("selected_contract")) and not _is_blocked(model)


def _is_entry_available(model: StrategyInstanceReadModel) -> bool:
    runtime_stage = str(model.state.get("runtime_stage") or "").upper()
    return runtime_stage in {"NORMAL_ENTRY_STILL_VALID", "RC_ENTRY_STILL_VALID", "ENTRY_AVAILABLE"}


def _is_no_trade(model: StrategyInstanceReadModel) -> bool:
    return str(model.execution.get("order_state") or "").upper() == "NO_ORDER" and not _is_entry_available(model) and not str(model.position.get("health") or "").upper().startswith("OPEN")


def _aggregate_health(health_values: set[str]) -> str:
    if any("DEGRADED" in value or "BLOCK" in value or "MISSING" in value for value in health_values):
        return "Needs review"
    return "Healthy"


def _estimated_margin_usage_pct(item: Mapping[str, Any]) -> int:
    if item.get("blocked"):
        return 0
    if str(item.get("position") or "").startswith("OPEN"):
        return 18
    if item.get("entry_available") or item.get("qualified"):
        return 9
    return 0


def _pretty_strategy_name(definition_id: str) -> str:
    text = str(definition_id).strip()
    if not text:
        return "Strategy"
    if text.startswith("S21"):
        return "S21 Monthly Option Selling"
    if text.startswith("S22"):
        return "S22 Stock Option Selling"
    if text.startswith("S23"):
        return "S23 Weekly Option Selling"
    return text.replace("_", " ").title()


def _side_from_branch(branch: str | None) -> str:
    text = str(branch or "").upper()
    if "CALL" in text:
        return "CALL SELL"
    if "PUT" in text:
        return "PUT SELL"
    return "UNKNOWN"


def _broker_name(market_data_source: str) -> str:
    if "FYERS" in market_data_source.upper():
        return "FYERS"
    if "FIXTURE" in market_data_source.upper():
        return "Internal Fixture"
    return market_data_source.replace("_", " ").title()


def _operator_label(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return STATE_LABELS.get(text, text.replace("_", " ").title())


def _pnl_tone(value: Any) -> str:
    amount = Decimal(str(value or "0"))
    if amount > 0:
        return "POSITIVE"
    if amount < 0:
        return "NEGATIVE"
    return "FLAT"


def _position_age_from_session(session_id: str) -> str:
    try:
        session_date = date.fromisoformat(session_id.split(":")[1])
    except (IndexError, ValueError):
        return "Unknown"
    return "1d" if session_date < date(2026, 8, 4) else "Intraday"


def execution_fill_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    execution = result["execution"]
    return {
        "fill_state": execution["fill_state"],
        "filled_quantity": execution["filled_quantity"],
        "latest_event": execution["latest_event"],
    }
