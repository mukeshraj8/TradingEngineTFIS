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
from tfis.paper import (
    load_paper_runtime_broker_health_statuses,
    inspect_paper_live_state_store_from_yaml,
    load_paper_broker_runtime,
    load_paper_runtime_fresh_entry_handoff_statuses,
    load_paper_runtime_guardrail_statuses,
    load_paper_runtime_order_routing_statuses,
    load_paper_runtime_reconciliation_statuses,
    load_paper_lifecycle_supervisor_target_specs,
    prepare_paper_broker_runtime_environment,
)
from tfis.paper.operator_controls import (
    load_latest_operator_control_event_from_root,
    load_paper_runtime_control_state_from_root,
)


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
    parser.add_argument(
        "--probe-broker-health",
        action="store_true",
        help="Actively connect each configured paper broker adapter and confirm health.",
    )
    parser.add_argument("--json", action="store_true", help="Emit a JSON report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    checks = run_checks(
        require_token=args.require_token,
        probe_broker_health=args.probe_broker_health,
    )
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


def run_checks(*, require_token: bool, probe_broker_health: bool = False) -> tuple[ReadinessCheck, ...]:
    checks: list[ReadinessCheck] = [
        _project_structure_check(),
        _strategy_config_validation_check(),
        _dashboard_config_check(),
        _paper_lifecycle_supervisor_config_check(),
        _paper_broker_runtime_check(require_token=require_token),
        _paper_runtime_guardrail_check(),
        _paper_order_routing_safety_check(),
        _paper_runtime_reconciliation_check(),
        _paper_runtime_fresh_entry_handoff_check(),
        _paper_live_state_check(),
        _operator_control_check(),
        _monthly_status_config_check(),
        _token_check(required=require_token),
    ]
    if probe_broker_health:
        checks.insert(
            5,
            _paper_runtime_broker_health_check(
                require_token=require_token,
            ),
        )
    return tuple(checks)


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


def _paper_live_state_check() -> ReadinessCheck:
    config_path = REPO_ROOT / "config" / "paper_lifecycle_supervisor_targets.yaml"
    try:
        specs = load_paper_lifecycle_supervisor_target_specs(config_path, repo_root=REPO_ROOT)
    except Exception as exc:
        return ReadinessCheck(
            name="paper_live_state",
            status="FAIL",
            message=f"Paper live-state readiness could not load target config: {exc}",
        )

    failures: list[str] = []
    summaries: list[str] = []
    for spec in specs:
        diagnostics = inspect_paper_live_state_store_from_yaml(spec.config_path)
        label = f"{spec.strategy_code}=>{diagnostics.provider}/{diagnostics.backend}"
        if diagnostics.status != "PASS":
            failures.append(f"{spec.strategy_code}: {diagnostics.message}")
        else:
            summaries.append(label)
    if failures:
        return ReadinessCheck(
            name="paper_live_state",
            status="FAIL",
            message="; ".join(failures),
        )
    return ReadinessCheck(
        name="paper_live_state",
        status="PASS",
        message="Paper live-state providers ready: " + ", ".join(summaries),
    )


def _operator_control_check() -> ReadinessCheck:
    control_root = REPO_ROOT / "tmp" / "operator_controls"
    state = load_paper_runtime_control_state_from_root(control_root)
    latest_event = load_latest_operator_control_event_from_root(control_root)
    if state.global_pause_active:
        latest_detail = (
            f" Latest control event: {latest_event.action} at {latest_event.occurred_at}."
            if latest_event is not None
            else ""
        )
        return ReadinessCheck(
            name="operator_controls",
            status="FAIL",
            message=(
                "Global TFIS paper-runtime pause marker is active under "
                f"{control_root}.{latest_detail} Clear it with "
                "`scripts\\resume_tfis_runtime.ps1` before market start."
            ),
        )
    if state.paused_strategies:
        paused = ", ".join(sorted(state.paused_strategies))
        latest_detail = (
            f" Latest control event: {latest_event.action} at {latest_event.occurred_at}."
            if latest_event is not None
            else ""
        )
        return ReadinessCheck(
            name="operator_controls",
            status="FAIL",
            message=(
                f"Per-strategy TFIS pause markers are active for {paused}.{latest_detail} "
                "Clear them with `scripts\\resume_tfis_runtime.ps1 -StrategyCode <CODE>` "
                "before market start."
            ),
        )
    if latest_event is None:
        return ReadinessCheck(
            name="operator_controls",
            status="PASS",
            message="No TFIS pause markers are active, and no operator-control events are recorded yet.",
        )
    strategy_suffix = f" strategy={latest_event.strategy_code}" if latest_event.strategy_code else ""
    return ReadinessCheck(
        name="operator_controls",
        status="PASS",
        message=(
            "No TFIS pause markers are active. Latest operator-control event: "
            f"{latest_event.action}{strategy_suffix} at {latest_event.occurred_at}."
        ),
    )


