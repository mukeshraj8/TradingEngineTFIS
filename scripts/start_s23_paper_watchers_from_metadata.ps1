param(
    [string]$TfisRoot,
    [string]$Config = "config/paper.s23.fyers_connect_test.yaml",
    [string]$ArtifactRoot = "data/strategies/S23/fyers_morning_supervised_decision",
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

$Host.UI.RawUI.WindowTitle = "TFIS S23 Watcher Launcher"

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

$artifactRootPath = $ArtifactRoot
if (-not [System.IO.Path]::IsPathRooted($artifactRootPath)) {
    $artifactRootPath = Join-Path $repoRoot $artifactRootPath
}

$effectiveSessionDate = if ($SessionDate) { $SessionDate.Date } else { (Get-Date).Date }
$dayRoot = Join-Path $artifactRootPath $effectiveSessionDate.ToString("yyyy-MM-dd")
$logDir = Join-Path $repoRoot "tmp\s23_fyers_morning_supervised_decision\_task_launch_logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

function Quote-TfisPowerShellLiteral {
    param([string]$Value)
    return "'" + ($Value -replace "'", "''") + "'"
}

function Start-TfisS23Watcher {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("order", "state")]
        [string]$Mode,
        [Parameter(Mandatory = $true)]
        [string]$Directory
    )

    $watchScript = Join-Path $repoRoot "scripts\run_s23_paper_position_watch.py"
    $safeLabel = ((Split-Path -Leaf $Directory) -replace '[\\/:*?"<>|\s]+', '_').Trim('_')
    if ($safeLabel.Length -gt 96) {
        $safeLabel = $safeLabel.Substring($safeLabel.Length - 96)
    }
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $stdoutPath = Join-Path $logDir "s23_paper_watch_${Mode}_${safeLabel}_${stamp}.out.log"
    $stderrPath = Join-Path $logDir "s23_paper_watch_${Mode}_${safeLabel}_${stamp}.err.log"
    $launchScriptPath = Join-Path $logDir "s23_paper_watch_${Mode}_${safeLabel}_${stamp}.ps1"

    $modeArg = if ($Mode -eq "state") { "--state-dir" } else { "--order-dir" }
    $watchArgsLiteral = @(
        Quote-TfisPowerShellLiteral $watchScript
        "'--tfis-root'"
        Quote-TfisPowerShellLiteral $TfisRoot
        "'--config'"
        Quote-TfisPowerShellLiteral $Config
        "'--skip-refresh'"
        "'--timezone'"
        Quote-TfisPowerShellLiteral $Timezone
        Quote-TfisPowerShellLiteral $modeArg
        Quote-TfisPowerShellLiteral $Directory
    )
    if ($DisableDashboardRebuild) {
        $watchArgsLiteral += "'--disable-dashboard-rebuild'"
    }
    $watchArgsText = $watchArgsLiteral -join ", "
    $launchScript = @"
`$ErrorActionPreference = 'Continue'
`$Host.UI.RawUI.WindowTitle = 'TFIS S23 Paper Watch - $Mode'
Write-Host '============================================================'
Write-Host 'TFIS S23 PAPER WATCHER'
Write-Host 'Mode      : $Mode'
Write-Host 'Directory : $Directory'
Write-Host 'Repo      : $repoRoot'
Write-Host 'Stdout    : $stdoutPath'
Write-Host 'Stderr    : $stderrPath'
Write-Host '============================================================'
Set-Location $(Quote-TfisPowerShellLiteral $repoRoot)
`$watchArgs = @($watchArgsText)
& $(Quote-TfisPowerShellLiteral $pythonExe) @watchArgs 2> $(Quote-TfisPowerShellLiteral $stderrPath) | Tee-Object -FilePath $(Quote-TfisPowerShellLiteral $stdoutPath) -Append
`$tfisWatchExitCode = `$LASTEXITCODE
Write-Host '============================================================'
Write-Host "TFIS S23 paper watcher exited with code `$tfisWatchExitCode."
Write-Host 'This window is held open for review.'
Write-Host '============================================================'
Read-Host 'Press Enter to close this TFIS watcher window'
"@
    Set-Content -Path $launchScriptPath -Value $launchScript -Encoding UTF8

    $process = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @("-ExecutionPolicy", "Bypass", "-File", $launchScriptPath) `
        -WorkingDirectory $repoRoot `
        -WindowStyle Normal `
        -PassThru

    [pscustomobject]@{
        ProcessId = $process.Id
        Mode = $Mode
        Directory = $Directory
        Stdout = $stdoutPath
        Stderr = $stderrPath
        Launcher = $launchScriptPath
    }
}

if (-not (Test-Path $dayRoot)) {
    throw "No TFIS S23 artifact day directory found for $($effectiveSessionDate.ToString('yyyy-MM-dd')): $dayRoot"
}

$metadata = Get-ChildItem -Path $dayRoot -Recurse -Filter "scheduled_run_metadata.json" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $metadata) {
    throw "No scheduled_run_metadata.json found under $dayRoot"
}

$metadataJson = Get-Content -Path $metadata.FullName -Raw | ConvertFrom-Json
$watchTargets = @()
$stateDirectories = @{}
if ($metadataJson.branch_position_state_json) {
    $metadataJson.branch_position_state_json.PSObject.Properties | ForEach-Object {
        if ($_.Value) {
            $stateDir = Split-Path -Parent ([string]$_.Value)
            $stateDirectories[$stateDir] = $true
            $watchTargets += [pscustomobject]@{ Mode = "state"; Directory = $stateDir }
        }
    }
}
if ($metadataJson.branch_order_state_json) {
    $metadataJson.branch_order_state_json.PSObject.Properties | ForEach-Object {
        if ($_.Value) {
            $orderDir = Split-Path -Parent ([string]$_.Value)
            if (-not $stateDirectories.ContainsKey($orderDir)) {
                $derivedStatePath = Join-Path $orderDir "paper_position_state.json"
                if (Test-Path $derivedStatePath) {
                    $stateDirectories[$orderDir] = $true
                    $watchTargets += [pscustomobject]@{ Mode = "state"; Directory = $orderDir }
                }
                else {
                    $watchTargets += [pscustomobject]@{ Mode = "order"; Directory = $orderDir }
                }
            }
        }
    }
}

if ($watchTargets.Count -eq 0) {
    throw "No paper position/order state paths were present in $($metadata.FullName)"
}

Write-Host "TFIS S23 watcher launcher"
Write-Host "Session date : $($effectiveSessionDate.ToString('yyyy-MM-dd'))"
Write-Host "Metadata     : $($metadata.FullName)"
Write-Host "Targets      : $($watchTargets.Count)"

$started = foreach ($target in $watchTargets) {
    Start-TfisS23Watcher -Mode $target.Mode -Directory $target.Directory
}

$started | Format-Table -AutoSize
