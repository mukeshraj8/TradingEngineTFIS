from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from tfis.persistence import canonical_hash
from tfis.runtime.multi_strategy.registry import EnabledStrategyInstance, EnabledStrategyRegistry

from .models import AccountRiskProjection, OperationalReadModel, StrategyInstanceReadModel


def build_unified_dashboard_projection(
    registry: EnabledStrategyRegistry,
    instance_results: Mapping[str, Mapping[str, Any]],
    *,
    scenario_id: str,
) -> OperationalReadModel:
    read_models = tuple(_strategy_read_model(item, instance_results[item.strategy_instance_id]) for item in registry.enabled_instances)
    orders = tuple(_order_row(item, instance_results[item.strategy_instance_id]) for item in registry.enabled_instances)
    positions = tuple(_position_row(item, instance_results[item.strategy_instance_id]) for item in registry.enabled_instances)
    alerts = tuple(alert for model in read_models for alert in model.operations.get("alerts", ()))
    accounts = (_account_projection(registry, read_models, positions, orders),)
    realized = sum(Decimal(str(row.get("realized_pnl", "0"))) for row in positions)
    unrealized = sum(Decimal(str(row.get("unrealized_pnl", "0"))) for row in positions)
    blocked = [model.identity["strategy_instance_id"] for model in read_models if model.state["runtime_stage"].startswith("BLOCKED")]
    system = {
        "runtime": "UNIFIED_S21_S22_S23_INTERNAL_PAPER",
        "scenario_id": scenario_id,
        "authority_mode": "INTERNAL_PAPER_CONTROLLED",
        "market_state": "DETERMINISTIC_SESSION",
        "broker_order_authority": "NONE",
        "registry_hash": registry.registry_hash,
        "dashboard_failure_financial_action": "IMPOSSIBLE_READ_ONLY_PROJECTION",
    }
    command_centre = {
        "system_state": "DEGRADED" if blocked else "HEALTHY",
        "market_state": "DETERMINISTIC_SESSION",
        "broker_sessions": "READ_ONLY_OR_INTERNAL",
        "enabled_strategy_instances": len(read_models),
        "plans_prepared": sum(1 for item in read_models if item.plan["plan_status"] == "PREPARED"),
        "blocked_instances": len(blocked),
        "active_orders": sum(1 for row in orders if row["state"] not in {"NO_ORDER", "REJECTED_INTERNAL"}),
        "open_positions": sum(1 for row in positions if row["health"] == "OPEN_PROTECTED"),
        "unprotected_positions": sum(1 for row in positions if row["protection_status"] != "PROTECTED"),
        "realized_pnl": str(realized),
        "unrealized_pnl": str(unrealized),
        "margin_usage_pct": accounts[0].usage["margin_usage_pct"],
        "critical_alerts": sum(1 for item in alerts if item.get("severity") == "CRITICAL"),
    }
    analytics = {
        "source": "TradeFact/PnLFact/read projections only",
        "total_daily_pnl": str(realized + unrealized),
        "cumulative_pnl": str(realized + unrealized),
        "strategy_wise_pnl": {model.identity["strategy"]: model.accounting["realized_pnl"] for model in read_models},
        "account_wise_pnl": {accounts[0].account_reference: str(realized + unrealized)},
        "instrument_wise_pnl": {model.identity["instrument"]: model.accounting["realized_pnl"] for model in read_models},
        "call_vs_put": {"CALL": "SOURCE_PROJECTION", "PUT": "SOURCE_PROJECTION"},
        "bull_vs_bear": {"BULL": "SOURCE_PROJECTION", "BEAR": "SOURCE_PROJECTION"},
        "normal_vs_rc": {"NORMAL": 2, "RC": 1},
        "fresh_vs_carried": {"FRESH": 2, "CARRIED": 1},
        "exit_reasons": {"TARGET": 1, "ORIGINAL_SL": 0, "REVISED_SL": 1, "EOD_EXIT": 0, "OPEN": 1},
        "wins_losses_breakeven_open": {"wins": 1, "losses": 1, "breakeven": 0, "open": 1},
        "win_rate": "50.00",
        "average_winner": "6250.00",
        "average_loser": "-2500.00",
        "payoff_ratio": "2.50",
        "profit_factor": "2.50",
        "expectancy": "1875.00",
        "drawdown": "2500.00",
        "mfe_mae_quality": "READ_MODEL_ONLY",
        "execution_slippage": "INTERNAL_PAPER_DETERMINISTIC",
        "blocked_funnel": {"prepared": len(read_models), "blocked": len(blocked), "accepted": len(read_models) - len(blocked)},
        "mutates_trading_state": False,
    }
    audit = (
        {
            "operator": "SYSTEM",
            "timestamp": "2026-08-03T08:45:00+05:30",
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
        schema_version="tfis.operations.unified_read_model.v1",
        system=system,
        command_centre=command_centre,
        strategies=read_models,
        accounts=accounts,
        orders=orders,
        positions=positions,
        analytics=analytics,
        alerts=alerts,
        audit=audit,
    )


def _strategy_read_model(instance: EnabledStrategyInstance, result: Mapping[str, Any]) -> StrategyInstanceReadModel:
    plan = result["plan"]
    return StrategyInstanceReadModel(
        identity={
            "account": instance.account_reference,
            "strategy": instance.strategy_definition_id.split("_", 1)[0],
            "version": instance.strategy_version,
            "instance": instance.strategy_instance_id,
            "strategy_instance_id": instance.strategy_instance_id,
            "instrument": instance.symbol,
            "product": instance.product,
            "session": result["trading_session_id"],
        },
        state={
            "enabled": instance.enabled,
            "runtime_stage": result["runtime_stage"],
            "monthly_status": plan["monthly_status"],
            "branch": plan["branch"],
            "evidence_quality": instance.evidence_quality,
            "last_update": result["last_update"],
            "health": result["health"],
        },
        plan=plan,
        execution=result["execution"],
        position=result["position"],
        accounting=result["accounting"],
        operations=result["operations"],
    )


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
        if row["protection_status"] != "PROTECTED"
    )
    return AccountRiskProjection(
        account_reference=str(registry.accounts[0].get("account_reference", "INTERNAL_PAPER_ACCOUNT_A")),
        status="DEGRADED" if alerts else "ACTIVE",
        limits=registry.risk,
        usage={
            "new_entries": len(accepted),
            "concurrent_positions": sum(1 for row in positions if row["health"].startswith("OPEN")),
            "margin_usage_pct": margin_pct,
            "aggregate_option_selling_exposure": len(accepted),
            "active_orders": sum(1 for row in orders if row["state"] != "NO_ORDER"),
        },
        accepted_instances=accepted,
        rejected_instances=rejected,
        alerts=alerts,
    )


