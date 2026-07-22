from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    script_path = REPO_ROOT / "scripts" / "pre_live_readiness.py"
    spec = importlib.util.spec_from_file_location("pre_live_readiness", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _stub_additive_runtime_checks(module) -> None:
    module._paper_runtime_fresh_entry_handoff_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_runtime_fresh_entry_handoff",
        status="PASS",
        message="paper fresh-entry handoff confirmed",
    )


def test_pre_live_readiness_parser_supports_token_probe_and_json_flags() -> None:
    module = _load_module()

    parser = module.build_parser()
    args = parser.parse_args(["--profile", "prod", "--require-token", "--probe-broker-health", "--json"])

    assert args.profile == "prod"
    assert args.require_token is True
    assert args.probe_broker_health is True
    assert args.json is True


def test_pre_live_readiness_checks_skip_token_by_default() -> None:
    module = _load_module()
    _stub_additive_runtime_checks(module)
    module._paper_broker_runtime_check = lambda require_token: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_broker_runtime",
        status="PASS",
        message=f"mocked broker runtime readiness require_token={require_token}",
    )
    module._paper_live_state_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_live_state",
        status="PASS",
        message="mocked live-state readiness",
    )
    module._paper_runtime_guardrail_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_runtime_guardrails",
        status="PASS",
        message="paper runtime guardrails look good",
    )
    module._paper_runtime_broker_health_check = lambda require_token: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_runtime_broker_health",
        status="PASS",
        message=f"paper broker health confirmed require_token={require_token}",
    )
    module._paper_order_routing_safety_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_order_routing_safety",
        status="PASS",
        message="paper order routing remains blocked",
    )
    module._paper_runtime_reconciliation_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_runtime_reconciliation",
        status="PASS",
        message="paper runtime reconciliation confirmed",
    )
    module._operator_control_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="operator_controls",
        status="PASS",
        message="no active operator pauses",
    )

    checks = module.run_checks(require_token=False, probe_broker_health=True)
    token_check = next(check for check in checks if check.name == "fyers_token")
    broker_runtime_check = next(check for check in checks if check.name == "paper_broker_runtime")
    broker_health_check = next(check for check in checks if check.name == "paper_runtime_broker_health")
    live_state_check = next(check for check in checks if check.name == "paper_live_state")

    assert token_check.status == "PASS"
    assert "skipped" in token_check.message.lower()
    assert broker_runtime_check.status == "PASS"
    assert broker_health_check.status == "PASS"
    assert live_state_check.status == "PASS"
    assert any(check.name == "paper_runtime_guardrails" for check in checks)
    assert any(check.name == "paper_order_routing_safety" for check in checks)
    assert any(check.name == "paper_runtime_reconciliation" for check in checks)
    assert any(check.name == "paper_runtime_fresh_entry_handoff" for check in checks)
    assert any(check.name == "operator_controls" for check in checks)


def test_pre_live_readiness_reports_live_state_failure() -> None:
    module = _load_module()
    _stub_additive_runtime_checks(module)
    module._paper_broker_runtime_check = lambda require_token: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_broker_runtime",
        status="PASS",
        message="mocked broker runtime readiness",
    )
    module._paper_live_state_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_live_state",
        status="FAIL",
        message="S23: redis unavailable",
    )
    module._paper_runtime_guardrail_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_runtime_guardrails",
        status="PASS",
        message="paper runtime guardrails look good",
    )
    module._paper_order_routing_safety_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_order_routing_safety",
        status="PASS",
        message="paper order routing remains blocked",
    )
    module._paper_runtime_reconciliation_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_runtime_reconciliation",
        status="PASS",
        message="paper runtime reconciliation confirmed",
    )
    module._operator_control_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="operator_controls",
        status="PASS",
        message="no active operator pauses",
    )

    checks = module.run_checks(require_token=False)
    live_state_check = next(check for check in checks if check.name == "paper_live_state")

    assert live_state_check.status == "FAIL"
    assert "redis unavailable" in live_state_check.message


