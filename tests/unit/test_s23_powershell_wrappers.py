from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DURABLE_S23_ARTIFACT_ROOT = "data/strategies/S23/fyers_morning_supervised_decision"


def _script_text(name: str) -> str:
    return (REPO_ROOT / "scripts" / name).read_text(encoding="utf-8")


def test_morning_wrapper_does_not_stream_supervised_decision_through_pipeline() -> None:
    script = _script_text("start_s23_fyers_morning_supervised_decision.ps1")

    assert f'[string]$ArtifactRoot = "{DURABLE_S23_ARTIFACT_ROOT}"' in script
    assert "2>&1 | ForEach-Object" not in script
    assert "run_s23_fyers_0916_supervised_decision_$stamp.out.log" in script
    assert "run_s23_fyers_0916_supervised_decision_$stamp.err.log" in script
    assert "& $pythonExe @args > $pythonOutputPath 2> $pythonErrorPath" in script
    assert 'Write-LaunchLog "Morning supervised decision finished with exit code $exitCode."' in script


def test_morning_wrapper_starts_watchers_from_current_session_metadata_and_open_positions() -> None:
    script = _script_text("start_s23_fyers_morning_supervised_decision.ps1")

    assert "function Resolve-TfisAbsolutePathText" in script
    assert "function Resolve-TfisPositionStateDirectory" in script
    assert "[System.IO.Path]::GetFullPath" in script
    assert "function Get-TfisLatestSessionMetadata" in script
    assert "function Get-TfisOpenPositionStatePaths" in script
    assert 'Join-Path $artifactRootPath $Date.ToString("yyyy-MM-dd")' in script
    assert "Get-TfisLatestSessionMetadata -Date $effectiveRunDate" in script
    assert "Using S23 metadata for watcher startup" in script
    assert 'Get-ChildItem -Path $artifactRootPath -Recurse -Filter "paper_position_state.json"' in script
    assert "Discovered $($openCarryForwardStatePaths.Count) open/carry-forward S23 paper position state file(s) for watcher startup." in script
    assert "Passing latest discovered open S23 paper position to supervised decision" in script
    assert "$discoveredCarryForwardStatePaths = @(Get-TfisOpenPositionStatePaths -Date $effectiveRunDate)" in script
    assert "$openCarryForwardStatePaths = @(Get-TfisOpenPositionStatePaths -Date $effectiveRunDate)" in script
    assert "$openStatePaths = @(Get-TfisOpenPositionStatePaths -Date $effectiveRunDate)" in script
    assert "$discoveredCarryForwardStatePath = Resolve-TfisAbsolutePathText -PathText ([string]$discoveredCarryForwardStatePaths[0])" in script
    assert "$discoveredCarryForwardStateDir = Resolve-TfisPositionStateDirectory -PathText $discoveredCarryForwardStatePath" in script
    assert "$args += $discoveredCarryForwardStateDir" in script


def test_morning_wrapper_normalizes_carry_forward_paths_before_subprocess_handoff() -> None:
    script = _script_text("start_s23_fyers_morning_supervised_decision.ps1")

    assert "$carryForwardStateDirArg = Resolve-TfisPositionStateDirectory -PathText $CarryForwardStateDir" in script
    assert "$args += $carryForwardStateDirArg" in script
    assert "Carry-forward state directory argument: $discoveredCarryForwardStateDir" in script
    assert "$watchArgs += $normalizedWatchDirectory" in script
    assert "$watchArgs += $normalizedSearchRoot" in script
    assert "directory=$normalizedWatchDirectory, searchRoot=$normalizedSearchRoot" in script


def test_s23_watcher_launchers_start_mixed_position_and_order_branches() -> None:
    morning_wrapper = _script_text("start_s23_fyers_morning_supervised_decision.ps1")
    recovery_launcher = _script_text("start_s23_paper_watchers_from_metadata.ps1")

    for script in (morning_wrapper, recovery_launcher):
        assert "$stateDirectories" in script
        assert "branch_position_state_json" in script
        assert "branch_order_state_json" in script
        assert "ContainsKey($orderDir)" in script
        assert 'Join-Path $orderDir "paper_position_state.json"' in script

    assert 'if ($orderPaths.Count -gt 0)' in morning_wrapper
    assert 'elseif ($orderPaths.Count -gt 0)' not in morning_wrapper
    assert '$watcherStartCount -eq 0' in morning_wrapper
    assert 'if ($metadataJson.branch_order_state_json)' in recovery_launcher
    assert 'if ($watchTargets.Count -eq 0 -and $metadataJson.branch_order_state_json)' not in recovery_launcher


def test_tfis_watcher_windows_are_visible_and_self_identifying() -> None:
    script = _script_text("start_s23_fyers_morning_supervised_decision.ps1")

    assert '$Host.UI.RawUI.WindowTitle = "TFIS S23 Morning Supervised Decision"' in script
    assert "This window belongs to TradingEngineTFIS only." in script
    assert "TFIS S23 PAPER WATCHER" in script
    assert "-WindowStyle Normal" in script
    assert "-WindowStyle Hidden" not in script


def test_morning_wrapper_launches_watcher_script_as_encoded_command() -> None:
    script = _script_text("start_s23_fyers_morning_supervised_decision.ps1")

    assert "[System.Text.Encoding]::Unicode.GetBytes($watchCommand)" in script
    assert '"-EncodedCommand", $encodedWatchCommand' in script
    assert '"-Command", $watchCommand' not in script
    assert "This window is held open for review; it is safe to close" in script


def test_s23_operational_wrappers_default_to_durable_data_artifact_root() -> None:
    scripts = (
        "start_s23_fyers_morning_supervised_decision.ps1",
        "start_s23_paper_watchers_from_metadata.ps1",
        "start_s23_paper_order_finalizer.ps1",
        "register_s23_fyers_morning_supervised_task.ps1",
        "register_s23_paper_order_finalizer_task.ps1",
    )

    for script_name in scripts:
        script = _script_text(script_name)
        assert f'[string]$ArtifactRoot = "{DURABLE_S23_ARTIFACT_ROOT}"' in script

    for script_name in (
        "register_s23_fyers_morning_supervised_task.ps1",
        "register_s23_paper_order_finalizer_task.ps1",
    ):
        script = _script_text(script_name)
        assert f'$defaultArtifactRoot = "{DURABLE_S23_ARTIFACT_ROOT}"' in script


def test_s23_operational_python_entrypoints_default_to_durable_data_artifact_root() -> None:
    scripts = (
        "run_s23_fyers_0916_supervised_decision.py",
        "run_s23_paper_position_watch.py",
        "finalize_s23_pending_paper_orders.py",
        "build_operator_dashboard.py",
        "serve_operator_dashboard.py",
    )

    for script_name in scripts:
        script = _script_text(script_name)
        assert f'"{DURABLE_S23_ARTIFACT_ROOT}"' in script
