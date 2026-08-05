from __future__ import annotations

import argparse
import sys
from pathlib import Path
from datetime import date


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.runtime.multi_strategy import (
    build_authoritative_readiness_projection,
    build_unified_runtime_reports,
    run_complete_session_preflight,
    run_continuous_supervisor,
    run_live_observation,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic unified S21/S22/S23 internal-paper certification.")
    parser.add_argument("--registry")
    parser.add_argument("--report-dir", default="reports/dashboard_v1")
    parser.add_argument("--live-observation-only", action="store_true")
    parser.add_argument("--continuous-supervisor", action="store_true")
    parser.add_argument("--preflight-complete-session", action="store_true")
    parser.add_argument("--dashboard-port", type=int, default=8766)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--max-iterations", type=int, default=0)
    parser.add_argument("--supervisor-report-dir", default="reports/live_supervisor")
    parser.add_argument("--supervisor-state-root", default="tmp/tfis_supervisor_state")
    parser.add_argument("--dashboard-output-root", default="tmp/tfis_dashboard_v1")
    parser.add_argument("--db-path", default="data/internal_paper/unified_supervisor.sqlite")
    parser.add_argument("--readiness-report-dir", default="reports/unified_readiness")
    parser.add_argument("--session-date")
    parser.add_argument("--reconstruct-if-late", action="store_true")
    args = parser.parse_args(argv)
    registry = args.registry or _default_registry_for_mode(args)
    if args.preflight_complete_session:
        result = run_complete_session_preflight(
            repo_root=REPO_ROOT,
            registry_path=registry,
            report_dir=args.supervisor_report_dir,
            db_path=args.db_path,
        )
        readiness = build_authoritative_readiness_projection(
            repo_root=REPO_ROOT,
            report_dir=REPO_ROOT / args.readiness_report_dir,
        )
        print(result.verdict)
        if result.reasons:
            print("Reasons:")
            for reason in result.reasons:
                print(f"- {reason}")
        print(f"Report: {result.report_path}")
        print(f"Authoritative readiness: {readiness.report_path}")
        print(f"Clean-start package: {readiness.operator_package_md}")
        return 0 if result.verdict == "READY_FOR_COMPLETE_UNIFIED_SESSION" else 1
    if args.live_observation_only:
        live_dir = f"reports/live_session_{datetime_now_ist().strftime('%Y%m%d')}"
        result = run_live_observation(
            repo_root=REPO_ROOT,
            registry_path=registry,
            report_dir=live_dir,
            dashboard_port=args.dashboard_port,
        )
        print("TFIS unified live observation completed.")
        print(f"Reports: {result.report_dir}")
        print(f"Verdict: {result.verdict}")
        print(f"Session: {result.session_id}")
        print(f"Report count: {len(result.files)}")
        return 0
    if args.continuous_supervisor:
        result = run_continuous_supervisor(
            repo_root=REPO_ROOT,
            registry_path=registry,
            report_dir=args.supervisor_report_dir,
            state_root=args.supervisor_state_root,
            dashboard_output_root=args.dashboard_output_root,
            db_path=args.db_path,
            dashboard_port=args.dashboard_port,
            poll_seconds=args.poll_seconds,
            max_iterations=args.max_iterations,
            session_date=date.fromisoformat(args.session_date) if args.session_date else None,
            reconstruct_if_late=args.reconstruct_if_late,
        )
        print("TFIS continuous unified internal-paper supervisor completed.")
        print(f"Verdict: {result.verdict}")
        print(f"Session: {result.session_id}")
        print(f"Final state: {result.final_state}")
        print(f"Iterations: {result.iterations}")
        print(f"Reports: {result.report_dir}")
        print(f"Snapshot: {result.snapshot_json}")
        print(f"Heartbeat: {result.heartbeat_json}")
        print(f"Database: {result.db_path}")
        return 0
    reports = build_unified_runtime_reports(REPO_ROOT / registry, REPO_ROOT / args.report_dir)
    print("TFIS unified internal-paper certification completed.")
    print(f"Reports: {REPO_ROOT / args.report_dir}")
    print(f"Report count: {len(reports)}")
    return 0


def datetime_now_ist():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(tz=ZoneInfo("Asia/Calcutta"))


def _default_registry_for_mode(args: argparse.Namespace) -> str:
    if args.live_observation_only or args.continuous_supervisor or args.preflight_complete_session:
        return "config/live_market_internal_paper_strategy_instances.yaml"
    return "config/internal_paper_strategy_instances.yaml"


if __name__ == "__main__":
    raise SystemExit(main())
