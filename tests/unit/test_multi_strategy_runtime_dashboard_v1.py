from __future__ import annotations

import json
from pathlib import Path

import pytest

from tfis.dashboard.api import DashboardApiRouter
from tfis.dashboard.commands import audit_dashboard_command
from tfis.dashboard.events import build_sse_event_stream
from tfis.dashboard.professional import build_professional_dashboard
from tfis.runtime.multi_strategy import (
    MultiStrategyRuntimeCoordinator,
    build_unified_runtime_reports,
    load_enabled_strategy_registry,
)


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "config" / "internal_paper_strategy_instances.yaml"


def test_enabled_strategy_registry_is_configuration_driven_and_no_external_authority() -> None:
    registry = load_enabled_strategy_registry(REGISTRY_PATH)

    assert [item.symbol for item in registry.enabled_instances] == ["BANKNIFTY", "RELIANCE", "NIFTY"]
    assert len({item.strategy_instance_id for item in registry.enabled_instances}) == 3
    assert all(item.authority_mode == "INTERNAL_PAPER_CONTROLLED" for item in registry.enabled_instances)
    assert all(item.to_dict()["external_authority"]["live_submission"] == "NONE" for item in registry.enabled_instances)
    assert registry.registry_hash


def test_unified_runtime_runs_all_three_and_preserves_s22_evidence_limitation() -> None:
    registry = load_enabled_strategy_registry(REGISTRY_PATH)
    result = MultiStrategyRuntimeCoordinator(registry).run_deterministic_session()

    assert result["status"] == "PASSED"
    assert result["external_authority"]["external_broker_submission"] == "NONE"
    projection = result["dashboard_projection"]
    assert projection["command_centre"]["enabled_strategy_instances"] == 3
    assert projection["system"]["broker_order_authority"] == "NONE"
    assert len(projection["decision_explanations"]) == 18
    assert projection["decision_explanations"][0]["stage"] == "MONTHLY_STATUS"
    s22 = next(item for item in projection["strategies"] if item["identity"]["instrument"] == "RELIANCE")
    assert s22["state"]["evidence_quality"] == "DETERMINISTIC_TIMING_SUPPLEMENT"
    assert s22["operations"]["alerts"][0]["code"] == "S22_LIVE_OPEN_ORPT_RC_PENDING"


def test_selected_contract_identity_is_continuous_across_runtime_and_dashboard() -> None:
    registry = load_enabled_strategy_registry(REGISTRY_PATH)
    result = MultiStrategyRuntimeCoordinator(registry).run_deterministic_session()

    assert result["subscription_snapshot"]["contract_subscriptions"]
    for instance_id, instance_result in result["instance_results"].items():
        contract = instance_result["plan"]["selected_contract"]
        assert contract
        assert instance_result["execution"]["selected_contract"] == contract
        assert instance_result["position"]["selected_contract"] == contract
        assert instance_result["accounting"]["selected_contract"] == contract
        assert contract in result["subscription_snapshot"]["contract_subscriptions"]
        assert instance_id in result["subscription_snapshot"]["contract_subscriptions"][contract]

    projection = result["dashboard_projection"]
    for row in projection["strategies"]:
        contract = row["plan"]["selected_contract"]
        assert row["execution"]["selected_contract"] == contract
        assert row["position"]["selected_contract"] == contract
    for row in projection["orders"]:
        assert row["contract"] == row["execution_contract"]
    for row in projection["positions"]:
        assert row["contract"] == row["position_contract"]


def test_selected_contract_identity_survives_blocked_rc_carried_and_recovery_scenarios() -> None:
    registry = load_enabled_strategy_registry(REGISTRY_PATH)
    coordinator = MultiStrategyRuntimeCoordinator(registry)

    for scenario_id in (
        "one_strategy_blocked",
        "rc_and_normal",
        "one_position_carried",
        "restart_restore",
    ):
        result = coordinator.run_deterministic_session(scenario_id=scenario_id)
        for instance_result in result["instance_results"].values():
            contract = instance_result["plan"]["selected_contract"]
            assert contract
            assert instance_result["execution"]["selected_contract"] == contract
            assert instance_result["position"]["selected_contract"] == contract
            assert instance_result["accounting"]["selected_contract"] == contract


def test_runtime_rejects_missing_selected_contract_configuration() -> None:
    registry = load_enabled_strategy_registry(REGISTRY_PATH)
    instance = registry.enabled_instances[0]
    projection = dict(instance.deterministic_projection)
    projection["selected_contract"] = ""
    broken = instance.__class__(
        strategy_definition_id=instance.strategy_definition_id,
        strategy_version=instance.strategy_version,
        strategy_instance_id=instance.strategy_instance_id,
        account_reference=instance.account_reference,
        underlying=instance.underlying,
        product=instance.product,
        enabled=instance.enabled,
        configured_quantity=instance.configured_quantity,
        authority_mode=instance.authority_mode,
        market_data_source=instance.market_data_source,
        rule_config_hash=instance.rule_config_hash,
        risk_allocation=instance.risk_allocation,
        operator_approval_status=instance.operator_approval_status,
        evidence_quality=instance.evidence_quality,
        source_reports=instance.source_reports,
        deterministic_projection=projection,
    )

    broken_registry = registry.__class__(
        schema_version=registry.schema_version,
        session_scope=registry.session_scope,
        accounts=registry.accounts,
        risk=registry.risk,
        instances=(broken, *registry.instances[1:]),
    )

    with pytest.raises(ValueError, match="deterministic_projection.selected_contract"):
        MultiStrategyRuntimeCoordinator(broken_registry).run_deterministic_session()


