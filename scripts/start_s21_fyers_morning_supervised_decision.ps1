param(
    [datetime]$Date = (Get-Date),
    [string]$TfisRoot,
    [string]$Config = "config/paper.s21.fyers_connect_test.yaml",
    [string[]]$StrategyPath = @(
        "config/strategies/options_sell/banknifty/S21_BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL",
        "config/strategies/options_sell/banknifty/S21_BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT",
        "config/strategies/options_sell/banknifty/S21_BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL",
        "config/strategies/options_sell/banknifty/S21_BANKNIFTY_OP_SELL_MONTHLY_BEAR_PUT"
    ),
    [string]$ReferencePacket = "config/reference_packets/s21_banknifty_monthly_live_decision_reference.json",
    [string]$ArtifactRoot = "data/strategies/S21/fyers_morning_supervised_decision",
    [string]$SessionIdPrefix = "s21-fyers-morning-supervised-decision",
    [string]$Timezone = "Asia/Kolkata",
    [ValidateSet("run_now", "abort")]
    [string]$IfPast = "run_now",
    [switch]$SkipRefresh,
    [switch]$EnableSmokeOverride,
    [string]$CarryForwardStateDir,
    [string]$TradingHolidayCalendar = "config/nse_trading_holidays_2026.json"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot
$paperPositionHelperPath = Join-Path $scriptDir "tfis_paper_position_state_helpers.ps1"
$tradingCalendarHelperPath = Join-Path $scriptDir "tfis_trading_calendar_helpers.ps1"
$wrapperTaskHelperPath = Join-Path $scriptDir "tfis_wrapper_task_helpers.ps1"
. $paperPositionHelperPath
. $tradingCalendarHelperPath
. $wrapperTaskHelperPath
if (-not $TfisRoot) {
    $TfisRoot = $repoRoot
}

$Host.UI.RawUI.WindowTitle = "TFIS S21 Morning Supervised Decision"

$pythonExe = Resolve-TfisPythonExecutable -RepoRoot $repoRoot

$taskContext = New-TfisTaskLaunchContext `
    -RepoRoot $repoRoot `
    -RelativeLogDirectory "tmp\s21_fyers_morning_supervised_decision\_task_launch_logs" `
    -LogFilePrefix "start_s21_fyers_morning_supervised_decision"
$logDir = $taskContext.LogDirectory
$stamp = $taskContext.Stamp
$pythonOutputPath = Join-Path $logDir "run_s21_banknifty_0916_supervised_decision_$stamp.out.log"
$pythonErrorPath = Join-Path $logDir "run_s21_banknifty_0916_supervised_decision_$stamp.err.log"
$launchLogPath = $taskContext.LogPath

function Write-LaunchLog {
    param([string]$Message)
    Write-TfisTaskLogMessage `
        -LogPath $launchLogPath `
        -Message $Message `
        -TimestampFormat "yyyy-MM-ddTHH:mm:sszzz"
}

function Invoke-S21SupervisedDecisionProcess {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$ArgumentList,
        [Parameter(Mandatory = $true)]
        [string]$StdoutPath,
        [Parameter(Mandatory = $true)]
        [string]$StderrPath
    )

    $process = Start-TfisHiddenPythonProcess `
        -PythonExecutable $pythonExe `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $repoRoot `
        -StdoutPath $StdoutPath `
        -StderrPath $StderrPath

    $stdoutLines = @()
    $stderrLines = @()
    if (Test-Path $StdoutPath) {
        $stdoutLines = @(Get-Content -Path $StdoutPath)
    }
    if (Test-Path $StderrPath) {
        $stderrLines = @(Get-Content -Path $StderrPath)
    }

    return [pscustomobject]@{
        ExitCode = $process.ExitCode
        StdoutLines = $stdoutLines
        StderrLines = $stderrLines
    }
}

