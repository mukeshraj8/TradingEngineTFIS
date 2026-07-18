param(
    [string]$TfisRoot
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$runtimeProcessHelperPath = Join-Path $scriptDir "tfis_runtime_process_helpers.ps1"
. $runtimeProcessHelperPath

if (-not $TfisRoot) {
    $TfisRoot = $repoRoot
}

Set-Location $repoRoot
$Host.UI.RawUI.WindowTitle = "TFIS Runtime Stop"

Write-Host "============================================"
Write-Host "TFIS RUNTIME STOP"
Write-Host "This window belongs to TradingEngineTFIS only."
Write-Host "============================================"

$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
Stop-TfisRuntimeProcesses -RepoRoot $repoRoot -CurrentProcessId $PID
Write-Host ("Stopped TFIS runtime in {0:n1}s" -f $stopwatch.Elapsed.TotalSeconds)
