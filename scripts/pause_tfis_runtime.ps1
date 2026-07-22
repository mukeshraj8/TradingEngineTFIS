param(
    [string]$TfisRoot,
    [string]$StrategyCode,
    [string]$Reason = "manual_operator_pause"
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
$Host.UI.RawUI.WindowTitle = "TFIS Runtime Pause"

Write-Host "============================================"
Write-Host "TFIS RUNTIME PAUSE"
Write-Host "This window belongs to TradingEngineTFIS only."
Write-Host "============================================"

$markerPath = Set-TfisOperatorPauseMarker -RepoRoot $repoRoot -StrategyCode $StrategyCode -Reason $Reason
if ([string]::IsNullOrWhiteSpace($StrategyCode)) {
    Write-Host "Applied global TFIS runtime pause."
}
else {
    Write-Host "Applied TFIS runtime pause for strategy $($StrategyCode.Trim().ToUpperInvariant())."
}
Write-Host "Marker: $markerPath"
