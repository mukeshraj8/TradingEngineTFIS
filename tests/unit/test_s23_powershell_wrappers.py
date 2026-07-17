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
    assert "Start-TfisHiddenPythonProcess" in script
    assert 'Write-LaunchLog "Morning supervised decision finished with exit code $exitCode."' in script


def test_morning_wrapper_starts_supervisor_from_current_session_metadata_and_open_positions() -> None:
    script = _script_text("start_s23_fyers_morning_supervised_decision.ps1")

    assert '. $paperPositionHelperPath' in script
    assert '. $supervisorHelperPath' in script
    assert '. $tradingCalendarHelperPath' in script
    assert '. $wrapperTaskHelperPath' in script
    assert "Write-TfisTaskLogMessage" in script
    assert "Show-TfisTaskBanner" in script
    assert "Get-TfisResumablePaperPositionStatePaths" in script
    assert "Resolve-TfisAbsolutePathText -RepoRoot $repoRoot" in script
    assert "Resolve-TfisPositionStateDirectoryPath -RepoRoot $repoRoot" in script
    assert "function Get-TfisLatestSessionMetadata" in script
    assert "Get-TfisLatestSessionMetadataFile -ArtifactRoot $artifactRootPath -SessionDate $Date" in script
    assert "function Get-TfisOpenPositionStatePaths" in script
    assert "Get-TfisLatestSessionMetadata -Date $effectiveRunDate" in script
    assert "Using S23 metadata for supervisor startup" in script
    assert "Get-TfisResumablePaperPositionStatePaths" in script
    assert "Discovered $($openCarryForwardStatePaths.Count) open/carry-forward S23 paper position state file(s) for supervisor startup." in script
    assert "Passing latest discovered open S23 paper position to supervised decision" in script
    assert "$discoveredCarryForwardStatePaths = @(Get-TfisOpenPositionStatePaths -Date $effectiveRunDate)" in script
    assert "$openCarryForwardStatePaths = @(Get-TfisOpenPositionStatePaths -Date $effectiveRunDate)" in script
    assert "$discoveredCarryForwardStatePath = Resolve-TfisAbsolutePathText -RepoRoot $repoRoot -PathText ([string]$discoveredCarryForwardStatePaths[0])" in script
    assert "$discoveredCarryForwardStateDir = Resolve-TfisPositionStateDirectoryPath -RepoRoot $repoRoot -PathText $discoveredCarryForwardStatePath" in script
    assert "$args += $discoveredCarryForwardStateDir" in script
    assert "Start-TfisPaperLifecycleSupervisorProcess" in script
    assert "Starting shared TFIS paper lifecycle supervisor" in script
    assert "function Start-S23PaperWatchProcess" not in script


def test_morning_wrapper_normalizes_carry_forward_paths_before_subprocess_handoff() -> None:
    script = _script_text("start_s23_fyers_morning_supervised_decision.ps1")

    assert "$carryForwardStateDirArg = Resolve-TfisPositionStateDirectoryPath -RepoRoot $repoRoot -PathText $CarryForwardStateDir" in script
    assert "$args += $carryForwardStateDirArg" in script
    assert "Carry-forward state directory argument: $discoveredCarryForwardStateDir" in script
    assert "function Start-TfisSharedSupervisor" in script
    assert "-SessionDate $SessionDate" in script or "-SessionDate\", $SessionDate" in script


def test_s23_compatibility_launchers_delegate_to_shared_supervisor() -> None:
    morning_wrapper = _script_text("start_s23_fyers_morning_supervised_decision.ps1")
    recovery_launcher = _script_text("start_s23_paper_watchers_from_metadata.ps1")
    s21_recovery_launcher = _script_text("start_s21_paper_watchers_from_metadata.ps1")

    assert '. $supervisorHelperPath' in morning_wrapper
    assert "Started shared TFIS paper lifecycle supervisor PID=" in morning_wrapper
    assert '. $supervisorHelperPath' in recovery_launcher
    assert "Start-TfisPaperLifecycleSupervisorProcess" in recovery_launcher
    assert '$Host.UI.RawUI.WindowTitle = "TFIS S23 Supervisor Compatibility Launcher"' in recovery_launcher
    assert "TFIS S23 supervisor compatibility launcher" in recovery_launcher
    assert "This compatibility launcher now starts one supervisor process for S21 and S23 together." in recovery_launcher
    assert '. $supervisorHelperPath' in s21_recovery_launcher
    assert "Start-TfisPaperLifecycleSupervisorProcess" in s21_recovery_launcher
    assert '$Host.UI.RawUI.WindowTitle = "TFIS S21 Supervisor Compatibility Launcher"' in s21_recovery_launcher
    assert "TFIS S21 supervisor compatibility launcher" in s21_recovery_launcher
    assert "This compatibility launcher now starts one supervisor process for S21 and S23 together." in s21_recovery_launcher


def test_tfis_supervisor_window_is_visible_and_self_identifying() -> None:
    script = _script_text("start_tfis_paper_lifecycle_supervisor.ps1")

    assert '$Host.UI.RawUI.WindowTitle = "TFIS Paper Lifecycle Supervisor Launcher"' in script
    assert "This window belongs to TradingEngineTFIS only." in script
    assert "TFIS PAPER LIFECYCLE SUPERVISOR" in script
    assert "-WindowStyle Normal" in script


def test_shared_supervisor_launcher_runs_python_supervisor_script() -> None:
    script = _script_text("start_tfis_paper_lifecycle_supervisor.ps1")

    assert "run_tfis_paper_lifecycle_supervisor.py" in script
    assert '"--targets-config"' in script or "'--targets-config'" in script
    assert '"--session-date"' in script or "'--session-date'" in script
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


