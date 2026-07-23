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
    assert "function New-TfisPathRegex" in helper_script
    assert "function Get-TfisRuntimeProcesses" in helper_script
    assert "function Get-TfisPortOwnerProcesses" in helper_script
    assert "function Get-TfisRuntimeProcessRole" in helper_script
    assert "build_operator_dashboard\\.py|serve_operator_dashboard\\.py" in helper_script
    assert "reset_tfis_dashboard_and_watchers\\.ps1" in helper_script
    assert "start_s21_fyers_morning_supervised_decision\\.ps1" in helper_script
    assert "start_s23_fyers_morning_supervised_decision\\.ps1" in helper_script
    assert "ParentProcessId" in helper_script
    assert "Get-NetTCPConnection -LocalAddress \"127.0.0.1\" -LocalPort $Port -State Listen" in helper_script
    assert "netstat.exe -ano" in helper_script
    assert "LISTENING" in helper_script
    assert "Get-Process -Id $processId" in helper_script
    assert "CommandLine = $null" in helper_script
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
    lifecycle_audit_script = _script_text("show_paper_runtime_lifecycle_audit_status.py")
    waiting_order_script = _script_text("show_paper_runtime_waiting_order_status.py")
    order_routing_script = _script_text("show_paper_runtime_order_routing_status.py")
    reconciliation_script = _script_text("show_paper_runtime_reconciliation_status.py")
    fresh_entry_handoff_script = _script_text("show_paper_runtime_fresh_entry_handoff_status.py")

    assert '. $runtimeProcessHelperPath' in status_script
    assert '. $operatorControlHelperPath' in status_script
    assert '$Host.UI.RawUI.WindowTitle = "TFIS Runtime Status"' in status_script
    assert '[switch]$RequireToken' in status_script
    assert '[datetime]$RunDate = (Get-Date)' in status_script
    assert '[string]$TradingHolidayCalendar = "config/nse_trading_holidays_2026.json"' in status_script
    assert "TFIS RUNTIME STATUS" in status_script
    assert "function Test-TfisDashboardPortReady" in status_script
    assert "function Get-TfisRestartRecoveryStatus" in status_script
    assert "function Get-TfisMarketSessionPhase" in status_script
    assert ". $tradingCalendarHelperPath" in status_script
    assert "MarketSessionPhase:" in status_script
    assert 'show_paper_runtime_guardrail_status.py' in status_script
    assert 'show_paper_runtime_broker_health_status.py' in status_script
    assert 'show_paper_runtime_heartbeat_status.py' in status_script
    assert 'show_paper_runtime_lifecycle_audit_status.py' in status_script
    assert 'show_paper_runtime_waiting_order_status.py' in status_script
    assert 'show_paper_runtime_order_routing_status.py' in status_script
    assert 'show_paper_runtime_reconciliation_status.py' in status_script
    assert 'show_paper_runtime_fresh_entry_handoff_status.py' in status_script
    assert "PaperGuardrails:" in status_script
    assert "BrokerHealth:" in status_script
    assert '$brokerHealthArgs += "--require-token"' in status_script
    assert "RuntimeHeartbeats:" in status_script
    assert "LifecycleAudit:" in status_script
    assert "$lifecycleAuditArgs = @($lifecycleAuditScript)" in status_script
    assert '$lifecycleAuditArgs += @("--stale-after-seconds", "86400")' in status_script
    assert "WaitingOrders:" in status_script
    assert "RestartRecoveryStatus:" in status_script
    assert "READY_FOR_MORNING_STARTUP" in status_script
    assert "ACTION_REQUIRED" in status_script
    assert "STOPPED_AFTER_MARKET" in status_script
    assert "AFTER_MARKET_IDLE" in status_script
    assert "ACTIVE_MARKET" in status_script
    assert "POST_MARKET" in status_script
    assert "resolve_stale_waiting_orders" in status_script
    assert "start_or_recover_dashboard" in status_script
    assert "start_shared_supervisor" in status_script
    assert "OrderRoutingSafety:" in status_script
    assert "RuntimeReconciliation:" in status_script
    assert "FreshEntryHandoffs:" in status_script
    assert "actor=$(if ($latestEvent.actor)" in status_script
    assert "reason=$(if ($latestEvent.reason)" in status_script
    assert "marker=$(if ($latestEvent.marker_path)" in status_script
    assert "Get-TfisLatestOperatorControlEvent" in status_script
    assert "Get-TfisRuntimeProcesses -RepoRoot $repoRoot" in status_script
    assert "DashboardPortReady:" in status_script
    assert "DashboardPortOwnerProcesses:" in status_script
    assert "DashboardProcesses:" in status_script
    assert "SupervisorProcesses:" in status_script
    assert "Get-TfisRuntimeProcessRole -CommandLine $_.CommandLine" in status_script
    assert "Role={2}" in status_script
    assert "Role=dashboard_port_owner" in status_script
    assert "load_paper_runtime_guardrail_statuses" in guardrail_script
    assert "GuardrailStatus:" in guardrail_script
    assert "load_paper_runtime_broker_health_statuses" in broker_health_script
    assert "BrokerHealthStatus:" in broker_health_script
    assert "load_paper_runtime_heartbeat_statuses" in heartbeat_script
    assert "HeartbeatStatus:" in heartbeat_script
    assert "owner_id=" in heartbeat_script
    assert "state_directory=" in heartbeat_script
    assert "load_paper_runtime_lifecycle_audit_statuses" in lifecycle_audit_script
    assert "LifecycleAuditStatus:" in lifecycle_audit_script
    assert "load_paper_runtime_waiting_order_statuses" in waiting_order_script
    assert "WaitingOrderStatus:" in waiting_order_script
    assert "load_paper_runtime_order_routing_statuses" in order_routing_script
    assert "OrderRoutingStatus:" in order_routing_script
    assert "load_paper_runtime_reconciliation_statuses" in reconciliation_script
    assert "ReconciliationStatus:" in reconciliation_script
    assert "load_paper_runtime_fresh_entry_handoff_statuses" in fresh_entry_handoff_script
    assert "FreshEntryHandoffStatus:" in fresh_entry_handoff_script


