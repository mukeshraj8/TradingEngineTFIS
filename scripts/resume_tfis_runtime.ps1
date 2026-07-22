param(
    [string]$TfisRoot,
    [string]$StrategyCode
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$operatorControlHelperPath = Join-Path $scriptDir "tfis_operator_control_helpers.ps1"
. $operatorControlHelperPath

if (-not $TfisRoot) {
    $TfisRoot = $repoRoot
}

Set-Location $repoRoot
$Host.UI.RawUI.WindowTitle = "TFIS Runtime Resume"

Write-Host "============================================"
Write-Host "TFIS RUNTIME RESUME"
Write-Host "This window belongs to TradingEngineTFIS only."
Write-Host "============================================"

$markerPath = Clear-TfisOperatorPauseMarker -RepoRoot $repoRoot -StrategyCode $StrategyCode
if ([string]::IsNullOrWhiteSpace($StrategyCode)) {
    Write-Host "Cleared global TFIS runtime pause."
}
else {
    Write-Host "Cleared TFIS runtime pause for strategy $($StrategyCode.Trim().ToUpperInvariant())."
}
Write-Host "Marker: $markerPath"