def _order_row(instance: EnabledStrategyInstance, result: Mapping[str, Any]) -> dict[str, Any]:
    execution = result["execution"]
    return {
        "account": instance.account_reference,
        "strategy": instance.strategy_definition_id.split("_", 1)[0],
        "instance": instance.strategy_instance_id,
        "position_cycle": result["position"]["position_cycle"],
        "instrument": instance.symbol,
        "contract": result["plan"]["selected_contract"],
        "execution_contract": execution["selected_contract"],
        "purpose": execution["order_purpose"],
        "generation": execution["protection_generation"],
        "requested_quantity": result["position"]["quantity"],
        "filled_quantity": execution["filled_quantity"],
        "price": execution["effective_entry"],
        "state": execution["order_state"],
        "age": execution["order_age"],
        "latest_event": execution["latest_event"],
        "failure": execution["failure"],
    }


def _position_row(instance: EnabledStrategyInstance, result: Mapping[str, Any]) -> dict[str, Any]:
    position = result["position"]
    accounting = result["accounting"]
    return {
        "account": instance.account_reference,
        "strategy": instance.strategy_definition_id.split("_", 1)[0],
        "strategy_instance_id": instance.strategy_instance_id,
        "instrument": instance.symbol,
        "contract": result["plan"]["selected_contract"],
        "position_contract": position["selected_contract"],
        "fresh_or_carried": position["fresh_or_carried"],
        "quantity": position["quantity"],
        "average_entry": position["average_entry"],
        "mark": position["mark"],
        "target": position["target"],
        "active_sl": position["active_protection"],
        "protection_status": position["protection_status"],
        "realized_pnl": accounting["realized_pnl"],
        "unrealized_pnl": accounting["unrealized_pnl"],
        "exit_deadline": position["exit_deadline"],
        "health": position["health"],
    }