def test_status_script_is_market_phase_aware_for_supervisor_recovery() -> None:
    status_script = _script_text("show_tfis_runtime_status.ps1")

    assert 'if ($MarketSessionPhase -eq "ACTIVE_MARKET")' in status_script
    assert '$pending += "start_shared_supervisor"' in status_script
    assert 'elseif ($MarketSessionPhase -eq "PRE_MARKET")' in status_script
    assert '$pending += "run_morning_startup"' in status_script
    assert 'elseif (($MarketSessionPhase -eq "POST_MARKET") -and ($SupervisorProcessCount -eq 0))' in status_script
    assert "no shared supervisor restart is required" in status_script
    assert "TFIS appears stopped during active market; operator recovery is required." in status_script


def test_runtime_process_helper_matches_windows_path_variants_and_child_processes() -> None:
    helper_script = _script_text("tfis_runtime_process_helpers.ps1")

    assert "$segments = @($fullPath -split '[\\\\/]+'" in helper_script
    assert "-join '[\\\\/]+'" in helper_script
    assert "$repoPattern = New-TfisPathRegex -PathText $RepoRoot" in helper_script
    assert "$matchedById[[int]$proc.ProcessId] = $proc" in helper_script
    assert "$parentProcessId = [int]$proc.ParentProcessId" in helper_script
    assert "$matchedById.ContainsKey($parentProcessId)" in helper_script
    assert "Name = 'py.exe'" in helper_script


def test_runtime_process_helper_exposes_operator_roles() -> None:
    helper_script = _script_text("tfis_runtime_process_helpers.ps1")

    assert "return \"dashboard\"" in helper_script
    assert "return \"supervisor\"" in helper_script
    assert "return \"morning_strategy\"" in helper_script
    assert "return \"position_watcher\"" in helper_script
    assert "return \"dashboard_maintenance\"" in helper_script
    assert "return \"runtime_startup\"" in helper_script
    assert "return \"runtime_stop\"" in helper_script


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