$effectiveRunDate = Get-TfisEffectiveRunDate -RunDate $Date
$noRunReason = Get-TfisNoRunReason -RepoRoot $repoRoot -EffectiveDate $effectiveRunDate -CalendarPath $TradingHolidayCalendar
if ($noRunReason) {
    Show-TfisTaskBanner `
        -Title "TFIS S21 MORNING SUPERVISED DECISION" `
        -RepoRoot $repoRoot `
        -LogPath $launchLogPath
    Write-LaunchLog "Starting TFIS S21 morning supervised decision wrapper."
    Write-LaunchLog $noRunReason
    Write-LaunchLog "Skipping TFIS S21 morning decision."
    Write-LaunchLog "Wrapper finished with exit code 0."
    exit 0
}

$carryForwardStateDirArg = Resolve-TfisPositionStateDirectoryPath -RepoRoot $repoRoot -PathText $CarryForwardStateDir
if (-not $carryForwardStateDirArg) {
    $discoveredCarryForwardStatePaths = @(
        Get-TfisResumablePaperPositionStatePaths `
            -ArtifactRoot (Resolve-TfisAbsolutePathText -RepoRoot $repoRoot -PathText $ArtifactRoot) `
            -EffectiveDate $effectiveRunDate
    )
    if ($discoveredCarryForwardStatePaths.Count -gt 0) {
        $discoveredCarryForwardStatePath = Resolve-TfisAbsolutePathText -RepoRoot $repoRoot -PathText ([string]$discoveredCarryForwardStatePaths[0])
        $carryForwardStateDirArg = Resolve-TfisPositionStateDirectoryPath -RepoRoot $repoRoot -PathText $discoveredCarryForwardStatePath
        Write-LaunchLog "Passing latest discovered open S21 paper position to supervised decision: $discoveredCarryForwardStatePath"
    }
}
elseif ($carryForwardStateDirArg) {
    Write-LaunchLog "Carry-forward state directory argument: $carryForwardStateDirArg"
}

$resolvedArtifactRoot = Resolve-TfisAbsolutePathText -RepoRoot $repoRoot -PathText $ArtifactRoot

$args = @(
    (Resolve-TfisAbsolutePathText -RepoRoot $repoRoot -PathText "scripts/run_s21_banknifty_0916_supervised_decision.py"),
    "--tfis-root", $TfisRoot,
    "--config", (Resolve-TfisAbsolutePathText -RepoRoot $repoRoot -PathText $Config),
    "--reference-packet", (Resolve-TfisAbsolutePathText -RepoRoot $repoRoot -PathText $ReferencePacket),
    "--artifact-root", $resolvedArtifactRoot,
    "--session-id-prefix", $SessionIdPrefix,
    "--timezone", $Timezone,
    "--if-past", $IfPast
)

foreach ($strategy in $StrategyPath) {
    $args += "--strategy-path"
    $args += (Resolve-TfisAbsolutePathText -RepoRoot $repoRoot -PathText $strategy)
}

if ($SkipRefresh) {
    $args += "--skip-refresh"
}
if ($EnableSmokeOverride) {
    $args += "--enable-smoke-override"
}
if ($carryForwardStateDirArg) {
    $args += "--carry-forward-state-dir"
    $args += $carryForwardStateDirArg
}

Show-TfisTaskBanner `
    -Title "TFIS S21 MORNING SUPERVISED DECISION" `
    -RepoRoot $repoRoot `
    -LogPath $launchLogPath
Write-LaunchLog "Starting TFIS S21 morning supervised decision wrapper."
Write-LaunchLog "Python executable: $pythonExe"
Write-LaunchLog "TfisRoot: $TfisRoot"
Write-LaunchLog "ArtifactRoot: $ArtifactRoot"
Write-LaunchLog "SessionIdPrefix: $SessionIdPrefix"
Write-LaunchLog "Supervised decision stdout: $pythonOutputPath"
Write-LaunchLog "Supervised decision stderr: $pythonErrorPath"
Write-LaunchLog "Starting S21 supervised decision Python process."
Write-LaunchLog "Effective run date: $($effectiveRunDate.ToString('yyyy-MM-dd'))"

try {
    $result = Invoke-S21SupervisedDecisionProcess `
        -ArgumentList $args `
        -StdoutPath $pythonOutputPath `
        -StderrPath $pythonErrorPath
    $exitCode = $result.ExitCode
    $stdoutLines = $result.StdoutLines
    $stderrLines = $result.StderrLines
    $stdoutLines | ForEach-Object {
        Write-LaunchLog ("PYTHON: {0}" -f $_)
    }
    $stderrLines | ForEach-Object {
        Write-LaunchLog ("PYTHON_ERR: {0}" -f $_)
    }

    $tokenRaceDetected = (
        (-not $SkipRefresh) -and
        ($exitCode -ne 0) -and
        ($stderrLines -match "invalid auth code").Count -gt 0
    )
    if ($tokenRaceDetected) {
        Write-LaunchLog "Detected FYERS auth-code race during S21 refresh; retrying once with --skip-refresh."
        $retryStamp = "{0}_retry_skip_refresh" -f $stamp
        $retryOutputPath = Join-Path $logDir "run_s21_banknifty_0916_supervised_decision_$retryStamp.out.log"
        $retryErrorPath = Join-Path $logDir "run_s21_banknifty_0916_supervised_decision_$retryStamp.err.log"
        $retryArgs = @($args + "--skip-refresh")
        $retryResult = Invoke-S21SupervisedDecisionProcess `
            -ArgumentList $retryArgs `
            -StdoutPath $retryOutputPath `
            -StderrPath $retryErrorPath
        $exitCode = $retryResult.ExitCode
        $stdoutLines = $retryResult.StdoutLines
        $stderrLines = $retryResult.StderrLines
        $stdoutLines | ForEach-Object {
            Write-LaunchLog ("PYTHON_RETRY: {0}" -f $_)
        }
        $stderrLines | ForEach-Object {
            Write-LaunchLog ("PYTHON_RETRY_ERR: {0}" -f $_)
        }
        $pythonOutputPath = $retryOutputPath
        $pythonErrorPath = $retryErrorPath
    }

    Write-LaunchLog "Morning supervised decision finished with exit code $exitCode."

    if ($exitCode -ne 0) {
        $stderrLines | ForEach-Object { Write-Host $_ }
        Write-LaunchLog "Wrapper finished with exit code $exitCode."
        exit $exitCode
    }

    $stdoutLines | ForEach-Object { Write-Host $_ }

    Write-LaunchLog "Wrapper finished with exit code 0."
    exit 0
}
catch {
    Write-LaunchLog ("Wrapper failed: {0}" -f $_.Exception.Message)
    throw
}
