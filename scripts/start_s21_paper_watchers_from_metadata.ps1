param(
    [string]$TfisRoot,
    [string]$Config = "config/paper.s21.fyers_connect_test.yaml",
    [string]$ArtifactRoot = "data/strategies/S21/fyers_morning_supervised_decision",
    [string]$Timezone = "Asia/Kolkata",
    [datetime]$SessionDate,
    [switch]$DisableDashboardRebuild
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot
if (-not $TfisRoot) {
    $TfisRoot = $repoRoot
}

$Host.UI.RawUI.WindowTitle = "TFIS S21 Watcher Launcher"

$effectiveSessionDate = if ($SessionDate) { $SessionDate.Date } else { (Get-Date).Date }
$launcherPath = Join-Path $repoRoot "scripts\start_tfis_paper_lifecycle_supervisor.ps1"
if (-not (Test-Path $launcherPath)) {
    throw "Missing TFIS lifecycle supervisor launcher: $launcherPath"
}

Write-Host "TFIS S21 watcher launcher"
Write-Host "Session date : $($effectiveSessionDate.ToString('yyyy-MM-dd'))"
Write-Host "Mode         : shared TFIS paper lifecycle supervisor"
Write-Host "This launcher now starts one supervisor process for S21 and S23 together."

$args = @(
    "-ExecutionPolicy", "Bypass",
    "-File", $launcherPath,
    "-TfisRoot", $TfisRoot,
    "-SessionDate", $effectiveSessionDate.ToString("yyyy-MM-dd")
)
if ($DisableDashboardRebuild) {
    $args += "-DisableDashboardRebuild"
}

$process = Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList $args `
    -WorkingDirectory $repoRoot `
    -WindowStyle Normal `
    -PassThru

Write-Host "Started shared TFIS paper lifecycle supervisor PID=$($process.Id)"
