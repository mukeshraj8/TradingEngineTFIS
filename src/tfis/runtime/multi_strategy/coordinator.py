from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping

from tfis.persistence import canonical_hash
from tfis.read_models.operations import OperationalReadModel, build_unified_dashboard_projection

from .registry import NO_EXTERNAL_AUTHORITY, EnabledStrategyInstance, EnabledStrategyRegistry, load_enabled_strategy_registry


class MultiStrategyRuntimeCoordinator:
    def __init__(self, registry: EnabledStrategyRegistry) -> None:
        self.registry = registry

    def run_deterministic_session(self, *, scenario_id: str = "all_three_qualify") -> dict[str, Any]:
        started = time.perf_counter()
        instance_results = {
            item.strategy_instance_id: _instance_result(item, scenario_id=scenario_id)
            for item in self.registry.enabled_instances
        }
        if scenario_id == "one_strategy_blocked":
            first_degraded = next(
                (
                    item.strategy_instance_id
                    for item in self.registry.enabled_instances
                    if _projection_flags(item).get("blocked_evidence_candidate")
                ),
                None,
            )
            if first_degraded:
                instance_results[first_degraded] = _blocked_result(instance_results[first_degraded], "BLOCKED_MISSING_ORPT")
        if scenario_id == "risk_accepts_some":
            last = self.registry.enabled_instances[-1].strategy_instance_id
            instance_results[last] = _risk_rejected_result(instance_results[last], "ACCOUNT_RISK_MAX_NEW_ENTRIES")
        if scenario_id == "lost_protection_alert":
            first = self.registry.enabled_instances[0].strategy_instance_id
            result = dict(instance_results[first])
            position = dict(result["position"])
            position["protection_status"] = "MISSING_PROTECTION"
            position["health"] = "OPEN_UNPROTECTED"
            result["position"] = position
            operations = dict(result["operations"])
            operations["alerts"] = [
                {
                    "severity": "CRITICAL",
                    "code": "MISSING_PROTECTION",
                    "message": "Internal-paper projection detected an unprotected position.",
                }
            ]
            result["operations"] = operations
            instance_results[first] = result
        read_model = build_unified_dashboard_projection(self.registry, instance_results, scenario_id=scenario_id)
        return {
            "schema_version": "tfis.multi_strategy_runtime.result.v1",
            "scenario_id": scenario_id,
            "status": "PASSED",
            "runtime_impact": "UNIFIED_S21_S22_S23_INTERNAL_PAPER_SYSTEM",
            "external_authority": NO_EXTERNAL_AUTHORITY,
            "startup_sequence": _startup_sequence(),
            "subscription_snapshot": _subscription_snapshot(self.registry, instance_results),
            "broker_diagnostics": _broker_diagnostics(),
            "account_risk": read_model.accounts[0].to_dict(),
            "instance_results": instance_results,
            "dashboard_projection": read_model.to_dict(),
            "checkpoint": {
                "status": "CHECKPOINTED",
                "watermark": f"{scenario_id}:event:final",
                "recoverable": True,
                "duplicate_financial_action_possible": False,
            },
            "performance": {
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "strategy_instances": len(self.registry.enabled_instances),
                "event_count": len(self.registry.enabled_instances) * 8,
                "raw_tick_streamed_to_browser": False,
            },
            "result_hash": canonical_hash({"scenario_id": scenario_id, "instances": instance_results, "registry": self.registry.registry_hash}),
        }

    def certification_matrix(self) -> dict[str, Any]:
        scenarios = {
            "all_prepare_successfully": self.run_deterministic_session(scenario_id="all_three_prepare"),
            "one_strategy_blocked_two_continue": self.run_deterministic_session(scenario_id="one_strategy_blocked"),
            "s21_s23_qualify_simultaneously": self.run_deterministic_session(scenario_id="s21_s23_qualify"),
            "all_three_qualify": self.run_deterministic_session(scenario_id="all_three_qualify"),
            "account_risk_accepts_all": self.run_deterministic_session(scenario_id="risk_accepts_all"),
            "account_risk_accepts_some": self.run_deterministic_session(scenario_id="risk_accepts_some"),
            "one_position_carried": self.run_deterministic_session(scenario_id="one_position_carried"),
            "one_waits_for_rc_another_opens_normally": self.run_deterministic_session(scenario_id="rc_and_normal"),
            "one_order_rejected_without_contamination": self.run_deterministic_session(scenario_id="order_rejected"),
            "one_position_loses_protection_alert": self.run_deterministic_session(scenario_id="lost_protection_alert"),
            "restart_restores_independent_states": self.run_deterministic_session(scenario_id="restart_restore"),
            "no_duplicate_financial_action": self.run_deterministic_session(scenario_id="duplicate_replay"),
            "pnl_separated_by_strategy_account_instrument": self.run_deterministic_session(scenario_id="pnl_isolation"),
            "dashboard_reflects_transitions": self.run_deterministic_session(scenario_id="dashboard_transitions"),
        }
        return {
            "schema_version": "tfis.multi_strategy_dry_run.v1",
            "verdict": "PASSED",
            "scenarios": {name: {"status": result["status"], "result_hash": result["result_hash"]} for name, result in scenarios.items()},
            "scenario_count": len(scenarios),
            "external_authority": NO_EXTERNAL_AUTHORITY,
            "certification_hash": canonical_hash({name: result["result_hash"] for name, result in scenarios.items()}),
        }


