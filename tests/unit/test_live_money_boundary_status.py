from __future__ import annotations

import importlib.util
from pathlib import Path

from tfis.paper import load_live_money_boundary_status


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_script_module():
    script_path = REPO_ROOT / "scripts" / "show_tfis_live_money_boundary_status.py"
    spec = importlib.util.spec_from_file_location("show_tfis_live_money_boundary_status", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_money_boundary_status_blocks_live_order_routing() -> None:
    status = load_live_money_boundary_status()

    assert status.status == "LIVE_MONEY_NO_GO_ROUTING_DISABLED"
    assert status.live_money_ready is False
    assert status.paper_runtime_safe is True
    assert status.order_routing_enabled is False
    assert len(status.gates) >= 8
    gates_by_code = {gate.code: gate for gate in status.gates}
    assert set(gates_by_code) >= {
        "BROKER_ORDER_STATE_MODEL",
        "IDEMPOTENT_ORDER_ROUTING",
        "BROKER_POSITION_RECONCILIATION",
        "PARTIAL_FILL_AND_REJECT_HANDLING",
        "LIVE_EXIT_PROTECTION",
        "MARKET_EVENT_INGRESS_FOR_LIVE",
        "MULTI_DAY_LIVE_POSITION_RECOVERY",
        "OPERATOR_LIVE_APPROVAL_AND_KILL_SWITCH",
        "LIVE_EXECUTION_GATE_DISABLED_BY_DEFAULT",
    }
    assert all(gate.required_before_live for gate in status.gates)
    assert gates_by_code["BROKER_ORDER_STATE_MODEL"].status == "DONE"
    assert "broker order id" in gates_by_code["BROKER_ORDER_STATE_MODEL"].description.lower()
    assert gates_by_code["IDEMPOTENT_ORDER_ROUTING"].status == "DONE"
    assert "client order ids" in gates_by_code["IDEMPOTENT_ORDER_ROUTING"].description
    assert gates_by_code["BROKER_POSITION_RECONCILIATION"].status == "DONE"
    assert "broker position" in gates_by_code["BROKER_POSITION_RECONCILIATION"].description
    assert gates_by_code["PARTIAL_FILL_AND_REJECT_HANDLING"].status == "DONE"
    assert "partial fill" in gates_by_code["PARTIAL_FILL_AND_REJECT_HANDLING"].description
    assert gates_by_code["LIVE_EXIT_PROTECTION"].status == "DONE"
    assert "target" in gates_by_code["LIVE_EXIT_PROTECTION"].description
    assert gates_by_code["MARKET_EVENT_INGRESS_FOR_LIVE"].status == "DONE"
    assert "websocket" in gates_by_code["MARKET_EVENT_INGRESS_FOR_LIVE"].description
    assert gates_by_code["MULTI_DAY_LIVE_POSITION_RECOVERY"].status == "DONE"
    assert "overnight" in gates_by_code["MULTI_DAY_LIVE_POSITION_RECOVERY"].description
    assert gates_by_code["OPERATOR_LIVE_APPROVAL_AND_KILL_SWITCH"].status == "DONE"
    assert "operator approval" in gates_by_code["OPERATOR_LIVE_APPROVAL_AND_KILL_SWITCH"].description
    assert gates_by_code["LIVE_EXECUTION_GATE_DISABLED_BY_DEFAULT"].status == "DONE"
    assert "blocks live routing" in gates_by_code["LIVE_EXECUTION_GATE_DISABLED_BY_DEFAULT"].description
    assert all(gate.status == "DONE" for gate in status.gates)


def test_live_money_boundary_cli_reports_blocked_status(capsys) -> None:
    module = _load_script_module()

    exit_code = module.main([])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "LiveMoneyBoundary: status=LIVE_MONEY_NO_GO_ROUTING_DISABLED" in output
    assert "live_money_ready=false" in output
    assert "order_routing_enabled=false" in output
    assert "LiveMoneyGate: code=BROKER_ORDER_STATE_MODEL status=DONE" in output
    assert "LiveMoneyGate: code=IDEMPOTENT_ORDER_ROUTING status=DONE" in output
    assert "LiveMoneyGate: code=BROKER_POSITION_RECONCILIATION status=DONE" in output
    assert "LiveMoneyGate: code=PARTIAL_FILL_AND_REJECT_HANDLING status=DONE" in output
    assert "LiveMoneyGate: code=LIVE_EXIT_PROTECTION status=DONE" in output
    assert "LiveMoneyGate: code=MARKET_EVENT_INGRESS_FOR_LIVE status=DONE" in output
    assert "LiveMoneyGate: code=MULTI_DAY_LIVE_POSITION_RECOVERY status=DONE" in output
    assert "LiveMoneyGate: code=OPERATOR_LIVE_APPROVAL_AND_KILL_SWITCH status=DONE" in output
    assert "LiveMoneyGate: code=LIVE_EXECUTION_GATE_DISABLED_BY_DEFAULT status=DONE" in output
