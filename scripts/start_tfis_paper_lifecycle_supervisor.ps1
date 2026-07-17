param(
    [string]$TfisRoot,
    [string]$TargetsConfig = "config/paper_lifecycle_supervisor_targets.yaml",
    [string]$DashboardOutputRoot = "tmp/operator_dashboard",
    [int]$DashboardPort = 8765,
    [datetime]$SessionDate,
    [double]$PollSeconds = 5.0,
    [string]$Until = "15:30",
    [switch]$DisableDashboardRebuild,
    [switch]$SkipRefresh
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot
if (-not $TfisRoot) {
    $TfisRoot = $repoRoot
}

$Host.UI.RawUI.WindowTitle = "TFIS Paper Lifecycle Supervisor Launcher"

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

$logDir = Join-Path $repoRoot "tmp\tfis_paper_lifecycle_supervisor\_launch_logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

function Quote-TfisPowerShellLiteral {
    param([string]$Value)
    return "'" + ($Value -replace "'", "''") + "'"
}

$effectiveSessionDate = if ($SessionDate) { $SessionDate.ToString("yyyy-MM-dd") } else { (Get-Date).ToString("yyyy-MM-dd") }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stdoutPath = Join-Path $logDir "tfis_paper_lifecycle_supervisor_${stamp}.out.log"
$stderrPath = Join-Path $logDir "tfis_paper_lifecycle_supervisor_${stamp}.err.log"
$launchScriptPath = Join-Path $logDir "tfis_paper_lifecycle_supervisor_${stamp}.ps1"
$watchScript = Join-Path $repoRoot "scripts\run_tfis_paper_lifecycle_supervisor.py"

$watchArgsLiteral = @(
    Quote-TfisPowerShellLiteral $watchScript
    "'--tfis-root'"
    Quote-TfisPowerShellLiteral $TfisRoot
    "'--targets-config'"
    Quote-TfisPowerShellLiteral $TargetsConfig
    "'--dashboard-output-root'"
    Quote-TfisPowerShellLiteral $DashboardOutputRoot
    "'--session-date'"
    Quote-TfisPowerShellLiteral $effectiveSessionDate
    "'--poll-seconds'"
    Quote-TfisPowerShellLiteral ([string]$PollSeconds)
    "'--until'"
    Quote-TfisPowerShellLiteral $Until
    "'--no-targets-ok'"
)
if ($SkipRefresh) {
    $watchArgsLiteral += "'--skip-refresh'"
}
if ($DisableDashboardRebuild) {
    $watchArgsLiteral += "'--disable-dashboard-rebuild'"
}
$watchArgsText = $watchArgsLiteral -join ", "

$launchScript = @"
`$ErrorActionPreference = 'Continue'
`$Host.UI.RawUI.WindowTitle = 'TFIS Paper Lifecycle Supervisor'
Write-Host '============================================================'
Write-Host 'TFIS PAPER LIFECYCLE SUPERVISOR'
Write-Host 'This window belongs to TradingEngineTFIS only.'
Write-Host 'Targets config   : $TargetsConfig'
Write-Host 'Dashboard output : $DashboardOutputRoot'
Write-Host 'Session date     : $effectiveSessionDate'
Write-Host 'Poll seconds     : $PollSeconds'
Write-Host 'Cutoff           : $Until'
Write-Host 'Stdout           : $stdoutPath'
Write-Host 'Stderr           : $stderrPath'
Write-Host '============================================================'
Set-Location $(Quote-TfisPowerShellLiteral $repoRoot)
`$watchArgs = @($watchArgsText)
& $(Quote-TfisPowerShellLiteral $pythonExe) @watchArgs 2> $(Quote-TfisPowerShellLiteral $stderrPath) | Tee-Object -FilePath $(Quote-TfisPowerShellLiteral $stdoutPath) -Append
`$tfisSupervisorExitCode = `$LASTEXITCODE
Write-Host '============================================================'
Write-Host "TFIS paper lifecycle supervisor exited with code `$tfisSupervisorExitCode."
Write-Host 'This window is held open for review; it is safe to close when done.'
Write-Host '============================================================'
Read-Host 'Press Enter to close this TFIS supervisor window'
"@
Set-Content -Path $launchScriptPath -Value $launchScript -Encoding UTF8

$process = Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList @("-ExecutionPolicy", "Bypass", "-File", $launchScriptPath) `
    -WorkingDirectory $repoRoot `
    -WindowStyle Normal `
    -PassThru

Write-Host "Started TFIS paper lifecycle supervisor PID=$($process.Id) date=$effectiveSessionDate targets=$TargetsConfig"
Write-Host "URL: http://127.0.0.1:$DashboardPort/index.html"
Write-Host "Launcher: $launchScriptPath"