def test_pre_live_readiness_reports_broker_runtime_failure() -> None:
    module = _load_module()
    _stub_additive_runtime_checks(module)
    module._paper_broker_runtime_check = lambda require_token: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_broker_runtime",
        status="FAIL",
        message=f"runtime bootstrap failed require_token={require_token}",
    )
    module._paper_live_state_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_live_state",
        status="PASS",
        message="mocked live-state readiness",
    )
    module._paper_runtime_guardrail_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_runtime_guardrails",
        status="PASS",
        message="paper runtime guardrails look good",
    )
    module._paper_order_routing_safety_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_order_routing_safety",
        status="PASS",
        message="paper order routing remains blocked",
    )
    module._paper_runtime_reconciliation_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_runtime_reconciliation",
        status="PASS",
        message="paper runtime reconciliation confirmed",
    )
    module._operator_control_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="operator_controls",
        status="PASS",
        message="no active operator pauses",
    )

    checks = module.run_checks(require_token=True)
    broker_runtime_check = next(check for check in checks if check.name == "paper_broker_runtime")

    assert broker_runtime_check.status == "FAIL"
    assert "require_token=True" in broker_runtime_check.message


def test_pre_live_readiness_reports_broker_health_probe_failure() -> None:
    module = _load_module()
    _stub_additive_runtime_checks(module)
    module._paper_broker_runtime_check = lambda require_token: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_broker_runtime",
        status="PASS",
        message="mocked broker runtime readiness",
    )
    module._paper_runtime_broker_health_check = lambda require_token: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_runtime_broker_health",
        status="FAIL",
        message=f"broker health probe failed require_token={require_token}",
    )
    module._paper_live_state_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_live_state",
        status="PASS",
        message="mocked live-state readiness",
    )
    module._paper_runtime_guardrail_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_runtime_guardrails",
        status="PASS",
        message="paper runtime guardrails look good",
    )
    module._paper_order_routing_safety_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_order_routing_safety",
        status="PASS",
        message="paper order routing remains blocked",
    )
    module._paper_runtime_reconciliation_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_runtime_reconciliation",
        status="PASS",
        message="paper runtime reconciliation confirmed",
    )
    module._operator_control_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="operator_controls",
        status="PASS",
        message="no active operator pauses",
    )

    checks = module.run_checks(require_token=True, probe_broker_health=True)
    broker_health_check = next(
        check for check in checks if check.name == "paper_runtime_broker_health"
    )

    assert broker_health_check.status == "FAIL"
    assert "require_token=True" in broker_health_check.message


def test_pre_live_readiness_reports_operator_pause_marker_failure(tmp_path: Path) -> None:
    module = _load_module()
    module.REPO_ROOT = tmp_path  # type: ignore[attr-defined]
    control_root = module.REPO_ROOT / "tmp" / "operator_controls"
    control_root.mkdir(parents=True, exist_ok=True)
    (control_root / "global_pause.json").write_text("{}", encoding="utf-8")
    (control_root / "operator_control_events.jsonl").write_text(
        '{"action":"PAUSE","scope":"GLOBAL","occurred_at":"2026-07-21T08:55:00+05:30"}\n',
        encoding="utf-8",
    )

    check = module._operator_control_check()  # type: ignore[attr-defined]

    assert check.status == "FAIL"
    assert check.name == "operator_controls"
    assert "resume_tfis_runtime.ps1" in check.message


def test_pre_live_readiness_reports_runtime_guardrail_failure() -> None:
    module = _load_module()
    _stub_additive_runtime_checks(module)
    module._paper_broker_runtime_check = lambda require_token: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_broker_runtime",
        status="PASS",
        message="mocked broker runtime readiness",
    )
    module._paper_live_state_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_live_state",
        status="PASS",
        message="mocked live-state readiness",
    )
    module._paper_runtime_guardrail_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_runtime_guardrails",
        status="FAIL",
        message="S23: paper.no_live_orders_allowed must be true",
    )
    module._paper_order_routing_safety_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_order_routing_safety",
        status="PASS",
        message="paper order routing remains blocked",
    )
    module._paper_runtime_reconciliation_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_runtime_reconciliation",
        status="PASS",
        message="paper runtime reconciliation confirmed",
    )
    module._operator_control_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="operator_controls",
        status="PASS",
        message="no active operator pauses",
    )

    checks = module.run_checks(require_token=False)
    guardrail_check = next(check for check in checks if check.name == "paper_runtime_guardrails")

    assert guardrail_check.status == "FAIL"
    assert "no_live_orders_allowed" in guardrail_check.message


