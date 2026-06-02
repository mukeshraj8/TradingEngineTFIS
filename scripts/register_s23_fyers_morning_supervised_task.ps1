param(
    [string]$TaskName = "TFIS S23 Morning Supervised Decision",
    [string]$RunTime = "09:14",
    [string]$TradingEngineRoot = "D:\TradingEngineProd",
    [string]$Config = "config/paper.s23.fyers_connect_test.yaml",
    [string]$StrategyPath = "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
    [string]$ReferencePacket = "config/reference_packets/s23_bear_put_live_decision_reference.json",
    [string]$ArtifactRoot = "tmp/s23_fyers_morning_supervised_decision",
    [string]$SessionIdPrefix = "s23-fyers-morning-supervised-decision",
    [string]$Timezone = "Asia/Kolkata",
    [ValidateSet("run_now", "abort")]
    [string]$IfPast = "run_now",
    [switch]$SkipRefresh,
    [switch]$EnableSmokeOverride,
    [string]$CarryForwardStateDir
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$wrapperPath = Join-Path $repoRoot "scripts\start_s23_fyers_morning_supervised_decision.ps1"

if (-not (Test-Path $wrapperPath)) {
    throw "Missing wrapper script: $wrapperPath"
}

$defaultTradingEngineRoot = "D:\TradingEngineProd"
$defaultConfig = "config/paper.s23.fyers_connect_test.yaml"
$defaultStrategyPath = "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
$defaultReferencePacket = "config/reference_packets/s23_bear_put_live_decision_reference.json"
$defaultArtifactRoot = "tmp/s23_fyers_morning_supervised_decision"
$defaultSessionIdPrefix = "s23-fyers-morning-supervised-decision"
$defaultTimezone = "Asia/Kolkata"
$defaultIfPast = "run_now"

$actionParts = @(
    "powershell.exe",
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", ('"{0}"' -f $wrapperPath)
)

if ($TradingEngineRoot -ne $defaultTradingEngineRoot) {
    $actionParts += "-TradingEngineRoot"
    $actionParts += ('"{0}"' -f $TradingEngineRoot)
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

$taskAction = $actionParts -join " "

$taskStartDate = (Get-Date).ToString("MM/dd/yyyy")
schtasks /Create /F /SC DAILY /ST $RunTime /SD $taskStartDate /TN $TaskName /TR $taskAction
if ($LASTEXITCODE -ne 0) {
    throw "schtasks failed with exit code $LASTEXITCODE"
}

Write-Host "Registered scheduled task: $TaskName"
Write-Host "Run time: $RunTime"
Write-Host "Action: $taskAction"