def test_s23_morning_task_registration_defaults_if_past_to_run_now() -> None:
    script = _script_text("register_s23_fyers_morning_supervised_task.ps1")

    assert '[string]$IfPast = "run_now"' in script
    assert '$defaultIfPast = "run_now"' in script


def test_s21_operational_scripts_exist_for_daily_startup() -> None:
    start_script = _script_text("start_s21_fyers_morning_supervised_decision.ps1")
    register_script = _script_text("register_s21_fyers_morning_supervised_task.ps1")
    check_script = _script_text("check_s21_fyers_morning_supervised_task.ps1")
    launcher_script = _script_text("start_tfis_paper_lifecycle_supervisor.ps1")

    assert '[string]$ArtifactRoot = "data/strategies/S21/fyers_morning_supervised_decision"' in start_script
    assert '[string]$IfPast = "run_now"' in start_script
    assert '. $paperPositionHelperPath' in start_script
    assert '. $tradingCalendarHelperPath' in start_script
    assert '. $wrapperTaskHelperPath' in start_script
    assert "Write-TfisTaskLogMessage" in start_script
    assert "Start-TfisHiddenPythonProcess" in start_script
    assert "Resolve-TfisAbsolutePathText -RepoRoot $repoRoot" in start_script
    assert "Resolve-TfisPositionStateDirectoryPath -RepoRoot $repoRoot" in start_script
    assert "Get-TfisResumablePaperPositionStatePaths" in start_script
    assert "Test-TfisTradingHolidayDate -RepoRoot $repoRoot -EffectiveDate $Date -CalendarPath $TradingHolidayCalendar" in start_script
    assert "Resolve-TfisPythonExecutable -RepoRoot $repoRoot" in start_script
    assert "New-TfisTaskLaunchContext" in start_script
    assert "Passing latest discovered open S21 paper position to supervised decision" in start_script
    assert "run_s21_banknifty_0916_supervised_decision_$stamp.out.log" in start_script
    assert "run_tfis_paper_lifecycle_supervisor.py" in launcher_script
    assert '[string]$TaskName = "TFIS S21 Morning Supervised Decision"' in register_script
    assert '[string]$IfPast = "run_now"' in register_script
    assert "start_s21_fyers_morning_supervised_decision.ps1" in register_script
    assert 'if ((@($StrategyPath) -join "|") -ne (@($defaultStrategyPath) -join "|")) {' in register_script
    assert "Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop" in check_script
    assert '& $schtasksExe /Query /V /FO CSV 2>&1' in check_script


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


def test_dashboard_server_supports_skip_build_mode() -> None:
    script = _script_text("serve_operator_dashboard.py")

    assert '--skip-build' in script
    assert '--runtime-config' in script
    assert 'if args.skip_build:' in script
    assert 'ERROR: --skip-build was requested but the dashboard index does not exist yet.' in script
    assert 'prepare_live_decision_runtime_environment' in script


def test_shared_paper_position_helper_is_used_by_recovery_scripts() -> None:
    helper_script = _script_text("tfis_paper_position_state_helpers.ps1")
    supervisor_helper_script = _script_text("tfis_paper_lifecycle_supervisor_helpers.ps1")
    trading_calendar_helper_script = _script_text("tfis_trading_calendar_helpers.ps1")
    wrapper_task_helper_script = _script_text("tfis_wrapper_task_helpers.ps1")
    reset_script = _script_text("reset_tfis_dashboard_and_watchers.ps1")

    assert "function Test-TfisResumablePaperPositionStateJson" in helper_script
    assert "function Resolve-TfisAbsolutePathText" in helper_script
    assert "function Resolve-TfisPositionStateDirectoryPath" in helper_script
    assert "function Get-TfisResumablePaperPositionStatePaths" in helper_script
    assert '"PAPER_POSITION_OPEN"' in helper_script
    assert '"PAPER_POSITION_CARRIED_FORWARD"' in helper_script
    assert '"PAPER_POSITION_RESUMED"' in helper_script
    assert '. $paperPositionHelperPath' in reset_script
    assert "function Start-TfisPaperLifecycleSupervisorProcess" in supervisor_helper_script
    assert "function Resolve-TfisPaperLifecycleSupervisorLauncherPath" in supervisor_helper_script
    assert "function Get-TfisTradingHolidayEntry" in trading_calendar_helper_script
    assert "function Test-TfisTradingHolidayDate" in trading_calendar_helper_script
    assert "function Get-TfisEffectiveRunDate" in trading_calendar_helper_script
    assert "function Get-TfisNoRunReason" in trading_calendar_helper_script
    assert "function Resolve-TfisPythonExecutable" in wrapper_task_helper_script
    assert "function New-TfisTaskLaunchContext" in wrapper_task_helper_script
    assert "function Write-TfisTaskLogMessage" in wrapper_task_helper_script
    assert "function Show-TfisTaskBanner" in wrapper_task_helper_script
    assert "function Start-TfisHiddenPythonProcess" in wrapper_task_helper_script
    assert '. $supervisorHelperPath' in reset_script
    assert "Start-TfisPaperLifecycleSupervisorProcess" in reset_script


def test_s23_task_checkers_match_real_task_name_variable() -> None:
    for script_name in (
        "check_s23_fyers_morning_supervised_task.ps1",
        "check_s23_paper_order_finalizer_task.ps1",
    ):
        script = _script_text(script_name)
        assert "Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop" in script
        assert '$task | Format-List TaskName, TaskPath, State' in script
        assert '$schtasksExe = Join-Path $env:SystemRoot "System32\\schtasks.exe"' in script
        assert '& $schtasksExe /Query /V /FO CSV 2>&1' in script
        assert 'Get-ScheduledTask lookup failed: $taskLookupError' in script
        assert "\\$TaskName" not in script
