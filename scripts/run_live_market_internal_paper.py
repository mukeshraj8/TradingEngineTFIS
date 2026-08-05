from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.broker.authentication import BrokerSessionStatus
from tfis.broker.authentication.fyers import FyersAuthenticationAdapter
from tfis.fyers_read_only import FyersReadOnlyAdapter, FyersReadOnlyStatus
from tfis.runtime.multi_strategy import MultiStrategyRuntimeCoordinator, load_enabled_strategy_registry
from tfis.runtime.multi_strategy.live_market_internal_paper import build_live_market_internal_paper_reports
from tfis.runtime.multi_strategy.supervisor import _write_symbol_master_cache


IST = ZoneInfo("Asia/Calcutta")
LAUNCHER_STATE = REPO_ROOT / "tmp" / "live_market_internal_paper" / "launcher_state.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TFIS live-market internal-paper operator launcher.")
    parser.add_argument("--mode", default="live-market-internal-paper", choices=["live-market-internal-paper"])
    parser.add_argument("--enabled-profile", default="baseline", choices=["baseline", "development-s22-multistock"])
    parser.add_argument("--dashboard-port", type=int, default=8766)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--session-date")
    parser.add_argument("--reconstruct-if-late", action="store_true")
    parser.add_argument("--supervisor-report-dir", default="reports/live_supervisor")
    parser.add_argument("--dashboard-output-root", default="tmp/tfis_dashboard_v1")
    parser.add_argument("--state-root", default="tmp/tfis_supervisor_state")
    parser.add_argument("--db-path", default="data/internal_paper/unified_supervisor.sqlite")
    parser.add_argument("--report-dir", default="reports/live_market_internal_paper")
    parser.add_argument("command", choices=["prepare", "start", "stop", "status", "export"])
    args = parser.parse_args(argv)

    if args.command == "stop":
        return _stop()
    if args.command == "status":
        return _status()

    registry = _registry_for_profile(args.enabled_profile)
    auth_payload = _refresh_and_diagnose()

    if args.command == "prepare":
        _run_preflight(registry_path=registry, db_path=args.db_path, report_dir=args.supervisor_report_dir)
        result = build_live_market_internal_paper_reports(
            repo_root=REPO_ROOT,
            report_dir=args.report_dir,
            authentication_diagnostics=auth_payload,
        )
        print(result.verdict)
        print(f"Reports: {result.report_dir}")
        print(f"Summary: {result.summary_path}")
        return 0

    if args.command == "export":
        result = build_live_market_internal_paper_reports(
            repo_root=REPO_ROOT,
            report_dir=args.report_dir,
            authentication_diagnostics=auth_payload,
        )
        print(result.verdict)
        print(f"Reports: {result.report_dir}")
        print(f"Summary: {result.summary_path}")
        return 0

    preflight_payload = _run_preflight(registry_path=registry, db_path=args.db_path, report_dir=args.supervisor_report_dir)
    if preflight_payload.get("verdict") != "READY_FOR_COMPLETE_UNIFIED_SESSION":
        result = build_live_market_internal_paper_reports(
            repo_root=REPO_ROOT,
            report_dir=args.report_dir,
            authentication_diagnostics=auth_payload,
        )
        print(preflight_payload.get("verdict"))
        print(f"Reports: {result.report_dir}")
        return 1

    return _start(
        registry_path=registry,
        dashboard_port=args.dashboard_port,
        poll_seconds=args.poll_seconds,
        session_date=args.session_date,
        reconstruct_if_late=args.reconstruct_if_late,
        supervisor_report_dir=args.supervisor_report_dir,
        dashboard_output_root=args.dashboard_output_root,
        state_root=args.state_root,
        db_path=args.db_path,
        report_dir=args.report_dir,
        authentication_diagnostics=auth_payload,
    )


def _refresh_and_diagnose() -> dict[str, object]:
    auth = FyersAuthenticationAdapter(
        tfis_root=REPO_ROOT,
        logical_account_ref="live-market-internal-paper-launcher",
    ).authenticate(allow_refresh=False, validate_session=True)
    if auth.status is not BrokerSessionStatus.AUTHENTICATED or auth.session is None:
        _run_command(
            [str(REPO_ROOT / ".venv" / "Scripts" / "python.exe"), "scripts/fyers_token_refresh.py", "--prepare"],
            check=True,
        )
    output = _run_command(
        [
            str(REPO_ROOT / ".venv" / "Scripts" / "python.exe"),
            "scripts/run_broker_diagnostics.py",
            "--broker",
            "fyers",
            "--check-reference-data",
            "--check-historical-data",
            "--check-quote",
            "--check-option-chain",
            "--underlying-symbol",
            "NSE:RELIANCE-EQ",
        ],
        capture_output=True,
        check=True,
    ).stdout
    payload = json.loads(output)
    report_dir = REPO_ROOT / "reports" / "live_market_internal_paper"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "authentication_diagnostics.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _warm_symbol_master_cache()
    return payload


