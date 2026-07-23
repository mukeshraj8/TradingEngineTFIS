param(
    [string]$TfisRoot,
    [string]$ArtifactRoot = "data/strategies/S23/fyers_morning_supervised_decision",
    [string]$TargetsConfig = "config/paper_lifecycle_supervisor_targets.yaml",
    [string]$DashboardOutputRoot = "tmp/operator_dashboard",
    [string]$Timezone = "Asia/Kolkata",
    [string]$Cutoff = "15:30",
    [string]$TradingHolidayCalendar = "config/nse_trading_holidays_2026.json",
    [datetime]$RunDate,
    [switch]$CurrentSessionOnly,
    [switch]$AllowBeforeCutoff,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot
$tradingCalendarHelperPath = Join-Path $scriptDir "tfis_trading_calendar_helpers.ps1"
$wrapperTaskHelperPath = Join-Path $scriptDir "tfis_wrapper_task_helpers.ps1"
. $tradingCalendarHelperPath
. $wrapperTaskHelperPath
$Host.UI.RawUI.WindowTitle = "TFIS Paper Order Finalizer"
if (-not $TfisRoot) {
    $TfisRoot = $repoRoot
}

$taskContext = New-TfisTaskLaunchContext `
    -RepoRoot $repoRoot `
    -RelativeLogDirectory "tmp\s23_fyers_morning_supervised_decision\_task_launch_logs" `
    -LogFilePrefix "tfis_paper_order_finalizer"
$logDir = $taskContext.LogDirectory
$stamp = $taskContext.Stamp
$logPath = $taskContext.LogPath

function Write-FinalizerLog {
    param([string]$Message)
    Write-TfisTaskLogMessage -LogPath $logPath -Message $Message -ConsolePrefix "[TFIS Finalizer] "
}

$pythonExe = Resolve-TfisPythonExecutable -RepoRoot $repoRoot -AllowSystemPythonFallback

Show-TfisTaskBanner `
    -Title "TFIS PAPER ORDER FINALIZER" `
    -RepoRoot $repoRoot `
    -LogPath $logPath
Write-FinalizerLog "Starting TFIS paper order finalizer."
Write-FinalizerLog "Python executable: $pythonExe"
Write-FinalizerLog "ArtifactRoot: $ArtifactRoot"
Write-FinalizerLog "TargetsConfig: $TargetsConfig"
Write-FinalizerLog "DashboardOutputRoot: $DashboardOutputRoot"
Write-FinalizerLog "Cutoff: $Cutoff"

if ($PSBoundParameters.ContainsKey("RunDate")) {
    $effectiveRunDate = Get-TfisEffectiveRunDate -RunDate $RunDate
}
else {
    $effectiveRunDate = Get-TfisEffectiveRunDate
}
$noRunReason = Get-TfisNoRunReason -RepoRoot $repoRoot -EffectiveDate $effectiveRunDate -CalendarPath $TradingHolidayCalendar
if ($noRunReason) {
    Write-FinalizerLog $noRunReason
    Write-FinalizerLog "Skipping TFIS paper order finalization."
    Write-FinalizerLog "Finalizer finished with exit code 0."
    exit 0
}

$args = @(
    (Join-Path $repoRoot "scripts\finalize_s23_pending_paper_orders.py"),
    "--targets-config", $TargetsConfig,
    "--artifact-root", $ArtifactRoot,
    "--dashboard-output-root", $DashboardOutputRoot,
    "--timezone", $Timezone,
    "--cutoff", $Cutoff,
    "--session-date", $effectiveRunDate.ToString("yyyy-MM-dd"),
    "--rebuild-dashboard"
)

if (-not $CurrentSessionOnly) {
    $args += "--include-prior-sessions"
}
if ($AllowBeforeCutoff) {
    $args += "--allow-before-cutoff"
}
if ($DryRun) {
    $args += "--dry-run"
}

try {
    & $pythonExe @args 2>&1 | ForEach-Object {
        Write-FinalizerLog ("PYTHON: {0}" -f $_)
        Write-Output $_
    }
    $exitCode = $LASTEXITCODE
    Write-FinalizerLog "Finalizer finished with exit code $exitCode."
    exit $exitCode
}
catch {
    Write-FinalizerLog ("Finalizer failed: {0}" -f $_.Exception.Message)
    throw
}
