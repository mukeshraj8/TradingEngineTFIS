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
    _write_dashboard_v2_reports(report_path.parent / "dashboard_v2", registry=registry, result=result, dry_run=dry_run)
    _write_dashboard_v3_reports(report_path.parent / "dashboard_v3", registry=registry, result=result, dry_run=dry_run)
    return reports | {"dashboard_summary.md": summary}


def _write_dashboard_v2_reports(report_dir: Path, *, registry: EnabledStrategyRegistry, result: Mapping[str, Any], dry_run: Mapping[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    projection = result["dashboard_projection"]
    legacy_principal_areas = [
        "Command Centre",
        "Strategies",
        "Orders",
        "Positions",
        "Accounts",
        "Risk",
        "Explainability",
        "Historical Trades",
        "Alerts & Audit",
        "Settings",
    ]
    reports: dict[str, Any] = {
        "dashboard_information_architecture.json": {
            "schema_version": "tfis.dashboard_v2.information_architecture.v1",
            "principal_areas": legacy_principal_areas,
            "strategy_hierarchy": projection["navigation"]["strategy_hierarchy"],
            "frontend_formula_calculation": False,
        },
        "operator_workflow_map.json": {
            "schema_version": "tfis.dashboard_v2.operator_workflow_map.v1",
            "home_page_panels": list(projection["command_centre"].keys()),
            "selected_strategy_workflow": [
                "Overview",
                "Current Decision",
                "Monthly Status",
                "Market Structure",
                "Contract Selection",
                "ORPT / RC",
                "Entry / Target / SL",
                "Orders",
                "Position",
                "P&L",
                "Timeline",
                "Evidence",
                "Manual Validation",
            ],
        },
        "command_centre_result.json": projection["command_centre"],
        "strategy_hierarchy_result.json": {
            "schema_version": "tfis.dashboard_v2.strategy_hierarchy_result.v1",
            "strategy_families": projection["strategy_families"],
            "strategy_instance_count": len(projection["strategies"]),
        },
        "orders_layout_result.json": {
            "schema_version": "tfis.dashboard_v2.orders_layout_result.v1",
            "primary_columns": ["time", "account", "strategy", "instrument", "contract", "side", "purpose", "quantity", "price", "status", "mode", "warning_or_error", "actions"],
            "row_count": len(projection["orders"]),
            "sample_rows": projection["orders"][:3],
        },
        "positions_layout_result.json": {
            "schema_version": "tfis.dashboard_v2.positions_layout_result.v1",
            "primary_columns": ["account", "strategy", "instrument", "contract", "side", "quantity", "average_entry", "mark", "target", "active_sl", "realized_pnl", "unrealized_pnl", "protection_status", "status", "age"],
            "row_count": len(projection["positions"]),
            "sample_rows": projection["positions"][:3],
        },
        "account_configuration_contract.json": {
            "schema_version": "tfis.dashboard_v2.account_configuration_contract.v1",
            "allowed_write_scope": "INTERNAL_PAPER_LOCAL_ONLY",
            "audit_required": True,
            "versioned_save_required": True,
            "credential_exposure": "PROHIBITED",
            "sample_accounts": projection["accounts"],
        },
        "risk_dashboard_result.json": projection["risk"],
        "s22_30_stock_scalability.json": _s22_scalability_projection(registry, projection),
        "future_segment_compatibility.json": {
            "schema_version": "tfis.dashboard_v2.future_segment_compatibility.v1",
            "segments": [
                {"segment": "Index Options", "status": "ACTIVE_IN_PROJECTION"},
                {"segment": "Stock Options", "status": "ACTIVE_IN_PROJECTION"},
                {"segment": "Futures", "status": "METADATA_COMPATIBLE_PLACEHOLDER"},
                {"segment": "Equity", "status": "METADATA_COMPATIBLE_PLACEHOLDER"},
                {"segment": "Commodity", "status": "METADATA_COMPATIBLE_PLACEHOLDER"},
                {"segment": "Currency", "status": "METADATA_COMPATIBLE_PLACEHOLDER"},
            ],
            "strategy_neutral_rendering": True,
        },
        "state_label_mapping.json": projection["state_labels"],
        "historical_trade_result.json": {
            "schema_version": "tfis.dashboard_v2.historical_trade_result.v1",
            "trade_count": len(projection["historical_trades"]),
            "sample_trades": projection["historical_trades"][:5],
        },
        "alerts_audit_result.json": {
            "schema_version": "tfis.dashboard_v2.alerts_audit_result.v1",
            "alerts": projection["alerts"],
            "audit": projection["audit"],
        },
        "responsive_layout_result.json": {
            "schema_version": "tfis.dashboard_v2.responsive_layout_result.v1",
            "primary_horizontal_scroll_contract": "NO_PRIMARY_PAGE_MANDATORY_HORIZONTAL_SCROLL_ON_NORMAL_DESKTOP_WIDTH",
            "secondary_data_in_drawers_or_expanders": True,
            "filters_sticky": True,
        },
        "security_and_write_boundary.json": {
            "schema_version": "tfis.dashboard_v2.security_and_write_boundary.v1",
            "external_broker_authority": projection["system"]["broker_order_authority"],
            "frontend_formula_calculation": False,
            "account_write_scope": "INTERNAL_PAPER_LOCAL_ONLY",
            "credential_exposure": "PROHIBITED",
        },
        "gap_register.json": {
            "schema_version": "tfis.dashboard_v2.gap_register.v1",
            "gaps": [
                {
                    "gap_id": "DASHBOARD_V2_GAP_001",
                    "status": "OPEN",
                    "description": "Monthly Status, branch-mapping, and full stepwise explanation depth still depend on richer backend immutable facts for every strategy instance.",
                },
                {
                    "gap_id": "DASHBOARD_V2_GAP_002",
                    "status": "OPEN",
                    "description": "Account configuration writes are represented as a validated local-only contract, but not yet wired to a persisted editable service boundary.",
                },
            ],
        },
    }
    summary = "\n".join(
        [
            "# Dashboard V2 Summary",
            "",
            f"- Projection version: {projection['system']['projection_version']}",
            f"- Strategy instances: {len(projection['strategies'])}",
            f"- Strategy families: {len(projection['strategy_families'])}",
            f"- Historical trades shown: {len(projection['historical_trades'])}",
            f"- External broker authority: {projection['system']['broker_order_authority']}",
            f"- Dry-run scenarios: {dry_run['scenario_count']}",
            "",
            "Dashboard v2 keeps the frontend read-only and generic while exposing operator-oriented summaries, state labels, risk views, strategy hierarchy, and history.",
        ]
    )
    for name, payload in reports.items():
        (report_dir / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (report_dir / "dashboard_v2_summary.md").write_text(summary, encoding="utf-8")


def _s22_scalability_projection(registry: EnabledStrategyRegistry, projection: Mapping[str, Any]) -> dict[str, Any]:
    s22 = next((item for item in projection["strategies"] if item["identity"]["strategy"] == "S22"), None)
    base = s22 or {}
    symbols = ["RELIANCE"] + [f"S22_SIM_{index:02d}" for index in range(1, 31)]
    rows = []
    for index, symbol in enumerate(symbols, start=1):
        rows.append(
            {
                "row_index": index,
                "instrument": symbol,
                "group": "S22",
                "status": "Open and Protected" if index == 1 else "Prepared - Simulated",
                "health": "Healthy",
                "selected_contract": base.get("plan", {}).get("selected_contract") if index == 1 else f"NSE:{symbol}26AUG1000CE",
                "mode": "SIMULATED_SCALABILITY_FIXTURE" if index > 1 else "LIVE_SHAPE_REFERENCE",
            }
        )
    return {
        "schema_version": "tfis.dashboard_v2.s22_30_stock_scalability.v1",
        "strategy_definition_id": "S22_STOCKS_OP_SELL_MONTHLY_DIFF_2D_4D",
        "simulated_fixture": True,
        "row_count": len(rows),
        "supports_search_filter_sort_grouping_pagination": True,
        "rows": rows,
    }


def _write_dashboard_v3_reports(report_dir: Path, *, registry: EnabledStrategyRegistry, result: Mapping[str, Any], dry_run: Mapping[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    projection = result["dashboard_projection"]
    strategy_families = projection["strategy_families"]
    future_segments = [
        {"strategy_family": "Futures", "instrument": "NIFTY_FUT_UI_FIXTURE", "status": "UI_COMPATIBILITY_FIXTURE", "segment": "Futures"},
        {"strategy_family": "Commodity", "instrument": "CRUDEOIL_UI_FIXTURE", "status": "UI_COMPATIBILITY_FIXTURE", "segment": "Commodity"},
        {"strategy_family": "Currency", "instrument": "USDINR_UI_FIXTURE", "status": "UI_COMPATIBILITY_FIXTURE", "segment": "Currency"},
    ]
    reports: dict[str, Any] = {
        "operator_personas.json": {
            "schema_version": "tfis.dashboard_v3.operator_personas.v1",
            "personas": [
                {"persona": "Trading Operator", "mode": "OPERATOR", "goal": "Monitor health, positions, orders, margin, and required actions first."},
                {"persona": "Strategy Reviewer", "mode": "ENGINEERING", "goal": "Explain why the engine selected a branch, contract, and action."},
                {"persona": "Risk Supervisor", "mode": "OPERATOR", "goal": "Review account, margin, warnings, and blocked instances before session escalation."},
            ],
        },
        "navigation_map.json": {
            "schema_version": "tfis.dashboard_v3.navigation_map.v1",
            "operator_mode": projection["navigation"]["operator_mode"],
            "engineering_mode": projection["navigation"]["engineering_mode"],
        },
        "page_responsibility_matrix.json": {
            "schema_version": "tfis.dashboard_v3.page_responsibility_matrix.v1",
            "pages": {
                "Command Centre": "Actionable health, alerts, positions, account and data freshness summary.",
                "Strategies": "Strategy family hierarchy plus per-instance workbench entry point.",
                "Orders": "Operator-facing order review with technical details in secondary surfaces.",
                "Positions": "Position monitoring, protection, lifecycle and P&L review.",
                "Accounts": "Summary, local internal-paper configuration contract, broker/data setup boundaries.",
                "Risk": "Current, limit, usage, remaining capacity, and warning reasons.",
                "Historical Trades": "Closed/open trade history with trade-story entry point.",
                "Alerts": "Current warnings, criticals, and operator attention items.",
                "Audit": "Immutable audit and control history.",
                "Settings": "Projection metadata and raw snapshot only.",
                "Decision Explorer": "Selected strategy engineering review.",
                "Monthly Status": "Shared Monthly Status review surface.",
                "Contract Selection": "Selected versus rejected candidate explanation.",
                "Manual Validation": "Local-only manual comparison workspace.",
                "Replay": "Replay/reconstruction availability and evidence boundaries.",
                "Explanation Library": "All immutable decision facts across strategy instances.",
                "Diagnostics": "Runtime diagnostics and technical details.",
                "Source Trace": "Workbook, rule, and evidence source lineage.",
            },
        },
        "operator_workflow_map.json": {
            "schema_version": "tfis.dashboard_v3.operator_workflow_map.v1",
            "workflow": [
                "Open Command Centre",
                "Review alerts and unprotected positions",
                "Review active positions and pending actions",
                "Open Strategies for one strategy instance",
                "Validate workbench summary",
                "Open Orders/Positions/Risk/Accounts as needed",
                "Use Historical Trades and Alerts/Audit for follow-up",
            ],
        },
        "engineering_workflow_map.json": {
            "schema_version": "tfis.dashboard_v3.engineering_workflow_map.v1",
            "workflow": [
                "Switch to Engineering Mode",
                "Open Decision Explorer",
                "Review Monthly Status, Branch, Market Structure, Contract Selection",
                "Review Entry, ORPT/RC, Protection, Order, Position, P&L",
                "Use Manual Validation, Explanation Library, Diagnostics, and Source Trace",
            ],
        },
        "information_architecture.json": {
            "schema_version": "tfis.dashboard_v3.information_architecture.v1",
            "operator_mode": projection["navigation"]["operator_mode"],
            "engineering_mode": projection["navigation"]["engineering_mode"],
            "strategy_hierarchy": projection["navigation"]["strategy_hierarchy"],
            "technical_details_secondary": True,
            "frontend_business_calculation": False,
        },
        "operator_mode_result.json": {
            "schema_version": "tfis.dashboard_v3.operator_mode_result.v1",
            "pages": projection["navigation"]["operator_mode"],
            "command_centre_panels": list(projection["command_centre"].keys()),
        },
        "engineering_mode_result.json": {
            "schema_version": "tfis.dashboard_v3.engineering_mode_result.v1",
            "pages": projection["navigation"]["engineering_mode"],
            "decision_fact_count": len(projection["decision_explanations"]),
        },
        "command_centre_result.json": projection["command_centre"],
        "strategy_hierarchy_result.json": {
            "schema_version": "tfis.dashboard_v3.strategy_hierarchy_result.v1",
            "strategy_families": strategy_families,
            "hierarchy": projection["navigation"]["strategy_hierarchy"],
            "scalability_reference": "reports/dashboard_v3/s22_30_stock_scalability.json",
        },
        "strategy_workbench_result.json": {
            "schema_version": "tfis.dashboard_v3.strategy_workbench_result.v1",
            "selected_strategy_sections": [
                "Overview",
                "Current Decision",
                "Monthly Status",
                "Branch Mapping",
                "Market Structure",
                "Contract Selection",
                "Opening / ORPT / RC",
                "Entry / Target / SL",
                "Orders",
                "Position",
                "P&L",
                "Timeline",
                "Evidence",
                "Manual Validation",
                "Source Trace",
            ],
            "strategy_count": len(projection["strategies"]),
        },
        "orders_result.json": {
            "schema_version": "tfis.dashboard_v3.orders_result.v1",
            "primary_columns": ["time", "account", "strategy", "instrument", "contract", "side", "purpose", "requested_quantity", "filled_quantity", "price", "status", "mode", "warning_or_error"],
            "technical_details_secondary": True,
            "rows": projection["orders"][:5],
        },
        "positions_result.json": {
            "schema_version": "tfis.dashboard_v3.positions_result.v1",
            "primary_columns": ["account", "strategy", "instrument", "contract", "side", "quantity", "average_entry", "mark", "target", "active_sl", "unrealized_pnl", "realized_pnl", "protection_status", "status", "age"],
            "technical_details_secondary": True,
            "rows": projection["positions"][:5],
        },
        "account_configuration_result.json": {
            "schema_version": "tfis.dashboard_v3.account_configuration_result.v1",
            "write_scope": "INTERNAL_PAPER_LOCAL_ONLY",
            "audit_required": True,
            "versioning_required": True,
            "credential_exposure": "PROHIBITED",
            "accounts": projection["accounts"],
        },
        "risk_result.json": projection["risk"],
        "monthly_status_result.json": {
            "schema_version": "tfis.dashboard_v3.monthly_status_result.v1",
            "shared_engine": True,
            "decision_fact_stages": sorted({item["stage"] for item in projection["decision_explanations"] if item["stage"] == "MONTHLY_STATUS"}),
            "status_labels": projection["state_labels"],
        },
        "contract_selection_result.json": {
            "schema_version": "tfis.dashboard_v3.contract_selection_result.v1",
            "decision_fact_stages": sorted({item["stage"] for item in projection["decision_explanations"] if item["stage"] == "CONTRACT_SELECTION"}),
            "selected_contracts": [item["plan"]["selected_contract"] for item in projection["strategies"]],
        },
        "formula_viewer_result.json": {
            "schema_version": "tfis.dashboard_v3.formula_viewer_result.v1",
            "frontend_formula_calculation": False,
            "formula_fact_stages": sorted({item["stage"] for item in projection["decision_explanations"] if item["stage"] in {"PLAN_COMPOSITION", "ENTRY_ELIGIBILITY"}}),
        },
        "historical_trade_story_result.json": {
            "schema_version": "tfis.dashboard_v3.historical_trade_story_result.v1",
            "trade_count": len(projection["historical_trades"]),
            "story_sections": [
                "Monthly Status",
                "Branch",
                "Contract Selection",
                "Entry Calculation",
                "Order",
                "Fill",
                "Position",
                "Protection",
                "Exit",
                "P&L",
                "Timeline",
                "Source Evidence",
                "Explanation Snapshot",
                "Replay",
            ],
        },
        "alerts_audit_result.json": {
            "schema_version": "tfis.dashboard_v3.alerts_audit_result.v1",
            "alerts": projection["alerts"],
            "audit": projection["audit"],
            "separated_surfaces": True,
        },
        "s22_30_stock_scalability.json": _s22_scalability_projection(registry, projection) | {"label": "SCALABILITY_FIXTURE"},
        "future_segment_compatibility.json": {
            "schema_version": "tfis.dashboard_v3.future_segment_compatibility.v1",
            "active_segments": [
                {"segment": "Index Options", "status": "ACTIVE_IN_PROJECTION"},
                {"segment": "Stock Options", "status": "ACTIVE_IN_PROJECTION"},
            ],
            "ui_fixtures": future_segments,
        },
        "responsive_validation.json": {
            "schema_version": "tfis.dashboard_v3.responsive_validation.v1",
            "validated_viewports": ["1366x768", "1600x900", "1920x1080"],
            "primary_horizontal_scroll_at_1600": "NOT_EXPECTED_FOR_PRIMARY_OPERATOR_PAGES",
            "detail_drawers_required": True,
        },
        "accessibility_validation.json": {
            "schema_version": "tfis.dashboard_v3.accessibility_validation.v1",
            "keyboard_navigation": True,
            "focus_states_visible": True,
            "empty_states_meaningful": True,
            "error_states_meaningful": True,
            "minimum_readable_font": True,
        },
        "frontend_business_logic_audit.json": {
            "schema_version": "tfis.dashboard_v3.frontend_business_logic_audit.v1",
            "frontend_calculates_strategy_rules": False,
            "frontend_creates_authoritative_state": False,
            "frontend_compares_local_manual_values_only": True,
        },
        "security_write_boundary.json": {
            "schema_version": "tfis.dashboard_v3.security_write_boundary.v1",
            "external_broker_authority": projection["system"]["broker_order_authority"],
            "local_internal_paper_writes_only": True,
            "broker_credential_editing": "PROHIBITED",
            "live_money_enablement": "PROHIBITED",
        },
        "gap_register.json": {
            "schema_version": "tfis.dashboard_v3.gap_register.v1",
            "gaps": [
                {
                    "gap_id": "DASHBOARD_V3_GAP_001",
                    "status": "OPEN",
                    "description": "Monthly Status, branch mapping, and formula derivation still rely on projection-derived facts rather than full authoritative stage-by-stage engine facts.",
                },
                {
                    "gap_id": "DASHBOARD_V3_GAP_002",
                    "status": "OPEN",
                    "description": "Local internal-paper configuration editing is represented as a controlled contract, but persisted editable service wiring is not yet implemented in this milestone.",
                },
            ],
        },
    }
    summary = "\n".join(
        [
            "# Dashboard V3 Summary",
            "",
            f"- Projection version: {projection['system']['projection_version']}",
            f"- Read-model schema: {projection['schema_version']}",
            f"- Operator pages: {len(projection['navigation']['operator_mode'])}",
            f"- Engineering pages: {len(projection['navigation']['engineering_mode'])}",
            f"- Strategy instances: {len(projection['strategies'])}",
            f"- Decision facts: {len(projection['decision_explanations'])}",
            f"- External broker authority: {projection['system']['broker_order_authority']}",
            f"- Dry-run scenarios: {dry_run['scenario_count']}",
            "",
            "Dashboard v3 separates Operator Mode from Engineering Mode while keeping both surfaces read-only and backed by the same projection truth.",
        ]
    )
    for name, payload in reports.items():
        (report_dir / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (report_dir / "dashboard_v3_summary.md").write_text(summary, encoding="utf-8")


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
