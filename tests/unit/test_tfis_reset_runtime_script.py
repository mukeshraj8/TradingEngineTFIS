from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _script_text(name: str) -> str:
    return (REPO_ROOT / "scripts" / name).read_text(encoding="utf-8")


def test_reset_script_waits_for_old_tfis_runtime_before_restarting() -> None:
    script = _script_text("reset_tfis_dashboard_and_watchers.ps1")
    helper_script = _script_text("tfis_runtime_process_helpers.ps1")

    assert '. $runtimeProcessHelperPath' in script
    assert "function Get-TfisProcessCandidates" in helper_script
    assert "function Get-TfisRuntimeProcesses" in helper_script
    assert "build_operator_dashboard\\.py|serve_operator_dashboard\\.py" in helper_script
    assert "function Wait-ForNoTfisRuntimeProcesses" in helper_script
    assert "throw \"Timed out waiting for TFIS runtime processes to exit" in helper_script
    assert "taskkill.exe" in helper_script
    assert "Stop-TfisRuntimeProcesses -RepoRoot $repoRoot -CurrentProcessId $PID" in script
    assert "This command stops and restarts the TFIS paper runtime." in script
    assert "refresh_tfis_operator_dashboard.ps1" in script


def test_reset_script_skips_duplicate_dashboard_and_supervisor_recovery_processes() -> None:
    script = _script_text("reset_tfis_dashboard_and_watchers.ps1")
    helper_script = _script_text("tfis_runtime_process_helpers.ps1")

    assert "function Get-TfisExistingDashboardProcess" in script
    assert "run_tfis_paper_lifecycle_supervisor\\.py" in helper_script
    assert ". $supervisorHelperPath" in script
    assert "Start-TfisPaperLifecycleSupervisorProcess" in script
    assert "Started shared TFIS paper lifecycle supervisor PID=" in script


def test_stop_script_uses_shared_runtime_process_helper() -> None:
    script = _script_text("stop_tfis_runtime.ps1")
    helper_script = _script_text("tfis_runtime_process_helpers.ps1")

    assert '. $runtimeProcessHelperPath' in script
    assert '$Host.UI.RawUI.WindowTitle = "TFIS Runtime Stop"' in script
    assert "TFIS RUNTIME STOP" in script
    assert "This window belongs to TradingEngineTFIS only." in script
    assert "Stop-TfisRuntimeProcesses -RepoRoot $repoRoot -CurrentProcessId $PID" in script
    assert "stop_tfis_runtime\\.ps1" in helper_script


def test_pause_and_resume_scripts_use_shared_operator_control_helper() -> None:
    pause_script = _script_text("pause_tfis_runtime.ps1")
    resume_script = _script_text("resume_tfis_runtime.ps1")
    helper_script = _script_text("tfis_operator_control_helpers.ps1")

    assert '. $operatorControlHelperPath' in pause_script
    assert '. $operatorControlHelperPath' in resume_script
    assert "TFIS RUNTIME PAUSE" in pause_script
    assert "TFIS RUNTIME RESUME" in resume_script
    assert "Set-TfisOperatorPauseMarker" in pause_script
    assert "Clear-TfisOperatorPauseMarker" in resume_script
    assert "function Resolve-TfisOperatorControlRoot" in helper_script
    assert "function Get-TfisGlobalPauseMarkerPath" in helper_script
    assert "function Get-TfisStrategyPauseMarkerPath" in helper_script
    assert "function Get-TfisOperatorControlEventLogPath" in helper_script
    assert "function Get-TfisLatestOperatorControlEvent" in helper_script
    assert "function Set-TfisOperatorPauseMarker" in helper_script
    assert "function Clear-TfisOperatorPauseMarker" in helper_script
    assert "function Write-TfisOperatorControlEvent" in helper_script


