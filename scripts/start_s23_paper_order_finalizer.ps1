param(
    [string]$TfisRoot,
    [string]$ArtifactRoot = "tmp/s23_fyers_morning_supervised_decision",
    [string]$DashboardOutputRoot = "tmp/operator_dashboard",
    [string]$Timezone = "Asia/Kolkata",
    [string]$Cutoff = "15:30",
    [string]$TradingHolidayCalendar = "config/nse_trading_holidays_2026.json",
    [datetime]$RunDate,
    [switch]$IncludePriorSessions,
    [switch]$AllowBeforeCutoff,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot
$Host.UI.RawUI.WindowTitle = "TFIS S23 Paper Order Finalizer"
if (-not $TfisRoot) {
    $TfisRoot = $repoRoot
}

$logDir = Join-Path $repoRoot "tmp\s23_fyers_morning_supervised_decision\_task_launch_logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$stamp = "{0}_{1}" -f (Get-Date -Format "yyyyMMdd_HHmmssfff"), $PID
$logPath = Join-Path $logDir "s23_paper_order_finalizer_$stamp.log"

function Write-FinalizerLog {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"), $Message
    Add-Content -Path $logPath -Value $line
    Write-Host "[TFIS S23 Finalizer] $Message"
}

function Get-TfisRunDate {
    if ($RunDate) {
        return $RunDate.Date
    }
    return (Get-Date).Date
}

function Get-TfisTradingHoliday {
    param([datetime]$Date)

    $calendarPath = $TradingHolidayCalendar
    if (-not [System.IO.Path]::IsPathRooted($calendarPath)) {
        $calendarPath = Join-Path $repoRoot $calendarPath
    }
    if (-not (Test-Path $calendarPath)) {
        return $null
    }
    $calendar = Get-Content -Path $calendarPath -Raw | ConvertFrom-Json
    $dateText = $Date.ToString("yyyy-MM-dd")
    foreach ($holiday in $calendar.holidays) {
        if ([string]$holiday.date -eq $dateText) {
            return $holiday
        }
    }
    return $null
}

function Get-TfisNoRunReason {
    param([datetime]$Date)

    if ($Date.DayOfWeek -eq [System.DayOfWeek]::Saturday -or $Date.DayOfWeek -eq [System.DayOfWeek]::Sunday) {
        return "WEEKEND_NO_ACTION: $($Date.ToString('yyyy-MM-dd')) is $($Date.DayOfWeek); NSE equity/F&O market is closed."
    }
    $holiday = Get-TfisTradingHoliday -Date $Date
    if ($holiday) {
        return "NSE_HOLIDAY_NO_ACTION: $($Date.ToString('yyyy-MM-dd')) is configured as NSE holiday '$($holiday.name)'."
    }
    return $null
}

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

Write-Host "============================================================"
Write-Host "TFIS S23 PAPER ORDER FINALIZER"
Write-Host "This window belongs to TradingEngineTFIS only."
Write-Host "Repo: $repoRoot"
Write-Host "Log : $logPath"
Write-Host "============================================================"
Write-FinalizerLog "Starting TFIS S23 paper order finalizer."
Write-FinalizerLog "Python executable: $pythonExe"
Write-FinalizerLog "ArtifactRoot: $ArtifactRoot"
Write-FinalizerLog "DashboardOutputRoot: $DashboardOutputRoot"
Write-FinalizerLog "Cutoff: $Cutoff"

$effectiveRunDate = Get-TfisRunDate
$noRunReason = Get-TfisNoRunReason -Date $effectiveRunDate
if ($noRunReason) {
    Write-FinalizerLog $noRunReason
    Write-FinalizerLog "Skipping TFIS S23 paper order finalization."
    Write-FinalizerLog "Finalizer finished with exit code 0."
    exit 0
}

$args = @(
    (Join-Path $repoRoot "scripts\finalize_s23_pending_paper_orders.py"),
    "--artifact-root", $ArtifactRoot,
    "--dashboard-output-root", $DashboardOutputRoot,
    "--timezone", $Timezone,
    "--cutoff", $Cutoff,
    "--session-date", $effectiveRunDate.ToString("yyyy-MM-dd"),
    "--rebuild-dashboard"
)

if ($IncludePriorSessions) {
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
