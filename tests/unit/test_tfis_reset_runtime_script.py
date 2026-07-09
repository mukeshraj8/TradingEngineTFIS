from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _script_text(name: str) -> str:
    return (REPO_ROOT / "scripts" / name).read_text(encoding="utf-8")


def test_reset_script_waits_for_old_tfis_runtime_before_restarting() -> None:
    script = _script_text("reset_tfis_dashboard_and_watchers.ps1")

    assert "function Get-TfisRuntimeProcesses" in script
    assert "function Wait-ForNoTfisRuntimeProcesses" in script
    assert "throw \"Timed out waiting for TFIS runtime processes to exit" in script
    assert "Wait-ForNoTfisRuntimeProcesses" in script


def test_reset_script_skips_duplicate_dashboard_and_watcher_processes() -> None:
    script = _script_text("reset_tfis_dashboard_and_watchers.ps1")

    assert "function Get-TfisExistingDashboardProcess" in script
    assert "function Get-TfisExistingWatcherProcess" in script
    assert '$seenTargets = @{}' in script
    assert "Skipping duplicate $StrategyCode watcher target" in script


def test_reset_script_keeps_dashboard_and_watchers_visible() -> None:
    script = _script_text("reset_tfis_dashboard_and_watchers.ps1")

    assert script.count("-WindowStyle Normal") >= 2
    assert "-WindowStyle Hidden" not in script
    assert "Skipping $StrategyCode watcher start because matching process is already running" in script
    assert "Skipping TFIS dashboard start because matching server is already running" in script


def test_reset_script_only_restores_same_day_waiting_orders_and_live_positions() -> None:
    script = _script_text("reset_tfis_dashboard_and_watchers.ps1")

    assert "function Test-TfisWatchablePositionState" in script
    assert "function Get-TfisLivePositionStateDirectories" in script
    assert '$sessionIsToday = $SessionDate -eq (Get-Date).ToString("yyyy-MM-dd")' in script
    assert 'foreach ($stateDir in @(Get-TfisLivePositionStateDirectories -ArtifactRoot $ArtifactRoot -EffectiveDate $effectiveDate))' in script
    assert 'if ($metadataJson.branch_order_state_json -and $sessionIsToday)' in script
    assert "Skipping stale waiting-order watcher startup for prior session $SessionDate" in script
    assert "Skipping non-carry-forward paper position state during recovery scan" in script
    assert "Skipping expired paper position state during recovery scan" in script
    assert '"PAPER_POSITION_OPEN"' in script
    assert '"PAPER_POSITION_CARRIED_FORWARD"' in script
    assert '"PAPER_POSITION_RESUMED"' in script