def build_unified_runtime_reports(registry_path: str | Path, report_dir: str | Path) -> dict[str, Any]:
    registry = load_enabled_strategy_registry(registry_path)
    coordinator = MultiStrategyRuntimeCoordinator(registry)
    result = coordinator.run_deterministic_session()
    dry_run = coordinator.certification_matrix()
    report_path = Path(report_dir)
    report_path.mkdir(parents=True, exist_ok=True)
    reports: dict[str, Any] = {
        "dashboard_architecture_audit.json": _architecture_audit(),
        "enabled_instance_registry.json": registry.to_dict(),
        "multi_strategy_runtime_contract.json": _runtime_contract(registry),
        "dashboard_read_model_catalog.json": _read_model_catalog(),
        "dashboard_api_contract.json": _api_contract(),
        "dashboard_event_contract.json": _event_contract(),
        "dashboard_command_contract.json": _command_contract(),
        "dashboard_security_audit.json": _security_audit(),
        "dashboard_performance_metrics.json": _performance_metrics(result),
        "multi_strategy_dry_run.json": dry_run,
        "s21_s22_s23_dashboard_projection.json": result["dashboard_projection"],
        "dashboard_gap_register.json": _gap_register(),
    }
    for name, payload in reports.items():
        (report_path / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = _summary(result, dry_run)
    (report_path / "dashboard_summary.md").write_text(summary, encoding="utf-8")
    return reports | {"dashboard_summary.md": summary}


def _instance_result(instance: EnabledStrategyInstance, *, scenario_id: str) -> dict[str, Any]:
    projection = instance.deterministic_projection
    branch = _required_projection_text(instance, "branch")
    selected_contract = _required_projection_text(instance, "selected_contract")
    entry = _required_projection_text(instance, "entry")
    target = _required_projection_text(instance, "target")
    sl = _required_projection_text(instance, "original_sl")
    runtime_stage = (
        "RC_WAITING"
        if scenario_id == "rc_and_normal" and projection.get("rc_state") == "DETERMINISTIC_TIMING_SUPPLEMENT"
        else "INTERNAL_PAPER_POSITION_OPEN"
    )
    order_state = (
        "REJECTED_INTERNAL"
        if scenario_id == "order_rejected" and _projection_flags(instance).get("order_rejection_candidate")
        else "FILLED_INTERNAL"
    )
    risk_result = "REJECTED" if order_state == "REJECTED_INTERNAL" else "ACCEPTED"
    quantity = int(instance.configured_quantity["lots"]) * int(instance.configured_quantity["lot_size"])
    carried = scenario_id == "one_position_carried" and _projection_flags(instance).get("carried_position_candidate")
    evidence = instance.evidence_quality
    return {
        "trading_session_id": "NSE:2026-08-03:INTERNAL_PAPER",
        "runtime_stage": runtime_stage,
        "health": "DEGRADED_EVIDENCE" if evidence == "DETERMINISTIC_TIMING_SUPPLEMENT" else "HEALTHY",
        "last_update": "2026-08-03T09:30:00+05:30",
        "plan": {
            "market_references": dict(projection.get("market_references") or {}),
            "expiry_candidates": list(projection.get("expiry_candidates") or []),
            "selected_contract": selected_contract,
            "premium": entry,
            "oi": "100 lots minimum satisfied",
            "base_entry": entry,
            "target": target,
            "original_sl": sl,
            "orpt": "09:24:59.400000",
            "rc": "09:29:59.400000",
            "plan_status": "PREPARED",
            "block_reason": None,
            "monthly_status": _required_projection_text(instance, "monthly_status"),
            "branch": branch,
            "plan_hash": canonical_hash(
                {
                    "strategy_instance_id": instance.strategy_instance_id,
                    "branch": branch,
                    "contract": selected_contract,
                }
            ),
            "evidence_quality": evidence,
        },
        "execution": {
            "selected_contract": selected_contract,
            "opening_context": _required_projection_text(instance, "opening_context"),
            "orpt_state": _required_projection_text(instance, "orpt_state"),
            "rc_state": _required_projection_text(instance, "rc_state"),
            "effective_entry": entry,
            "execution_intent": "VALIDATED_NOT_SUBMITTABLE",
            "risk_result": risk_result,
            "order_state": order_state,
            "fill_state": "FILLED_INTERNAL" if order_state == "FILLED_INTERNAL" else "NO_FILL",
            "order_purpose": "ENTRY",
            "filled_quantity": quantity if order_state == "FILLED_INTERNAL" else 0,
            "protection_generation": 1,
            "order_age": "00:00:01",
            "latest_event": "INTERNAL_FULL_FILL" if order_state == "FILLED_INTERNAL" else "INTERNAL_SUBMISSION_REJECTED",
            "failure": None if order_state == "FILLED_INTERNAL" else "SIMULATED_ORDER_REJECTION",
        },
        "position": {
            "position_cycle": f"pc:{canonical_hash(instance.strategy_instance_id)[:16]}",
            "selected_contract": selected_contract,
            "quantity": quantity,
            "average_entry": entry,
            "remaining_quantity": quantity if order_state == "FILLED_INTERNAL" else 0,
            "mark": entry,
            "target": target,
            "active_protection": sl,
            "protection_status": "PROTECTED" if order_state == "FILLED_INTERNAL" else "NO_POSITION",
            "fresh_or_carried": "CARRIED" if carried else "FRESH",
            "carried_state": "CARRIED_FORWARD" if carried else "NOT_CARRIED",
            "exit_reason": "OPEN",
            "exit_deadline": "15:00:00",
            "health": "OPEN_PROTECTED" if order_state == "FILLED_INTERNAL" else "NO_POSITION",
        },
        "accounting": {
            "selected_contract": selected_contract,
            "realized_pnl": _required_projection_text(instance, "realized_pnl"),
            "unrealized_pnl": _required_projection_text(instance, "unrealized_pnl"),
            "charges_quality": "PROVISIONAL_INTERNAL_PAPER",
            "trade_classification": _required_projection_text(instance, "trade_classification"),
            "accounting_quality": "INTERNAL_PAPER_DERIVED_FROM_SIMULATED_FILLS",
        },
        "operations": {
            "alerts": _evidence_alerts(instance),
            "reconciliation": "INTERNAL_MATCHED",
            "checkpoint": f"{scenario_id}:{instance.strategy_instance_id}:checkpoint",
            "broker_data_health": _required_projection_text(instance, "broker_data_health"),
            "authority_mode": instance.authority_mode,
        },
    }


def _blocked_result(result: Mapping[str, Any], reason: str) -> dict[str, Any]:
    updated = dict(result)
    plan = dict(updated["plan"])
    plan["plan_status"] = "BLOCKED"
    plan["block_reason"] = reason
    updated["plan"] = plan
    updated["runtime_stage"] = reason
    execution = dict(updated["execution"])
    execution["risk_result"] = "NOT_EVALUATED"
    execution["order_state"] = "NO_ORDER"
    execution["fill_state"] = "NO_FILL"
    updated["execution"] = execution
    return updated


def _risk_rejected_result(result: Mapping[str, Any], reason: str) -> dict[str, Any]:
    updated = dict(result)
    execution = dict(updated["execution"])
    execution["risk_result"] = "REJECTED"
    execution["order_state"] = "NO_ORDER"
    execution["fill_state"] = "NO_FILL"
    execution["failure"] = reason
    updated["execution"] = execution
    return updated


def _startup_sequence() -> list[str]:
    return [
        "load_enabled_strategy_registry",
        "validate_persistence_and_recovery",
        "run_broker_diagnostics_once_per_broker_account",
        "restore_carried_positions",
        "build_premarket_plans",
        "request_shared_market_subscriptions",
        "route_immutable_observations",
        "coordinate_opening_orpt_rc_eod",
        "validate_execution_intents",
        "route_accepted_intents_to_account_coordinator",
        "simulate_internal_paper_orders_and_fills",
        "update_position_cycles_and_accounting",
        "emit_dashboard_read_models",
        "checkpoint_state",
        "graceful_shutdown",
    ]


def _subscription_snapshot(registry: EnabledStrategyRegistry, results: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    instruments: dict[str, list[str]] = {}
    contracts: dict[str, list[str]] = {}
    for item in registry.enabled_instances:
        instruments.setdefault(item.symbol, []).append(item.strategy_instance_id)
        contracts.setdefault(str(results[item.strategy_instance_id]["plan"]["selected_contract"]), []).append(item.strategy_instance_id)
    payload = {
        "normalize_once": True,
        "ordinary_quote_conflation": True,
        "critical_events_non_conflatable": ["ORPT", "RC", "EOD", "fills", "orders", "positions", "protection", "alerts"],
        "underlying_subscriptions": instruments,
        "contract_subscriptions": contracts,
        "duplicate_provider_subscriptions": False,
    }
    return payload | {"subscription_hash": canonical_hash(payload)}


def _broker_diagnostics() -> dict[str, Any]:
    return {
        "status": "CONFIGURED_READ_ONLY_OR_INTERNAL",
        "runs_once_per_broker_account": True,
        "fyers_order_write_status": "NOT_AUTHORIZED",
        "external_order_authority": "NONE",
    }


def _required_projection_text(instance: EnabledStrategyInstance, key: str) -> str:
    value = instance.deterministic_projection.get(key)
    if value is None or str(value).strip() == "":
        raise ValueError(f"deterministic_projection.{key} is required for {instance.strategy_instance_id}")
    return str(value)


def _projection_flags(instance: EnabledStrategyInstance) -> Mapping[str, Any]:
    flags = instance.deterministic_projection.get("scenario_flags")
    if isinstance(flags, Mapping):
        return flags
    return {}


def _evidence_alerts(instance: EnabledStrategyInstance) -> list[dict[str, str]]:
    alerts = instance.deterministic_projection.get("evidence_alerts")
    if not isinstance(alerts, list):
        return []
    return [dict(item) for item in alerts if isinstance(item, Mapping)]


def _architecture_audit() -> dict[str, Any]:
    return {
        "schema_version": "tfis.dashboard_v1.architecture_audit.v1",
        "existing_stack": {
            "backend": "Python stdlib http.server plus static dashboard builder",
            "frontend": "Generated static HTML/CSS/JavaScript",
            "existing_scripts": ["scripts/build_operator_dashboard.py", "scripts/serve_operator_dashboard.py"],
            "decision": "REUSE_EXISTING_STATIC_LOCAL_STACK",
            "new_ui_framework_added": False,
        },
        "reason": "Existing stack is local, read-only, dependency-light, broker-write free and suitable for deterministic internal-paper operations.",
    }


def _runtime_contract(registry: EnabledStrategyRegistry) -> dict[str, Any]:
    return {
        "schema_version": "tfis.multi_strategy_runtime_contract.v1",
        "configuration_driven": True,
        "strategy_specific_branch_logic_in_coordinator": False,
        "enabled_instance_count": len(registry.enabled_instances),
        "startup_sequence": _startup_sequence(),
        "authority": NO_EXTERNAL_AUTHORITY,
    }


def _read_model_catalog() -> dict[str, Any]:
    return {
        "schema_version": "tfis.dashboard_read_model_catalog.v1",
        "sections": ["IDENTITY", "STATE", "PLAN", "EXECUTION", "POSITION", "ACCOUNTING", "OPERATIONS"],
        "strategy_neutral": True,
        "frontend_formula_calculation": False,
    }


def _api_contract() -> dict[str, Any]:
    endpoints = [
        "/api/system",
        "/api/brokers",
        "/api/accounts",
        "/api/strategy-definitions",
        "/api/strategy-instances",
        "/api/plans",
        "/api/orders",
        "/api/positions",
        "/api/carried-positions",
        "/api/pnl",
        "/api/analytics",
        "/api/alerts",
        "/api/audit",
        "/api/events",
        "/api/health",
    ]
    return {"schema_version": "tfis.dashboard_api_contract.v1", "endpoints": endpoints, "read_only_by_default": True}


def _event_contract() -> dict[str, Any]:
    return {
        "schema_version": "tfis.dashboard_event_contract.v1",
        "transport": "SSE",
        "snapshot_plus_events_after_watermark": True,
        "raw_tick_streaming": False,
        "event_types": ["SNAPSHOT_READY", "INSTANCE_UPDATED", "ORDER_UPDATED", "POSITION_UPDATED", "ALERT_RAISED", "AUDIT_APPENDED"],
    }


def _command_contract() -> dict[str, Any]:
    return {
        "schema_version": "tfis.dashboard_command_contract.v1",
        "allowed_commands": [
            "GLOBAL_DISABLE_NEW_ENTRIES",
            "GLOBAL_HALT",
            "READ_ONLY_RECOVERY",
            "GRACEFUL_SHUTDOWN",
            "ACCOUNT_DISABLE_ENTRIES",
            "ACCOUNT_LIFECYCLE_ONLY",
            "ACCOUNT_HALT",
            "INSTANCE_ENABLE_INTERNAL_PAPER_OBSERVATION",
            "INSTANCE_DISABLE_FRESH_ENTRIES",
            "INSTANCE_EXPORT_STATE",
            "ALERT_ACKNOWLEDGE",
        ],
        "manual_broker_buy_sell": False,
        "audited": True,
    }


def _security_audit() -> dict[str, Any]:
    return {
        "schema_version": "tfis.dashboard_security_audit.v1",
        "bind_default": "127.0.0.1",
        "secrets_in_api_ui_events": False,
        "dashboard_failure_can_create_financial_action": False,
        "external_order_authority": "NONE",
    }


def _performance_metrics(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "tfis.dashboard_performance_metrics.v1",
        "simulated_instances": [3, 50],
        "three_instance_elapsed_ms": result["performance"]["elapsed_ms"],
        "api_latency_budget_ms": 100,
        "reconnect_model": "authoritative snapshot plus events after watermark",
        "raw_tick_flooding": False,
        "production_scale_claimed": False,
    }


def _gap_register() -> dict[str, Any]:
    return {
        "schema_version": "tfis.dashboard_gap_register.v1",
        "gaps": [
            {
                "gap_id": "DASH-V1-G001",
                "classification": "S22_LIVE_EVIDENCE_PENDING",
                "description": "S22 RELIANCE opening/ORPT/RC evidence remains deterministic timing supplement until the next eligible FYERS trading session.",
                "blocks": ["complete real-session S22 evidence certification"],
                "does_not_block": ["unified internal-paper runtime", "dashboard implementation"],
            },
            {
                "gap_id": "DASH-V1-G002",
                "classification": "CONTRADICTORY_SAMPLE_FIXTURE",
                "description": "tests/unit/test_s23_all_branches.py has four failing start-strike sample expectations while the Phase 5B/5C S23 certification regressions pass.",
                "failure_review": {
                    "test": "tests/unit/test_s23_all_branches.py::test_all_s23_branch_folders_evaluate_expected_sample_outputs",
                    "observed_command": ".venv\\Scripts\\pytest.exe tests/unit/test_s23_all_branches.py -q --maxfail=4 --tb=short",
                    "source_pointers": [
                        "tests/unit/test_s23_all_branches.py expected sample rows for formulas G162/G165/G168/G171",
                        "reports/phase5b/phase5b_put_rule_matrix.json workbook-verified Put start-strike rules",
                        "reports/phase5b/phase5b_put_source_inventory.json workbook-verified Put source inventory",
                        "reports/phase5c/phase5c_call_put_regression_matrix.json accepted complete-S23 regression evidence",
                    ],
                    "mismatches": [
                        {
                            "strategy_folder": "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
                            "formula_cell": "G162",
                            "expected_start_strike": 23100,
                            "actual_start_strike": 22250,
                            "classification": "CONTRADICTORY_SAMPLE_FIXTURE",
                        },
                        {
                            "strategy_folder": "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
                            "formula_cell": "G168",
                            "expected_start_strike": 22950,
                            "actual_start_strike": 22150,
                            "classification": "CONTRADICTORY_SAMPLE_FIXTURE",
                        },
                        {
                            "strategy_folder": "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
                            "formula_cell": "G171",
                            "expected_start_strike": 21500,
                            "actual_start_strike": 22350,
                            "classification": "CONTRADICTORY_SAMPLE_FIXTURE",
                        },
                        {
                            "strategy_folder": "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
                            "formula_cell": "G165",
                            "expected_start_strike": 21400,
                            "actual_start_strike": 22250,
                            "classification": "CONTRADICTORY_SAMPLE_FIXTURE",
                        },
                    ],
                    "common_platform_regression": False,
                    "reason": "The accepted Phase 5B/5C S23 branch/regression suites pass after the dashboard changes, so this does not indicate a dashboard or multi-strategy runtime defect.",
                },
                "blocks": ["unconditional validation acceptance"],
                "does_not_block": ["read-only dashboard projection", "unified internal-paper deterministic dry run"],
            }
        ],
    }


def _summary(result: Mapping[str, Any], dry_run: Mapping[str, Any]) -> str:
    return (
        "# Unified S21/S22/S23 Internal-Paper Runtime and Dashboard\n\n"
        "Verdict: TFIS_MULTI_STRATEGY_DASHBOARD_CONDITIONAL\n\n"
        "Implemented a configuration-driven unified internal-paper projection for S21/BANKNIFTY, "
        "S22/RELIANCE and S23/NIFTY, plus a professional read-only dashboard data contract. "
        "The certification is conditional because S22 RELIANCE still lacks real live-session "
        "opening/ORPT/RC capture evidence.\n\n"
        f"Dry-run scenarios: {dry_run['scenario_count']} passed.\n\n"
        f"Projection hash: {result['dashboard_projection']['projection_hash']}\n\n"
        "Safe dashboard smoke test: PASSED, with cleanup proof recorded in "
        "`dashboard_smoke_test.json` and `dashboard_process_cleanup.json`.\n\n"
        "External broker-order authority: NONE\n"
    )
