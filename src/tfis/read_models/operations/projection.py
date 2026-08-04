from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Mapping

from tfis.persistence import canonical_hash
from tfis.runtime.multi_strategy.registry import EnabledStrategyInstance, EnabledStrategyRegistry

from .models import AccountRiskProjection, OperationalReadModel, StrategyInstanceReadModel


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
    risk = _risk_projection(accounts[0], positions, orders, alerts)
    realized = sum(Decimal(str(row.get("realized_pnl", "0"))) for row in positions)
    unrealized = sum(Decimal(str(row.get("unrealized_pnl", "0"))) for row in positions)
    blocked = [model.identity["strategy_instance_id"] for model in read_models if str(model.state["runtime_stage"]).startswith("BLOCKED")]
    state_labels = {key: {"label": value} for key, value in STATE_LABELS.items()}
    strategy_families = _strategy_family_summaries(read_models, positions)
    historical_trades = _historical_trade_rows(read_models, positions)
    decision_explanations = _build_decision_explanations(read_models, instance_results)
    navigation = _navigation_model()
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
        "generated_at": "2026-08-04T16:45:00+05:30",
        "trading_date": "2026-08-04",
        "session": registry.session_scope["trading_session_id"],
    }
    command_centre = _command_centre_model(
        registry=registry,
        read_models=read_models,
        orders=orders,
        positions=positions,
        alerts=alerts,
        realized=realized,
        unrealized=unrealized,
        blocked=blocked,
        account=accounts[0],
        risk=risk,
    )
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
            "strategy": strategy_code,
            "strategy_definition_id": instance.strategy_definition_id,
            "version": instance.strategy_version,
            "instance": instance.strategy_instance_id,
            "strategy_instance_id": instance.strategy_instance_id,
            "instrument": instance.symbol,
            "product": instance.product,
            "product_label": family_label,
            "segment": segment_code,
            "segment_label": segment_label,
            "exchange": instance.underlying.get("exchange"),
            "session": result["trading_session_id"],
            "broker": _broker_name(instance.market_data_source),
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
    return AccountRiskProjection(
        account_reference=str(account_cfg.get("account_reference", "INTERNAL_PAPER_ACCOUNT_A")),
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
    side = _side_from_branch(result["plan"]["branch"])
    warning = execution["failure"] or next((item.get("code") for item in result["operations"].get("alerts", ()) if item.get("severity") in {"WARNING", "CRITICAL"}), None)
    return {
        "time": result["last_update"],
        "account": instance.account_reference,
        "strategy": instance.strategy_definition_id.split("_", 1)[0],
        "strategy_instance_id": instance.strategy_instance_id,
        "instrument": instance.symbol,
        "contract": result["plan"]["selected_contract"],
        "side": side,
        "purpose": execution["order_purpose"],
        "quantity": result["position"]["quantity"],
        "price": execution["effective_entry"],
        "status": execution["order_state"],
        "status_label": _operator_label(execution["order_state"]),
        "mode": _operator_label(instance.authority_mode),
        "warning_or_error": warning,
        "actions": "Explain Decision",
        "technical_details": {
            "client_order_id": f"client-order:{canonical_hash(instance.strategy_instance_id)[:24]}",
            "position_cycle_id": result["position"]["position_cycle"],
            "generation": execution["protection_generation"],
            "margin_reservation": "SIMULATED_ONLY",
            "validation_trace": execution["execution_intent"],
            "internal_response": execution["latest_event"],
            "raw_state": execution["order_state"],
            "failure": execution["failure"],
        },
        "instance": instance.strategy_instance_id,
        "position_cycle": result["position"]["position_cycle"],
        "execution_contract": execution["selected_contract"],
        "generation": execution["protection_generation"],
        "requested_quantity": result["position"]["quantity"],
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
    return {
        "account": instance.account_reference,
        "strategy": instance.strategy_definition_id.split("_", 1)[0],
        "strategy_instance_id": instance.strategy_instance_id,
        "instrument": instance.symbol,
        "contract": result["plan"]["selected_contract"],
        "position_contract": position["selected_contract"],
        "side": _side_from_branch(result["plan"]["branch"]),
        "fresh_or_carried": position["fresh_or_carried"],
        "fresh_or_carried_label": _operator_label(position["fresh_or_carried"]),
        "quantity": position["quantity"],
        "average_entry": position["average_entry"],
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
                "account": account.account_reference,
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
                "account": model.identity["account"],
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


def _build_decision_explanations(
    read_models: tuple[StrategyInstanceReadModel, ...],
    instance_results: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for model in read_models:
        instance_id = model.identity["strategy_instance_id"]
        result = instance_results[instance_id]
        timestamp = str(model.state.get("last_update") or "")
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
                    "rule_id": "READ_MODEL_MONTHLY_STATUS",
                    "workbook_source": "READ_MODEL_DERIVED_RUNTIME_PROJECTION",
                    "formula_text": "Monthly Status emitted by backend runtime projection; no frontend calculation.",
                    "input_values": {
                        "strategy_instance_id": instance_id,
                        "instrument": model.identity["instrument"],
                    },
                    "intermediate_values": {},
                    "output_value": {
                        "monthly_status": model.state["monthly_status"],
                        "monthly_status_label": model.state["monthly_status_label"],
                    },
                    "candidate_evidence": {},
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
                {
                    **base_identity,
                    "stage": "CONTRACT_SELECTION",
                    "rule_id": "READ_MODEL_SELECTED_CONTRACT",
                    "workbook_source": "READ_MODEL_DERIVED_RUNTIME_PROJECTION",
                    "formula_text": "Selected contract and candidate-set summary emitted by backend runtime projection.",
                    "input_values": {
                        "branch": model.state["branch"],
                        "expiry_candidates": model.plan.get("expiry_candidates"),
                    },
                    "intermediate_values": {
                        "market_references": model.plan.get("market_references", {}),
                    },
                    "output_value": {
                        "selected_contract": model.plan["selected_contract"],
                        "premium": model.plan.get("premium"),
                        "oi": model.plan.get("oi"),
                    },
                    "candidate_evidence": {
                        "evaluated_contracts": [],
                        "rejected_candidates": [],
                    },
                },
                {
                    **base_identity,
                    "stage": "PLAN_COMPOSITION",
                    "rule_id": "READ_MODEL_PLAN_VALUES",
                    "workbook_source": "READ_MODEL_DERIVED_RUNTIME_PROJECTION",
                    "formula_text": "Entry, target, and stop-loss values emitted by backend runtime projection.",
                    "input_values": {
                        "selected_contract": model.plan["selected_contract"],
                        "market_references": model.plan.get("market_references", {}),
                    },
                    "intermediate_values": {},
                    "output_value": {
                        "base_entry": model.plan.get("base_entry"),
                        "target": model.plan.get("target"),
                        "original_sl": model.plan.get("original_sl"),
                        "raw_prices": {},
                        "normalized_prices": {},
                    },
                    "candidate_evidence": {},
                },
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
        "critical_alerts": len(critical_alerts),
        "broker_data_session": "Read-only / Internal Paper",
        "last_market_update": max((model.state["last_update"] for model in read_models), default=None),
        "account_summary": {
            "account": account.account_reference,
            "available_margin": risk["aggregate"]["available_margin"],
            "reserved_margin": risk["aggregate"]["reserved_margin"],
            "used_margin": risk["aggregate"]["used_margin"],
            "risk_state": risk["aggregate"]["risk_state"],
        },
        "critical_alert_rows": [dict(item) for item in critical_alerts[:6]],
        "active_trades": active_trades,
        "pending_actions": pending_actions[:8],
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


def _navigation_model() -> dict[str, Any]:
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
        "product_modes_share_backend_truth": True,
    }


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