def test_reset_script_supports_single_application_morning_startup() -> None:
    script = _script_text("reset_tfis_dashboard_and_watchers.ps1")

    assert "[switch]$MorningStartup" in script
    assert "[switch]$SkipAuthPreparation" in script
    assert "TFIS APPLICATION MORNING STARTUP" in script
    assert "Get-TfisMorningStartupWrapperPaths" in script
    assert "wrapper_script_path" in script
    assert "for wrapper in wrappers:" in script
    assert "print(wrapper)" in script
    assert "ConvertFrom-Json" not in script
    assert "Invoke-TfisRuntimeAuthPreparation" in script
    assert script.count("$pythonCode = @'") >= 2
    assert "encoding='utf-8'" in script
    assert "data.get('targets', [])" in script
    assert "target.get('wrapper_script_path')" in script
    assert "load_paper_lifecycle_supervisor_target_specs" in script
    assert "prepare_paper_broker_runtime_environment" in script
    assert "skip_refresh=False" in script
    assert "print('Prepared TFIS broker runtime auth for provider=' + provider)" in script
    assert "Invoke-TfisMorningStartupWrappers" in script
    assert "$script:MorningWrapperFailures = @()" in script
    assert "$wrapperProcesses = @()" in script
    assert "Start-Process `" in script
    assert "Started TFIS morning wrapper PID=" in script
    assert "Waiting for TFIS morning wrapper PID=" in script
    assert "$wrapperProcess.WaitForExit()" in script
    assert "TFIS morning wrapper completed successfully" in script
    assert "WARNING: TFIS morning startup wrapper failed with exit code" in script
    assert "Invoke-TfisMorningStartupWrappers" in script
    assert "$script:MorningWrapperFailures.Count" in script
    assert "dashboard and shared supervisor startup were still attempted" in script
    assert "-SkipRefresh" in script
    assert "-DisablePositionWatch" in script
    assert "morning startup will not stop them automatically" in script
    startup_body = script.split("$resetStopwatch", maxsplit=1)[1]
    assert startup_body.index("Invoke-TfisRuntimeAuthPreparation") < startup_body.index(
        'scripts/build_operator_dashboard.py'
    )


def test_reset_script_blocks_unforced_full_reset_during_market_session() -> None:
    script = _script_text("reset_tfis_dashboard_and_watchers.ps1")

    assert "[switch]$ForceInMarketReset" in script
    assert "[string]$TradingHolidayCalendar" in script
    assert '. $tradingCalendarHelperPath' in script
    assert "function Test-TfisMarketSessionActive" in script
    assert 'TimeSpan]::Parse("09:15:00")' in script
    assert 'TimeSpan]::Parse("15:30:00")' in script
    assert "Refusing full TFIS runtime reset during the active market session without -ForceInMarketReset" in script
    assert "refresh_tfis_operator_dashboard.ps1" in script


def test_refresh_script_rebuilds_dashboard_without_stopping_runtime() -> None:
    script = _script_text("refresh_tfis_operator_dashboard.ps1")

    assert '. $runtimeProcessHelperPath' in script
    assert "TFIS OPERATOR DASHBOARD REFRESH" in script
    assert "It does not stop or restart the shared TFIS paper runtime." in script
    assert 'build_operator_dashboard.py' in script
    assert 'serve_operator_dashboard.py' in script
    assert 'Stop-TfisRuntimeProcesses' not in script
    assert "Reusing existing TFIS dashboard server PID=" in script
    assert "Get-TfisPortOwnerProcesses -Port $DashboardPort" in script
    assert "TFIS operator dashboard refresh complete in" in script


def test_reset_and_refresh_scripts_fallback_to_dashboard_port_owner() -> None:
    reset_script = _script_text("reset_tfis_dashboard_and_watchers.ps1")
    refresh_script = _script_text("refresh_tfis_operator_dashboard.ps1")

    for script in (reset_script, refresh_script):
        assert "$matches = @(Get-TfisRuntimeProcesses -RepoRoot $repoRoot -RuntimePattern $pattern)" in script
        assert "if ($matches.Count -gt 0)" in script
        assert "return @(Get-TfisPortOwnerProcesses -Port $DashboardPort)" in script