def test_status_script_reads_shared_runtime_and_operator_control_state() -> None:
    status_script = _script_text("show_tfis_runtime_status.ps1")
    guardrail_script = _script_text("show_paper_runtime_guardrail_status.py")
    broker_health_script = _script_text("show_paper_runtime_broker_health_status.py")
    heartbeat_script = _script_text("show_paper_runtime_heartbeat_status.py")
    order_routing_script = _script_text("show_paper_runtime_order_routing_status.py")
    reconciliation_script = _script_text("show_paper_runtime_reconciliation_status.py")
    fresh_entry_handoff_script = _script_text("show_paper_runtime_fresh_entry_handoff_status.py")

    assert '. $runtimeProcessHelperPath' in status_script
    assert '. $operatorControlHelperPath' in status_script
    assert '$Host.UI.RawUI.WindowTitle = "TFIS Runtime Status"' in status_script
    assert '[switch]$RequireToken' in status_script
    assert "TFIS RUNTIME STATUS" in status_script
    assert "function Test-TfisDashboardPortReady" in status_script
    assert 'show_paper_runtime_guardrail_status.py' in status_script
    assert 'show_paper_runtime_broker_health_status.py' in status_script
    assert 'show_paper_runtime_heartbeat_status.py' in status_script
    assert 'show_paper_runtime_order_routing_status.py' in status_script
    assert 'show_paper_runtime_reconciliation_status.py' in status_script
    assert 'show_paper_runtime_fresh_entry_handoff_status.py' in status_script
    assert "PaperGuardrails:" in status_script
    assert "BrokerHealth:" in status_script
    assert '$brokerHealthArgs += "--require-token"' in status_script
    assert "RuntimeHeartbeats:" in status_script
    assert "OrderRoutingSafety:" in status_script
    assert "RuntimeReconciliation:" in status_script
    assert "FreshEntryHandoffs:" in status_script
    assert "Get-TfisLatestOperatorControlEvent" in status_script
    assert "Get-TfisRuntimeProcesses -RepoRoot $repoRoot" in status_script
    assert "DashboardPortReady:" in status_script
    assert "DashboardProcesses:" in status_script
    assert "SupervisorProcesses:" in status_script
    assert "load_paper_runtime_guardrail_statuses" in guardrail_script
    assert "GuardrailStatus:" in guardrail_script
    assert "load_paper_runtime_broker_health_statuses" in broker_health_script
    assert "BrokerHealthStatus:" in broker_health_script
    assert "load_paper_runtime_heartbeat_statuses" in heartbeat_script
    assert "HeartbeatStatus:" in heartbeat_script
    assert "owner_id=" in heartbeat_script
    assert "state_directory=" in heartbeat_script
    assert "load_paper_runtime_order_routing_statuses" in order_routing_script
    assert "OrderRoutingStatus:" in order_routing_script
    assert "load_paper_runtime_reconciliation_statuses" in reconciliation_script
    assert "ReconciliationStatus:" in reconciliation_script
    assert "load_paper_runtime_fresh_entry_handoff_statuses" in fresh_entry_handoff_script
    assert "FreshEntryHandoffStatus:" in fresh_entry_handoff_script


def test_reset_script_keeps_dashboard_and_supervisor_recovery_windows_visible() -> None:
    script = _script_text("reset_tfis_dashboard_and_watchers.ps1")
    supervisor_helper_script = _script_text("tfis_paper_lifecycle_supervisor_helpers.ps1")

    assert script.count("-WindowStyle Normal") >= 1
    assert supervisor_helper_script.count("-WindowStyle Normal") >= 1
    assert "-WindowStyle Hidden" not in script
    assert '"--skip-build"' in script
    assert "function Wait-ForDashboardReady" in script
    assert "TFIS dashboard is accepting connections." in script
    assert "Skipping TFIS dashboard start because matching server is already running" in script


def test_reset_script_delegates_recovery_to_shared_supervisor() -> None:
    script = _script_text("reset_tfis_dashboard_and_watchers.ps1")
    supervisor_helper_script = _script_text("tfis_paper_lifecycle_supervisor_helpers.ps1")

    assert '. $paperPositionHelperPath' in script
    assert '. $supervisorHelperPath' in script
    assert '"-TargetsConfig (Resolve-TfisPath $TargetsConfig)' not in script
    assert "Start-TfisPaperLifecycleSupervisorProcess" in script
    assert "-SkipRefresh" in script
    assert "Started shared TFIS paper lifecycle supervisor PID=" in script
    assert "Get-TfisLivePositionStateDirectories" not in script
    assert '[switch]$SkipRefresh' in supervisor_helper_script
    assert '$supervisorArgs += "-SkipRefresh"' in supervisor_helper_script


def test_refresh_script_rebuilds_dashboard_without_stopping_runtime() -> None:
    script = _script_text("refresh_tfis_operator_dashboard.ps1")

    assert '. $runtimeProcessHelperPath' in script
    assert "TFIS OPERATOR DASHBOARD REFRESH" in script
    assert "It does not stop or restart the shared TFIS paper runtime." in script
    assert 'build_operator_dashboard.py' in script
    assert 'serve_operator_dashboard.py' in script
    assert 'Stop-TfisRuntimeProcesses' not in script
    assert "Reusing existing TFIS dashboard server PID=" in script
    assert "TFIS operator dashboard refresh complete in" in script
