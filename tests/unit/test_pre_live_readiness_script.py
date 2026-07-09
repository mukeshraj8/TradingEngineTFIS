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

    checks = module.run_checks(require_token=False)
    token_check = next(check for check in checks if check.name == "fyers_token")

    assert token_check.status == "PASS"
    assert "skipped" in token_check.message.lower()
