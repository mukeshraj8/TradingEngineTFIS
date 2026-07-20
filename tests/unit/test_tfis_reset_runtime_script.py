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
