from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.brokers.fyers_token import FyersTokenRefreshError, prepare_fyers_env_from_tfis
from tfis.dashboard.config_loader import load_dashboard_strategy_configs
from tfis.monthly_status import load_monthly_status_instrument_registry, load_monthly_status_thresholds
from tfis.paper import load_paper_lifecycle_supervisor_target_specs


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    name: str
    status: str
    message: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run local TFIS pre-live readiness checks without placing orders."
    )
    parser.add_argument("--profile", default="prod")
    parser.add_argument("--require-token", action="store_true")
    parser.add_argument("--json", action="store_true", help="Emit a JSON report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    checks = run_checks(require_token=args.require_token)
    failed = [check for check in checks if check.status != "PASS"]
    payload = {
        "profile": args.profile,
        "overall_status": "PASS" if not failed else "FAIL",
        "checks": [asdict(check) for check in checks],
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"TFIS pre-live readiness: {payload['overall_status']}")
        print(f"Profile: {args.profile}")
        for check in checks:
            print(f"[{check.status}] {check.name}: {check.message}")
    return 0 if not failed else 1


def run_checks(*, require_token: bool) -> tuple[ReadinessCheck, ...]:
    return (
        _project_structure_check(),
        _strategy_config_validation_check(),
        _dashboard_config_check(),
        _paper_lifecycle_supervisor_config_check(),
        _monthly_status_config_check(),
        _token_check(required=require_token),
    )


def _project_structure_check() -> ReadinessCheck:
    failures: list[str] = []
    required_paths = (
        REPO_ROOT / "src" / "tfis",
        REPO_ROOT / "config" / "config.yaml",
        REPO_ROOT / "config" / "config.dev.yaml",
    )
    for path in required_paths:
        if not path.exists():
            failures.append(str(path))
    try:
        __import__("tfis")
    except Exception as exc:  # pragma: no cover - exercised in script runs
        failures.append(f"import tfis failed: {exc}")
    if failures:
        return ReadinessCheck(
            name="project_structure",
            status="FAIL",
            message="Missing or broken project prerequisites: " + "; ".join(failures),
        )
    return ReadinessCheck(
        name="project_structure",
        status="PASS",
        message="Source package, base configs, and tfis import are available.",
    )


def _strategy_config_validation_check() -> ReadinessCheck:
    command = [sys.executable, str(REPO_ROOT / "scripts" / "validate_strategy_configs.py")]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        return ReadinessCheck(
            name="strategy_configs",
            status="FAIL",
            message=output or "validate_strategy_configs.py failed.",
        )
    if "EXECUTION_PLAN" not in output:
        return ReadinessCheck(
            name="strategy_configs",
            status="FAIL",
            message="Strategy validation passed but execution plan output is missing.",
        )
    return ReadinessCheck(
        name="strategy_configs",
        status="PASS",
        message="Strategy validation passed and execution plans are runnable.",
    )


def _dashboard_config_check() -> ReadinessCheck:
    config_path = REPO_ROOT / "config" / "operator_dashboard_strategies.yaml"
    try:
        configs = load_dashboard_strategy_configs(config_path, repo_root=REPO_ROOT)
    except Exception as exc:
        return ReadinessCheck(
            name="dashboard_config",
            status="FAIL",
            message=f"Dashboard strategy config failed to load: {exc}",
        )
    strategy_codes = [item.strategy_code for item in configs]
    if not strategy_codes:
        return ReadinessCheck(
            name="dashboard_config",
            status="FAIL",
            message="Dashboard strategy config loaded but contains no strategies.",
        )
    return ReadinessCheck(
        name="dashboard_config",
        status="PASS",
        message="Dashboard config loaded for strategies: " + ", ".join(strategy_codes),
    )


def _monthly_status_config_check() -> ReadinessCheck:
    try:
        thresholds = load_monthly_status_thresholds()
        registry = load_monthly_status_instrument_registry()
    except Exception as exc:
        return ReadinessCheck(
            name="monthly_status",
            status="FAIL",
            message=f"Monthly-status configuration failed to load: {exc}",
        )
    instrument_symbols = sorted(registry.instruments.keys())
    return ReadinessCheck(
        name="monthly_status",
        status="PASS",
        message=(
            f"Monthly-status thresholds loaded ({len(thresholds)} groups); "
            f"instrument registry loaded for {', '.join(instrument_symbols)}."
        ),
    )


def _paper_lifecycle_supervisor_config_check() -> ReadinessCheck:
    config_path = REPO_ROOT / "config" / "paper_lifecycle_supervisor_targets.yaml"
    try:
        specs = load_paper_lifecycle_supervisor_target_specs(config_path, repo_root=REPO_ROOT)
    except Exception as exc:
        return ReadinessCheck(
            name="paper_lifecycle_supervisor",
            status="FAIL",
            message=f"Paper lifecycle supervisor target config failed to load: {exc}",
        )
    summary = ", ".join(
        f"{item.strategy_code}=>{item.artifact_root.name}"
        for item in specs
    )
    return ReadinessCheck(
        name="paper_lifecycle_supervisor",
        status="PASS",
        message="Paper lifecycle supervisor targets loaded: " + summary,
    )


def _token_check(*, required: bool) -> ReadinessCheck:
    if not required:
        return ReadinessCheck(
            name="fyers_token",
            status="PASS",
            message="Token check skipped; rerun with --require-token for pre-market auth verification.",
        )
    try:
        prepared = prepare_fyers_env_from_tfis(tfis_root=REPO_ROOT, skip_refresh=True)
    except (FyersTokenRefreshError, FileNotFoundError, json.JSONDecodeError) as exc:
        return ReadinessCheck(
            name="fyers_token",
            status="FAIL",
            message=f"Local FYERS token prerequisites are not ready: {exc}",
        )
    return ReadinessCheck(
        name="fyers_token",
        status="PASS",
        message=f"Loaded TFIS FYERS token store from {prepared.token_store}.",
    )


if __name__ == "__main__":
    raise SystemExit(main())
