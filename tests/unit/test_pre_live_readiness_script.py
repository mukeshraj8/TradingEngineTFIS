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


def test_pre_live_readiness_parser_supports_token_and_json_flags() -> None:
    module = _load_module()

    parser = module.build_parser()
    args = parser.parse_args(["--profile", "prod", "--require-token", "--json"])

    assert args.profile == "prod"
    assert args.require_token is True
    assert args.json is True


def test_pre_live_readiness_checks_skip_token_by_default() -> None:
    module = _load_module()
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

    checks = module.run_checks(require_token=False)
    token_check = next(check for check in checks if check.name == "fyers_token")
    broker_runtime_check = next(check for check in checks if check.name == "paper_broker_runtime")
    live_state_check = next(check for check in checks if check.name == "paper_live_state")

    assert token_check.status == "PASS"
    assert "skipped" in token_check.message.lower()
    assert broker_runtime_check.status == "PASS"
    assert live_state_check.status == "PASS"


def test_pre_live_readiness_reports_live_state_failure() -> None:
    module = _load_module()
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

    checks = module.run_checks(require_token=False)
    live_state_check = next(check for check in checks if check.name == "paper_live_state")

    assert live_state_check.status == "FAIL"
    assert "redis unavailable" in live_state_check.message


def test_pre_live_readiness_reports_broker_runtime_failure() -> None:
    module = _load_module()
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

    checks = module.run_checks(require_token=True)
    broker_runtime_check = next(check for check in checks if check.name == "paper_broker_runtime")

    assert broker_runtime_check.status == "FAIL"
    assert "require_token=True" in broker_runtime_check.message