def _paper_broker_runtime_check(*, require_token: bool) -> ReadinessCheck:
    config_path = REPO_ROOT / "config" / "paper_lifecycle_supervisor_targets.yaml"
    try:
        specs = load_paper_lifecycle_supervisor_target_specs(config_path, repo_root=REPO_ROOT)
    except Exception as exc:
        return ReadinessCheck(
            name="paper_broker_runtime",
            status="FAIL",
            message=f"Paper broker runtime readiness could not load target config: {exc}",
        )

    failures: list[str] = []
    summaries: list[str] = []
    prepared_providers: set[str] = set()
    for spec in specs:
        try:
            runtime = load_paper_broker_runtime(spec.config_path)
            provider = runtime.config.broker.provider.strip().lower()
            summaries.append(
                f"{spec.strategy_code}=>{provider}/{runtime.timezone_name}/{runtime.config.source_mode}"
            )
            if require_token and provider not in prepared_providers:
                prepare_paper_broker_runtime_environment(
                    runtime.config,
                    tfis_root=REPO_ROOT,
                    skip_refresh=True,
                )
                prepared_providers.add(provider)
        except Exception as exc:
            failures.append(f"{spec.strategy_code}: {type(exc).__name__}: {exc}")
    if failures:
        return ReadinessCheck(
            name="paper_broker_runtime",
            status="FAIL",
            message="; ".join(failures),
        )
    if require_token:
        return ReadinessCheck(
            name="paper_broker_runtime",
            status="PASS",
            message="Paper broker runtimes assembled and auth prerequisites prepared: " + ", ".join(summaries),
        )
    return ReadinessCheck(
        name="paper_broker_runtime",
        status="PASS",
        message="Paper broker runtimes assembled: " + ", ".join(summaries),
    )


def _paper_runtime_broker_health_check(*, require_token: bool) -> ReadinessCheck:
    config_path = REPO_ROOT / "config" / "paper_lifecycle_supervisor_targets.yaml"
    try:
        statuses = load_paper_runtime_broker_health_statuses(
            config_path,
            repo_root=REPO_ROOT,
            tfis_root=REPO_ROOT,
            skip_refresh=not require_token,
        )
    except Exception as exc:
        return ReadinessCheck(
            name="paper_runtime_broker_health",
            status="FAIL",
            message=f"Paper broker health probe could not load target config: {exc}",
        )

    failures = [item for item in statuses if item.status != "PASS"]
    if failures:
        return ReadinessCheck(
            name="paper_runtime_broker_health",
            status="FAIL",
            message="; ".join(
                f"{item.strategy_code}: {item.message}" for item in failures
            ),
        )
    return ReadinessCheck(
        name="paper_runtime_broker_health",
        status="PASS",
        message="Paper broker health confirmed: " + ", ".join(
            f"{item.strategy_code}=>{item.provider}/{item.connection_state}"
            for item in statuses
        ),
    )


