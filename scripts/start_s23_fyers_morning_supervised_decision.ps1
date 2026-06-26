param(
    [string]$TfisRoot,
    [string]$Config = "config/paper.s23.fyers_connect_test.yaml",
    [string[]]$StrategyPath = @(
        "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
        "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
        "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
        "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
    ),
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
$Host.UI.RawUI.WindowTitle = "TFIS S23 Morning Supervised Decision"
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
    Write-Host "[TFIS S23] $Message"
}

function Start-S23PaperWatchProcess {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("state", "order", "discover")]
        [string]$Mode,
        [string]$WatchDirectory,
        [string]$SearchRoot
    )

    $watchScript = Join-Path $repoRoot "scripts\run_s23_paper_position_watch.py"
    $watchArgs = @(
        $watchScript,
        "--tfis-root", $TfisRoot,
        "--config", $Config,
        "--skip-refresh",
        "--timezone", $Timezone
    )
    if ($Mode -eq "state") {
        $watchArgs += "--state-dir"
        $watchArgs += $WatchDirectory
    }
    elseif ($Mode -eq "order") {
        $watchArgs += "--order-dir"
        $watchArgs += $WatchDirectory
    }
    else {
        $watchArgs += "--state-search-root"
        $watchArgs += $SearchRoot
        $watchArgs += "--no-open-ok"
    }

    $labelSource = if ($WatchDirectory) { $WatchDirectory } else { $SearchRoot }
    $safeLabel = (($labelSource -replace '^[A-Za-z]:', '') -replace '[\\/:*?"<>|\s]+', '_').Trim('_')
    if (-not $safeLabel) {
        $safeLabel = "discovery"
    }
    if ($safeLabel.Length -gt 96) {
        $safeLabel = $safeLabel.Substring($safeLabel.Length - 96)
    }
    $watchStamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $stdoutPath = Join-Path $logDir "s23_paper_watch_${Mode}_${safeLabel}_${watchStamp}.out.log"
    $stderrPath = Join-Path $logDir "s23_paper_watch_${Mode}_${safeLabel}_${watchStamp}.err.log"

    $windowTitle = "TFIS S23 Paper Watch - $Mode"
    $quotedWindowTitle = "'" + ($windowTitle -replace "'", "''") + "'"
    $quotedRepoRoot = "'" + ($repoRoot -replace "'", "''") + "'"
    $quotedPythonExe = "'" + ($pythonExe -replace "'", "''") + "'"
    $quotedWatchArgs = @($watchArgs | ForEach-Object { "'" + ($_ -replace "'", "''") + "'" })
    $quotedStdoutPath = "'" + ($stdoutPath -replace "'", "''") + "'"
    $quotedStderrPath = "'" + ($stderrPath -replace "'", "''") + "'"
    $quotedMode = "'" + ($Mode -replace "'", "''") + "'"
    $watchDirectoryText = ""
    if ($WatchDirectory) {
        $watchDirectoryText = $WatchDirectory
    }
    $searchRootText = ""
    if ($SearchRoot) {
        $searchRootText = $SearchRoot
    }
    $quotedWatchDirectory = "'" + ($watchDirectoryText -replace "'", "''") + "'"
    $quotedSearchRoot = "'" + ($searchRootText -replace "'", "''") + "'"
    $watchCommand = @"
`$Host.UI.RawUI.WindowTitle = $quotedWindowTitle
Write-Host "============================================================"
Write-Host "TFIS S23 PAPER WATCHER"
Write-Host "Mode       : $quotedMode"
Write-Host "Directory  : $quotedWatchDirectory"
Write-Host "SearchRoot : $quotedSearchRoot"
Write-Host "Repo       : $quotedRepoRoot"
Write-Host "Stdout log : $quotedStdoutPath"
Write-Host "Stderr log : $quotedStderrPath"
Write-Host "============================================================"
Write-Host "Starting watcher. Leave this window open while TFIS paper orders/positions are being monitored."
Set-Location $quotedRepoRoot
& $quotedPythonExe $($quotedWatchArgs -join ' ') 2> $quotedStderrPath | Tee-Object -FilePath $quotedStdoutPath -Append
`$tfisWatchExitCode = `$LASTEXITCODE
Write-Host "============================================================"
Write-Host "TFIS S23 paper watcher exited with code `$tfisWatchExitCode."
Write-Host "If this was during market hours and an order/position should still be monitored, restart the watcher."
Write-Host "This window is held open for review; it is safe to close only after you have read the status above."
Write-Host "============================================================"
"@

    $process = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $watchCommand) `
        -WorkingDirectory $repoRoot `
        -WindowStyle Normal `
        -PassThru

    Write-LaunchLog "Started S23 paper watch process PID=$($process.Id), mode=$Mode, directory=$WatchDirectory, searchRoot=$SearchRoot"
    Write-LaunchLog "S23 paper watch stdout: $stdoutPath"
    Write-LaunchLog "S23 paper watch stderr: $stderrPath"
}

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

$args = @(
    (Join-Path $repoRoot "scripts\run_s23_fyers_0916_supervised_decision.py"),
    "--tfis-root", $TfisRoot,
    "--config", $Config,
    "--reference-packet", $ReferencePacket,
    "--artifact-root", $ArtifactRoot,
    "--session-id-prefix", $SessionIdPrefix,
    "--timezone", $Timezone,
    "--if-past", $IfPast
)

foreach ($strategy in $StrategyPath) {
    if ($strategy) {
        $args += "--strategy-path"
        $args += $strategy
    }
}

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

Write-Host "============================================================"
Write-Host "TFIS S23 MORNING SUPERVISED DECISION"
Write-Host "This window belongs to TradingEngineTFIS only."
Write-Host "Repo: $repoRoot"
Write-Host "Log : $logPath"
Write-Host "============================================================"
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
            $orderPaths = @()
            if ($metadataJson.branch_position_state_json) {
                $metadataJson.branch_position_state_json.PSObject.Properties | ForEach-Object {
                    if ($_.Value) {
                        $statePaths += [string]$_.Value
                    }
                }
            }
            if ($metadataJson.branch_order_state_json) {
                $metadataJson.branch_order_state_json.PSObject.Properties | ForEach-Object {
                    if ($_.Value) {
                        $orderPaths += [string]$_.Value
                    }
                }
            }
            if ($statePaths.Count -gt 0) {
                foreach ($statePath in $statePaths) {
                    $stateDir = Split-Path -Parent $statePath
                    Write-LaunchLog "Starting S23 paper position watch for state directory: $stateDir"
                    Start-S23PaperWatchProcess -Mode "state" -WatchDirectory $stateDir
                }
                Write-LaunchLog "Started $($statePaths.Count) S23 paper position watch process(es)."
            }
            elseif ($orderPaths.Count -gt 0) {
                foreach ($orderPath in $orderPaths) {
                    $orderDir = Split-Path -Parent $orderPath
                    Write-LaunchLog "Starting S23 paper order watch for order directory: $orderDir"
                    Start-S23PaperWatchProcess -Mode "order" -WatchDirectory $orderDir
                }
                Write-LaunchLog "Started $($orderPaths.Count) S23 paper order watch process(es)."
            }
            else {
                Write-LaunchLog "No new S23 paper position/order state was produced; attempting latest state discovery under $ArtifactRoot."
                Start-S23PaperWatchProcess -Mode "discover" -SearchRoot $ArtifactRoot
            }
        }
        else {
            Write-LaunchLog "No scheduled_run_metadata.json found under $artifactRootPath; attempting latest-open-state discovery."
            Start-S23PaperWatchProcess -Mode "discover" -SearchRoot $ArtifactRoot
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
