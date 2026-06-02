param(
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
Set-Location $repoRoot

Remove-Item Env:HTTP_PROXY,Env:HTTPS_PROXY,Env:http_proxy,Env:https_proxy,Env:ALL_PROXY,Env:all_proxy -ErrorAction SilentlyContinue

$logDir = Join-Path $repoRoot "tmp\s23_fyers_morning_supervised_decision\_task_launch_logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logDir "start_s23_fyers_morning_supervised_decision_$stamp.log"

function Write-LaunchLog {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"), $Message
    Add-Content -Path $logPath -Value $line
}

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

$args = @(
    (Join-Path $repoRoot "scripts\run_s23_fyers_0916_supervised_decision.py"),
    "--tradingengine-root", $TradingEngineRoot,
    "--config", $Config,
    "--strategy-path", $StrategyPath,
    "--reference-packet", $ReferencePacket,
    "--artifact-root", $ArtifactRoot,
    "--session-id-prefix", $SessionIdPrefix,
    "--timezone", $Timezone,
    "--if-past", $IfPast
)

if ($SkipRefresh) {
    $args += "--skip-refresh"
}
if ($EnableSmokeOverride) {
    $args += "--enable-smoke-override"
}
if ($CarryForwardStateDir) {
    $args += "--carry-forward-state-dir"
    $args += $CarryForwardStateDir
}

Write-LaunchLog "Starting TFIS S23 morning supervised decision wrapper."
Write-LaunchLog "Python executable: $pythonExe"
Write-LaunchLog "ArtifactRoot: $ArtifactRoot"
Write-LaunchLog "SessionIdPrefix: $SessionIdPrefix"

& $pythonExe @args
$exitCode = $LASTEXITCODE
Write-LaunchLog "Wrapper finished with exit code $exitCode."
exit $exitCode