def test_unified_runtime_blocked_instance_does_not_stop_other_instances() -> None:
    registry = load_enabled_strategy_registry(REGISTRY_PATH)
    result = MultiStrategyRuntimeCoordinator(registry).run_deterministic_session(scenario_id="one_strategy_blocked")
    projection = result["dashboard_projection"]

    blocked = [item for item in projection["strategies"] if item["plan"]["plan_status"] == "BLOCKED"]
    prepared = [item for item in projection["strategies"] if item["plan"]["plan_status"] == "PREPARED"]
    assert [item["identity"]["instrument"] for item in blocked] == ["RELIANCE"]
    assert {item["identity"]["instrument"] for item in prepared} == {"BANKNIFTY", "NIFTY"}
    assert all(item["plan"]["selected_contract"] for item in blocked + prepared)


def test_dashboard_api_event_and_command_contracts_are_read_only() -> None:
    registry = load_enabled_strategy_registry(REGISTRY_PATH)
    projection = MultiStrategyRuntimeCoordinator(registry).run_deterministic_session()["dashboard_projection"]
    router = DashboardApiRouter(projection)

    status, snapshot = router.resolve("/api/snapshot.json")
    assert status == 200
    assert snapshot["projection_hash"] == projection["projection_hash"]
    status, health = router.resolve("/api/health")
    assert status == 200
    assert health["broker_order_authority"] == "NONE"
    status, orders = router.resolve("/api/orders")
    assert status == 200
    assert len(orders["orders"]) == 3
    stream = build_sse_event_stream(projection)
    assert "SNAPSHOT_READY" in stream
    assert "raw_tick_stream" in stream
    accepted = audit_dashboard_command("GLOBAL_HALT", operator="TEST", scope="GLOBAL", reason="unit test")
    rejected = audit_dashboard_command("FYERS_PLACE_ORDER", operator="TEST", scope="GLOBAL", reason="unit test")
    assert accepted.accepted is True
    assert rejected.accepted is False
    assert rejected.audit_event["broker_order_authority"] == "NONE"


def test_professional_dashboard_builds_static_projection_without_formula_logic(tmp_path: Path) -> None:
    registry = load_enabled_strategy_registry(REGISTRY_PATH)
    projection = MultiStrategyRuntimeCoordinator(registry).run_deterministic_session()["dashboard_projection"]
    result = build_professional_dashboard(projection, output_root=tmp_path)

    assert result.index_html.exists()
    snapshot = json.loads(result.snapshot_json.read_text(encoding="utf-8"))
    manifest = json.loads(result.manifest_json.read_text(encoding="utf-8"))
    assert snapshot["projection_hash"] == projection["projection_hash"]
    assert manifest["frontend_formula_calculation"] is False
    html = result.index_html.read_text(encoding="utf-8")
    assert "Broker order authority" in html
    assert "Command Centre" in html
    assert "Strategies" in html
    assert "Orders" in html
    assert "Positions" in html
    assert "Accounts" in html
    assert "Risk" in html
    assert "Historical Trades" in html
    assert "Alerts" in html
    assert "Audit" in html
    assert "Decision Explorer" in html
    assert "Diagnostics" in html
    assert "How To Read This" in html


def test_runtime_reports_emit_dashboard_v2_projection_contract(tmp_path: Path) -> None:
    reports = build_unified_runtime_reports(REGISTRY_PATH, tmp_path / "dashboard_v1")

    assert "dashboard_summary.md" in reports

    v2_dir = tmp_path / "dashboard_v2"
    info_architecture = json.loads((v2_dir / "dashboard_information_architecture.json").read_text(encoding="utf-8"))
    strategy_hierarchy = json.loads((v2_dir / "strategy_hierarchy_result.json").read_text(encoding="utf-8"))
    risk_dashboard = json.loads((v2_dir / "risk_dashboard_result.json").read_text(encoding="utf-8"))
    history = json.loads((v2_dir / "historical_trade_result.json").read_text(encoding="utf-8"))
    security = json.loads((v2_dir / "security_and_write_boundary.json").read_text(encoding="utf-8"))
    summary = (v2_dir / "dashboard_v2_summary.md").read_text(encoding="utf-8")

    assert info_architecture["principal_areas"] == [
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
    assert strategy_hierarchy["strategy_instance_count"] == 3
    assert risk_dashboard["aggregate"]["risk_state"] in {"Active", "Degraded"}
    assert history["trade_count"] == 3
    assert security["external_broker_authority"] == "NONE"
    assert "Dashboard V2 Summary" in summary


def test_runtime_reports_emit_dashboard_v3_projection_contract(tmp_path: Path) -> None:
    build_unified_runtime_reports(REGISTRY_PATH, tmp_path / "dashboard_v1")

    v3_dir = tmp_path / "dashboard_v3"
    navigation = json.loads((v3_dir / "navigation_map.json").read_text(encoding="utf-8"))
    operator_mode = json.loads((v3_dir / "operator_mode_result.json").read_text(encoding="utf-8"))
    engineering_mode = json.loads((v3_dir / "engineering_mode_result.json").read_text(encoding="utf-8"))
    future_segments = json.loads((v3_dir / "future_segment_compatibility.json").read_text(encoding="utf-8"))
    logic_audit = json.loads((v3_dir / "frontend_business_logic_audit.json").read_text(encoding="utf-8"))
    summary = (v3_dir / "dashboard_v3_summary.md").read_text(encoding="utf-8")

    assert navigation["operator_mode"] == [
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
    ]
    assert "Decision Explorer" in engineering_mode["pages"]
    assert "Command Centre" in operator_mode["pages"]
    assert any(item["status"] == "UI_COMPATIBILITY_FIXTURE" for item in future_segments["ui_fixtures"])
    assert logic_audit["frontend_calculates_strategy_rules"] is False
    assert "Dashboard V3 Summary" in summary