def _warm_symbol_master_cache() -> None:
    auth = FyersAuthenticationAdapter(
        tfis_root=REPO_ROOT,
        logical_account_ref="live-market-internal-paper-cache-warmer",
    ).authenticate(allow_refresh=False, validate_session=True)
    if auth.status is not BrokerSessionStatus.AUTHENTICATED or auth.session is None:
        return
    adapter = FyersReadOnlyAdapter.from_validated_session(
        auth.session,
        now_provider=lambda: datetime.now(tz=IST),
        timeout_seconds=1.0,
        max_retries=0,
    )
    result = adapter.fetch_symbol_master("NSEFO")
    if result.status is not FyersReadOnlyStatus.SUCCESS:
        return
    records = tuple(result.payload)
    if not records:
        return
    _write_symbol_master_cache(
        REPO_ROOT / "tmp" / "tfis_supervisor_state" / "nsefo_symbol_master_cache.json",
        exchange="NSEFO",
        source_version=str(getattr(records[0], "source_version", "FYERS_READ_ONLY_CACHE")),
        downloaded_at=getattr(records[0], "downloaded_at", datetime.now(tz=IST)),
        records=records,
    )


def _run_preflight(*, registry_path: str, db_path: str, report_dir: str) -> dict[str, object]:
    _run_command(
        [
            str(REPO_ROOT / ".venv" / "Scripts" / "python.exe"),
            "scripts/run_tfis_internal_paper.py",
            "--registry",
            registry_path,
            "--db-path",
            db_path,
            "--supervisor-report-dir",
            report_dir,
            "--preflight-complete-session",
        ],
        check=True,
    )
    return json.loads((REPO_ROOT / report_dir / "complete_session_preflight.json").read_text(encoding="utf-8"))