def _paper_runtime_guardrail_check() -> ReadinessCheck:
    config_path = REPO_ROOT / "config" / "paper_lifecycle_supervisor_targets.yaml"
    try:
        statuses = load_paper_runtime_guardrail_statuses(config_path, repo_root=REPO_ROOT)
    except Exception as exc:
        return ReadinessCheck(
            name="paper_runtime_guardrails",
            status="FAIL",
            message=f"Paper runtime guardrail check could not load target config: {exc}",
        )

    failures: list[str] = []
    summaries: list[str] = []
    for status in statuses:
        if status.status != "PASS":
            failures.append(f"{status.strategy_code}: {status.message}")
            continue
        summaries.append(f"{status.strategy_code}=>{status.source_mode}/paper={status.paper_mode_enabled}")
    if failures:
        return ReadinessCheck(
            name="paper_runtime_guardrails",
            status="FAIL",
            message="; ".join(failures),
        )
    return ReadinessCheck(
        name="paper_runtime_guardrails",
        status="PASS",
        message="Paper runtime guardrails confirmed: " + ", ".join(summaries),
    )


def _paper_order_routing_safety_check() -> ReadinessCheck:
    config_path = REPO_ROOT / "config" / "paper_lifecycle_supervisor_targets.yaml"
    try:
        statuses = load_paper_runtime_order_routing_statuses(config_path, repo_root=REPO_ROOT)
    except Exception as exc:
        return ReadinessCheck(
            name="paper_order_routing_safety",
            status="FAIL",
            message=f"Paper order-routing safety check could not load target config: {exc}",
        )

    failures: list[str] = []
    summaries: list[str] = []
    for status in statuses:
        if status.status != "PASS":
            failures.append(f"{status.strategy_code}: {status.message}")
            continue
        summaries.append(f"{status.strategy_code}=>{status.provider}/blocked")
    if failures:
        return ReadinessCheck(
            name="paper_order_routing_safety",
            status="FAIL",
            message="; ".join(failures),
        )
    return ReadinessCheck(
        name="paper_order_routing_safety",
        status="PASS",
        message="Paper order routing remains blocked: " + ", ".join(summaries),
    )


def _paper_runtime_reconciliation_check() -> ReadinessCheck:
    config_path = REPO_ROOT / "config" / "paper_lifecycle_supervisor_targets.yaml"
    try:
        statuses = load_paper_runtime_reconciliation_statuses(config_path, repo_root=REPO_ROOT)
    except Exception as exc:
        return ReadinessCheck(
            name="paper_runtime_reconciliation",
            status="FAIL",
            message=f"Paper runtime reconciliation check could not load target config: {exc}",
        )

    failures: list[str] = []
    summaries: list[str] = []
    for status in statuses:
        if status.status == "FAIL":
            failures.append(f"{status.strategy_code}: {status.message}")
            continue
        summaries.append(
            f"{status.strategy_code}=>{status.status.lower()}/states={status.persisted_state_count}"
        )
    if failures:
        return ReadinessCheck(
            name="paper_runtime_reconciliation",
            status="FAIL",
            message="; ".join(failures),
        )
    return ReadinessCheck(
        name="paper_runtime_reconciliation",
        status="PASS",
        message="Paper runtime reconciliation confirmed: " + ", ".join(summaries),
    )


def _paper_runtime_fresh_entry_handoff_check() -> ReadinessCheck:
    config_path = REPO_ROOT / "config" / "paper_lifecycle_supervisor_targets.yaml"
    try:
        statuses = load_paper_runtime_fresh_entry_handoff_statuses(config_path, repo_root=REPO_ROOT)
    except Exception as exc:
        return ReadinessCheck(
            name="paper_runtime_fresh_entry_handoff",
            status="FAIL",
            message=f"Paper fresh-entry handoff check failed: {exc}",
        )
    failures = [item for item in statuses if item.status == "FAIL"]
    if failures:
        return ReadinessCheck(
            name="paper_runtime_fresh_entry_handoff",
            status="FAIL",
            message="; ".join(f"{item.strategy_code}: {item.message}" for item in failures),
        )
    summaries = [
        f"{item.strategy_code}=>{item.status.lower()}/fresh_closes={item.fresh_close_count}"
        for item in statuses
    ]
    return ReadinessCheck(
        name="paper_runtime_fresh_entry_handoff",
        status="PASS",
        message="Paper fresh-entry handoff evidence confirmed: " + ", ".join(summaries),
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
