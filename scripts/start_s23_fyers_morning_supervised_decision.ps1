param(
    [string]$TfisRoot,
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
    [string]$CarryForwardStateDir,
    [switch]$DisablePositionWatch
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot
if (-not $TfisRoot) {
    $TfisRoot = $repoRoot
}

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
    "--tfis-root", $TfisRoot,
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
Write-LaunchLog "TfisRoot: $TfisRoot"
Write-LaunchLog "ArtifactRoot: $ArtifactRoot"
Write-LaunchLog "SessionIdPrefix: $SessionIdPrefix"

try {
    & $pythonExe @args 2>&1 | ForEach-Object {
        Write-LaunchLog ("PYTHON: {0}" -f $_)
        Write-Output $_
    }
    $exitCode = $LASTEXITCODE
    Write-LaunchLog "Morning supervised decision finished with exit code $exitCode."
    if (($exitCode -eq 0) -and (-not $DisablePositionWatch)) {
        $artifactRootPath = Join-Path $repoRoot $ArtifactRoot
        $metadata = Get-ChildItem -Path $artifactRootPath -Recurse -Filter "scheduled_run_metadata.json" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($metadata) {
            $metadataJson = Get-Content -Path $metadata.FullName -Raw | ConvertFrom-Json
            $statePaths = @()
            if ($metadataJson.branch_position_state_json) {
                $metadataJson.branch_position_state_json.PSObject.Properties | ForEach-Object {
                    if ($_.Value) {
                        $statePaths += [string]$_.Value
                    }
                }
            }
            if ($statePaths.Count -eq 1) {
                $stateDir = Split-Path -Parent $statePaths[0]
                Write-LaunchLog "Starting S23 paper position watch for state directory: $stateDir"
                & $pythonExe (Join-Path $repoRoot "scripts\run_s23_paper_position_watch.py") `
                    --tfis-root $TfisRoot `
                    --config $Config `
                    --state-dir $stateDir `
                    --timezone $Timezone 2>&1 | ForEach-Object {
                        Write-LaunchLog ("WATCH: {0}" -f $_)
                        Write-Output $_
                    }
                $exitCode = $LASTEXITCODE
                Write-LaunchLog "S23 paper position watch finished with exit code $exitCode."
            }
            elseif ($statePaths.Count -gt 1) {
                Write-LaunchLog "Multiple S23 paper position states were produced; automatic watch skipped so the operator can choose the branch."
            }
            else {
                Write-LaunchLog "No new S23 paper position state was produced; attempting latest-open-state discovery under $ArtifactRoot."
                & $pythonExe (Join-Path $repoRoot "scripts\run_s23_paper_position_watch.py") `
                    --tfis-root $TfisRoot `
                    --config $Config `
                    --state-search-root $ArtifactRoot `
                    --timezone $Timezone `
                    --no-open-ok 2>&1 | ForEach-Object {
                        Write-LaunchLog ("WATCH: {0}" -f $_)
                        Write-Output $_
                    }
                $exitCode = $LASTEXITCODE
                Write-LaunchLog "S23 paper position watch discovery run finished with exit code $exitCode."
            }
        }
        else {
            Write-LaunchLog "No scheduled_run_metadata.json found under $artifactRootPath; attempting latest-open-state discovery."
            & $pythonExe (Join-Path $repoRoot "scripts\run_s23_paper_position_watch.py") `
                --tfis-root $TfisRoot `
                --config $Config `
                --state-search-root $ArtifactRoot `
                --timezone $Timezone `
                --no-open-ok 2>&1 | ForEach-Object {
                    Write-LaunchLog ("WATCH: {0}" -f $_)
                    Write-Output $_
                }
            $exitCode = $LASTEXITCODE
            Write-LaunchLog "S23 paper position watch discovery run finished with exit code $exitCode."
        }
    }
    elseif ($DisablePositionWatch) {
        Write-LaunchLog "Position watch disabled by switch."
    }
    Write-LaunchLog "Wrapper finished with exit code $exitCode."
    exit $exitCode
}
catch {
    Write-LaunchLog ("Wrapper failed: {0}" -f $_.Exception.Message)
    throw
}
