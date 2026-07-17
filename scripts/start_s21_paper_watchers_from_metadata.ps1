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
$supervisorHelperPath = Join-Path $scriptDir "tfis_paper_lifecycle_supervisor_helpers.ps1"
. $supervisorHelperPath
Set-Location $repoRoot
if (-not $TfisRoot) {
    $TfisRoot = $repoRoot
}

$Host.UI.RawUI.WindowTitle = "TFIS S21 Supervisor Compatibility Launcher"

$effectiveSessionDate = if ($SessionDate) { $SessionDate.Date } else { (Get-Date).Date }
Write-Host "TFIS S21 supervisor compatibility launcher"
Write-Host "Session date : $($effectiveSessionDate.ToString('yyyy-MM-dd'))"
Write-Host "Mode         : shared TFIS paper lifecycle supervisor"
Write-Host "This compatibility launcher now starts one supervisor process for S21 and S23 together."

$process = Start-TfisPaperLifecycleSupervisorProcess `
    -RepoRoot $repoRoot `
    -TfisRoot $TfisRoot `
    -SessionDate $effectiveSessionDate `
    -DisableDashboardRebuild:$DisableDashboardRebuild

Write-Host "Started shared TFIS paper lifecycle supervisor PID=$($process.Id)"
