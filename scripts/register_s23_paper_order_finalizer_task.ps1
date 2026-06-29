param(
    [string]$TaskName = "TFIS S23 Paper Order Finalizer",
    [string]$RunTime = "15:35",
    [string]$TfisRoot,
    [string]$ArtifactRoot = "tmp/s23_fyers_morning_supervised_decision",
    [string]$DashboardOutputRoot = "tmp/operator_dashboard",
    [string]$Timezone = "Asia/Kolkata",
    [string]$Cutoff = "15:30",
    [string]$TradingHolidayCalendar = "config/nse_trading_holidays_2026.json",
    [switch]$IncludePriorSessions
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$wrapperPath = Join-Path $repoRoot "scripts\start_s23_paper_order_finalizer.ps1"
if (-not $TfisRoot) {
    $TfisRoot = $repoRoot
}

if (-not (Test-Path $wrapperPath)) {
    throw "Missing wrapper script: $wrapperPath"
}

$defaultTfisRoot = $repoRoot
$defaultArtifactRoot = "tmp/s23_fyers_morning_supervised_decision"
$defaultDashboardOutputRoot = "tmp/operator_dashboard"
$defaultTimezone = "Asia/Kolkata"
$defaultCutoff = "15:30"
$defaultTradingHolidayCalendar = "config/nse_trading_holidays_2026.json"

$actionParts = @(
    "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe",
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", ('"{0}"' -f $wrapperPath)
)

if ($TfisRoot -ne $defaultTfisRoot) {
    $actionParts += "-TfisRoot"
    $actionParts += ('"{0}"' -f $TfisRoot)
}
if ($ArtifactRoot -ne $defaultArtifactRoot) {
    $actionParts += "-ArtifactRoot"
    $actionParts += ('"{0}"' -f $ArtifactRoot)
}
if ($DashboardOutputRoot -ne $defaultDashboardOutputRoot) {
    $actionParts += "-DashboardOutputRoot"
    $actionParts += ('"{0}"' -f $DashboardOutputRoot)
}
if ($Timezone -ne $defaultTimezone) {
    $actionParts += "-Timezone"
    $actionParts += ('"{0}"' -f $Timezone)
}
if ($Cutoff -ne $defaultCutoff) {
    $actionParts += "-Cutoff"
    $actionParts += ('"{0}"' -f $Cutoff)
}
if ($TradingHolidayCalendar -ne $defaultTradingHolidayCalendar) {
    $actionParts += "-TradingHolidayCalendar"
    $actionParts += ('"{0}"' -f $TradingHolidayCalendar)
}
if ($IncludePriorSessions) {
    $actionParts += "-IncludePriorSessions"
}

$taskAction = $actionParts -join " "

schtasks /Create /F /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST $RunTime /TN $TaskName /TR $taskAction
if ($LASTEXITCODE -ne 0) {
    throw "schtasks failed with exit code $LASTEXITCODE"
}

Write-Host "Registered scheduled task: $TaskName"
Write-Host "Run time: $RunTime"
Write-Host "Schedule: Weekly on MON,TUE,WED,THU,FRI"
Write-Host "Holiday calendar: $TradingHolidayCalendar"
Write-Host "Action: $taskAction"