def _start(
    *,
    registry_path: str,
    dashboard_port: int,
    poll_seconds: float,
    session_date: str | None,
    reconstruct_if_late: bool,
    supervisor_report_dir: str,
    dashboard_output_root: str,
    state_root: str,
    db_path: str,
    report_dir: str,
    authentication_diagnostics: dict[str, object],
) -> int:
    launcher_root = LAUNCHER_STATE.parent
    launcher_root.mkdir(parents=True, exist_ok=True)
    logs_root = REPO_ROOT / "logs" / "live_market_internal_paper"
    logs_root.mkdir(parents=True, exist_ok=True)
    seed_projection_path = launcher_root / "dashboard_seed_projection.json"

    dashboard_log = logs_root / "dashboard.log"
    supervisor_log = logs_root / "supervisor.log"
    python_exe = str(REPO_ROOT / ".venv" / "Scripts" / "python.exe")
    _write_dashboard_seed_projection(
        registry_path=registry_path,
        projection_path=seed_projection_path,
    )

    dashboard_cmd = [
        python_exe,
        "scripts/run_tfis_dashboard.py",
        "--projection",
        str(seed_projection_path.relative_to(REPO_ROOT)),
        "--output-root",
        dashboard_output_root,
        "--serve",
        "--port",
        str(dashboard_port),
    ]
    supervisor_cmd = [
        python_exe,
        "scripts/run_tfis_internal_paper.py",
        "--registry",
        registry_path,
        "--dashboard-port",
        str(dashboard_port),
        "--poll-seconds",
        str(poll_seconds),
        "--supervisor-report-dir",
        supervisor_report_dir,
        "--dashboard-output-root",
        dashboard_output_root,
        "--supervisor-state-root",
        state_root,
        "--db-path",
        db_path,
        "--continuous-supervisor",
    ]
    if session_date:
        supervisor_cmd.extend(["--session-date", session_date])
    if reconstruct_if_late:
        supervisor_cmd.append("--reconstruct-if-late")

    dashboard_proc = subprocess.Popen(
        dashboard_cmd,
        cwd=REPO_ROOT,
        stdout=dashboard_log.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    supervisor_proc = subprocess.Popen(
        supervisor_cmd,
        cwd=REPO_ROOT,
        stdout=supervisor_log.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )

    metadata = {
        "mode": "live-market-internal-paper",
        "enabled_profile": registry_path,
        "dashboard_port": dashboard_port,
        "poll_seconds": poll_seconds,
        "session_date": session_date,
        "reconstruct_if_late": reconstruct_if_late,
        "dashboard_pid": dashboard_proc.pid,
        "supervisor_pid": supervisor_proc.pid,
        "dashboard_log": str(dashboard_log),
        "supervisor_log": str(supervisor_log),
        "started_at": datetime.now(tz=IST).isoformat(),
    }
    LAUNCHER_STATE.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    _wait_for_heartbeat(REPO_ROOT / state_root / "heartbeat.json")
    _wait_for_dashboard_health(dashboard_port)
    result = build_live_market_internal_paper_reports(
        repo_root=REPO_ROOT,
        report_dir=report_dir,
        authentication_diagnostics=authentication_diagnostics,
    )
    print("LIVE_MARKET_INTERNAL_PAPER_STARTED")
    print(f"Dashboard PID: {dashboard_proc.pid}")
    print(f"Supervisor PID: {supervisor_proc.pid}")
    print(f"Reports: {result.report_dir}")
    print(f"Summary: {result.summary_path}")
    return 0


def _stop() -> int:
    stop_file = REPO_ROOT / "tmp" / "tfis_supervisor_state" / "continuous_unified_supervisor.stop"
    stop_file.parent.mkdir(parents=True, exist_ok=True)
    stop_file.write_text("STOP\n", encoding="utf-8")
    metadata = _read_json(LAUNCHER_STATE)
    dashboard_pid = metadata.get("dashboard_pid")
    if dashboard_pid:
        _run_command(["taskkill", "/PID", str(dashboard_pid), "/T", "/F"], check=False)
    print("LIVE_MARKET_INTERNAL_PAPER_STOP_REQUESTED")
    return 0


def _status() -> int:
    metadata = _read_json(LAUNCHER_STATE)
    heartbeat = _read_json(REPO_ROOT / "tmp" / "tfis_supervisor_state" / "heartbeat.json")
    payload = {
        "launcher_state": metadata,
        "supervisor_heartbeat": heartbeat,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _registry_for_profile(profile: str) -> str:
    if profile == "development-s22-multistock":
        return "config/s22_multi_stock_registry.yaml"
    return "config/live_market_internal_paper_strategy_instances.yaml"


def _run_command(command: list[str], *, capture_output: bool = False, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=capture_output,
        check=check,
    )


def _write_dashboard_seed_projection(*, registry_path: str, projection_path: Path) -> None:
    registry = load_enabled_strategy_registry(REPO_ROOT / registry_path)
    projection = MultiStrategyRuntimeCoordinator(registry).run_deterministic_session()["dashboard_projection"]
    projection["system"].update(
        {
            "runtime": "LIVE_MARKET_INTERNAL_PAPER_DASHBOARD_SEED",
            "market_state": "WAITING_FOR_SUPERVISOR_SNAPSHOT",
            "projection_mode": "LIVE_DASHBOARD_SEED_WAITING_FOR_SUPERVISOR",
            "generated_at": datetime.now(tz=IST).isoformat(),
            "source_timestamp": None,
            "session_id": None,
            "supervisor_state": "WAITING_FOR_SUPERVISOR_SNAPSHOT",
        }
    )
    projection["command_centre"].update(
        {
            "active_orders": 0,
            "pending_orders": 0,
            "open_positions": 0,
            "plans_prepared": 0,
            "system_state": "WAITING_FOR_SUPERVISOR_SNAPSHOT",
            "broker_sessions": "WAITING_FOR_SUPERVISOR_SNAPSHOT",
        }
    )
    projection["orders"] = []
    projection["positions"] = []
    projection["historical_trades"] = []
    projection["projection_hash"] = "LIVE_MARKET_DASHBOARD_SEED_WAITING_FOR_SUPERVISOR"
    projection_path.parent.mkdir(parents=True, exist_ok=True)
    projection_path.write_text(json.dumps(projection, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _wait_for_heartbeat(path: Path, *, timeout_seconds: float = 20.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(0.5)


def _wait_for_dashboard_health(port: int, *, timeout_seconds: float = 20.0) -> None:
    deadline = time.time() + timeout_seconds
    url = f"http://127.0.0.1:{port}/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.5)


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