def test_pre_live_readiness_reports_order_routing_safety_failure() -> None:
    module = _load_module()
    _stub_additive_runtime_checks(module)
    module._paper_broker_runtime_check = lambda require_token: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_broker_runtime",
        status="PASS",
        message="mocked broker runtime readiness",
    )
    module._paper_live_state_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_live_state",
        status="PASS",
        message="mocked live-state readiness",
    )
    module._paper_runtime_guardrail_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_runtime_guardrails",
        status="PASS",
        message="paper runtime guardrails look good",
    )
    module._paper_order_routing_safety_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_order_routing_safety",
        status="FAIL",
        message="S23: adapter place_order is not blocked",
    )
    module._paper_runtime_reconciliation_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_runtime_reconciliation",
        status="PASS",
        message="paper runtime reconciliation confirmed",
    )
    module._operator_control_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="operator_controls",
        status="PASS",
        message="no active operator pauses",
    )

    checks = module.run_checks(require_token=False)
    routing_check = next(check for check in checks if check.name == "paper_order_routing_safety")

    assert routing_check.status == "FAIL"
    assert "place_order" in routing_check.message


def test_pre_live_readiness_reports_runtime_reconciliation_failure() -> None:
    module = _load_module()
    _stub_additive_runtime_checks(module)
    module._paper_broker_runtime_check = lambda require_token: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_broker_runtime",
        status="PASS",
        message="mocked broker runtime readiness",
    )
    module._paper_live_state_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_live_state",
        status="PASS",
        message="mocked live-state readiness",
    )
    module._paper_runtime_guardrail_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_runtime_guardrails",
        status="PASS",
        message="paper runtime guardrails look good",
    )
    module._paper_order_routing_safety_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_order_routing_safety",
        status="PASS",
        message="paper order routing remains blocked",
    )
    module._paper_runtime_reconciliation_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_runtime_reconciliation",
        status="FAIL",
        message="S23: active position state conflicts with terminal ledger row",
    )
    module._operator_control_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="operator_controls",
        status="PASS",
        message="no active operator pauses",
    )

    checks = module.run_checks(require_token=False)
    reconciliation_check = next(
        check for check in checks if check.name == "paper_runtime_reconciliation"
    )

    assert reconciliation_check.status == "FAIL"
    assert "terminal ledger row" in reconciliation_check.message


def test_pre_live_readiness_reports_fresh_entry_handoff_failure() -> None:
    module = _load_module()
    module._paper_broker_runtime_check = lambda require_token: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_broker_runtime",
        status="PASS",
        message="mocked broker runtime readiness",
    )
    module._paper_live_state_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_live_state",
        status="PASS",
        message="mocked live-state readiness",
    )
    module._paper_runtime_guardrail_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_runtime_guardrails",
        status="PASS",
        message="paper runtime guardrails look good",
    )
    module._paper_order_routing_safety_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_order_routing_safety",
        status="PASS",
        message="paper order routing remains blocked",
    )
    module._paper_runtime_reconciliation_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_runtime_reconciliation",
        status="PASS",
        message="paper runtime reconciliation confirmed",
    )
    module._paper_runtime_fresh_entry_handoff_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="paper_runtime_fresh_entry_handoff",
        status="FAIL",
        message="S23: missing fresh-entry handoff evidence for trade-1@BRANCH",
    )
    module._operator_control_check = lambda: module.ReadinessCheck(  # type: ignore[attr-defined]
        name="operator_controls",
        status="PASS",
        message="no active operator pauses",
    )

    checks = module.run_checks(require_token=False)
    handoff_check = next(
        check for check in checks if check.name == "paper_runtime_fresh_entry_handoff"
    )

    assert handoff_check.status == "FAIL"
    assert "missing fresh-entry handoff evidence" in handoff_check.message
