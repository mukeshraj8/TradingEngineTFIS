param(
    [string]$TaskName = "TFIS S23 Morning Supervised Decision",
    [string]$RunTime = "09:08",
    [string]$TfisRoot,
    [string]$Config = "config/paper.s23.fyers_connect_test.yaml",
    [string]$StrategyPath = "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
    [string]$ReferencePacket = "config/reference_packets/s23_bear_put_live_decision_reference.json",
    [string]$ArtifactRoot = "data/strategies/S23/fyers_morning_supervised_decision",
    [string]$SessionIdPrefix = "s23-fyers-morning-supervised-decision",
    [string]$Timezone = "Asia/Kolkata",
    [ValidateSet("run_now", "abort")]
    [string]$IfPast = "abort",
    [switch]$SkipRefresh,
    [switch]$EnableSmokeOverride,
    [string]$CarryForwardStateDir,
    [string]$TradingHolidayCalendar = "config/nse_trading_holidays_2026.json"
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$wrapperPath = Join-Path $repoRoot "scripts\start_s23_fyers_morning_supervised_decision.ps1"
if (-not $TfisRoot) {
    $TfisRoot = $repoRoot
}

if (-not (Test-Path $wrapperPath)) {
    throw "Missing wrapper script: $wrapperPath"
}

$defaultTfisRoot = $repoRoot
$defaultConfig = "config/paper.s23.fyers_connect_test.yaml"
$defaultStrategyPath = "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
$defaultReferencePacket = "config/reference_packets/s23_bear_put_live_decision_reference.json"
$defaultArtifactRoot = "data/strategies/S23/fyers_morning_supervised_decision"
$defaultSessionIdPrefix = "s23-fyers-morning-supervised-decision"
$defaultTimezone = "Asia/Kolkata"
$defaultIfPast = "run_now"
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
if ($Config -ne $defaultConfig) {
    $actionParts += "-Config"
    $actionParts += ('"{0}"' -f $Config)
}
if ($StrategyPath -ne $defaultStrategyPath) {
    $actionParts += "-StrategyPath"
    $actionParts += ('"{0}"' -f $StrategyPath)
}
if ($ReferencePacket -ne $defaultReferencePacket) {
    $actionParts += "-ReferencePacket"
    $actionParts += ('"{0}"' -f $ReferencePacket)
}
if ($ArtifactRoot -ne $defaultArtifactRoot) {
    $actionParts += "-ArtifactRoot"
    $actionParts += ('"{0}"' -f $ArtifactRoot)
}
if ($SessionIdPrefix -ne $defaultSessionIdPrefix) {
    $actionParts += "-SessionIdPrefix"
    $actionParts += ('"{0}"' -f $SessionIdPrefix)
}
if ($Timezone -ne $defaultTimezone) {
    $actionParts += "-Timezone"
    $actionParts += ('"{0}"' -f $Timezone)
}
if ($IfPast -ne $defaultIfPast) {
    $actionParts += "-IfPast"
    $actionParts += ('"{0}"' -f $IfPast)
}

if ($SkipRefresh) {
    $actionParts += "-SkipRefresh"
}
if ($EnableSmokeOverride) {
    $actionParts += "-EnableSmokeOverride"
}
if ($CarryForwardStateDir) {
    $actionParts += "-CarryForwardStateDir"
    $actionParts += ('"{0}"' -f $CarryForwardStateDir)
}
if ($TradingHolidayCalendar -ne $defaultTradingHolidayCalendar) {
    $actionParts += "-TradingHolidayCalendar"
    $actionParts += ('"{0}"' -f $TradingHolidayCalendar)
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
