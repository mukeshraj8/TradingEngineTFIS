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
    [string]$ArtifactRoot = "data/strategies/S23/fyers_morning_supervised_decision",
    [string]$SessionIdPrefix = "s23-fyers-morning-supervised-decision",
    [string]$Timezone = "Asia/Kolkata",
    [ValidateSet("run_now", "abort")]
    [string]$IfPast = "run_now",
    [switch]$SkipRefresh,
    [switch]$EnableSmokeOverride,
    [string]$CarryForwardStateDir,
    [switch]$DisablePositionWatch,
    [string]$TradingHolidayCalendar = "config/nse_trading_holidays_2026.json",
    [datetime]$RunDate
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
$stamp = "{0}_{1}" -f (Get-Date -Format "yyyyMMdd_HHmmssfff"), $PID
$logPath = Join-Path $logDir "start_s23_fyers_morning_supervised_decision_$stamp.log"

function Write-LaunchLog {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"), $Message
    Add-Content -Path $logPath -Value $line
    Write-Host "[TFIS S23] $Message"
}

function Get-TfisRunDate {
    if ($RunDate) {
        return $RunDate.Date
    }
    return (Get-Date).Date
}

function Get-TfisTradingHoliday {
    param([datetime]$Date)

    $calendarPath = $TradingHolidayCalendar
    if (-not [System.IO.Path]::IsPathRooted($calendarPath)) {
        $calendarPath = Join-Path $repoRoot $calendarPath
    }
    if (-not (Test-Path $calendarPath)) {
        return $null
    }
    $calendar = Get-Content -Path $calendarPath -Raw | ConvertFrom-Json
    $dateText = $Date.ToString("yyyy-MM-dd")
    foreach ($holiday in $calendar.holidays) {
        if ([string]$holiday.date -eq $dateText) {
            return $holiday
        }
    }
    return $null
}

function Get-TfisNoRunReason {
    param([datetime]$Date)

    if ($Date.DayOfWeek -eq [System.DayOfWeek]::Saturday -or $Date.DayOfWeek -eq [System.DayOfWeek]::Sunday) {
        return "WEEKEND_NO_ACTION: $($Date.ToString('yyyy-MM-dd')) is $($Date.DayOfWeek); NSE equity/F&O market is closed."
    }
    $holiday = Get-TfisTradingHoliday -Date $Date
    if ($holiday) {
        return "NSE_HOLIDAY_NO_ACTION: $($Date.ToString('yyyy-MM-dd')) is configured as NSE holiday '$($holiday.name)'."
    }
    return $null
}

function Get-TfisLatestSessionMetadata {
    param([datetime]$Date)

    $artifactRootPath = $ArtifactRoot
    if (-not [System.IO.Path]::IsPathRooted($artifactRootPath)) {
        $artifactRootPath = Join-Path $repoRoot $artifactRootPath
    }
    $dayRoot = Join-Path $artifactRootPath $Date.ToString("yyyy-MM-dd")
    if (-not (Test-Path $dayRoot)) {
        Write-LaunchLog "No TFIS S23 artifact day directory found for watcher startup: $dayRoot"
        return $null
    }
    return Get-ChildItem -Path $dayRoot -Recurse -Filter "scheduled_run_metadata.json" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

function Get-TfisOpenPositionStatePaths {
    param(
        [Parameter(Mandatory = $true)]
        [datetime]$Date
    )

    $artifactRootPath = $ArtifactRoot
    if (-not [System.IO.Path]::IsPathRooted($artifactRootPath)) {
        $artifactRootPath = Join-Path $repoRoot $artifactRootPath
    }
    if (-not (Test-Path $artifactRootPath)) {
        Write-LaunchLog "No TFIS S23 artifact root found for open-position discovery: $artifactRootPath"
        return @()
    }

    $openStatuses = @(
        "PAPER_POSITION_OPEN",
        "PAPER_POSITION_CARRIED_FORWARD",
        "PAPER_POSITION_RESUMED"
    )
    $paths = @()
    Get-ChildItem -Path $artifactRootPath -Recurse -Filter "paper_position_state.json" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        ForEach-Object {
            try {
                $stateJson = Get-Content -Path $_.FullName -Raw | ConvertFrom-Json
            }
            catch {
                Write-LaunchLog "Skipping unreadable S23 paper position state: $($_.FullName)"
                return
            }
            $status = [string]$stateJson.lifecycle_status
            if ($openStatuses -notcontains $status) {
                return
            }
            if ($false -eq [bool]$stateJson.carry_forward_allowed) {
                return
            }
            if ($stateJson.expiry_date) {
                try {
                    $expiryDate = [datetime]::Parse([string]$stateJson.expiry_date).Date
                    if ($expiryDate -lt $Date.Date) {
                        Write-LaunchLog "Skipping expired S23 paper position state: $($_.FullName)"
                        return
                    }
                }
                catch {
                    Write-LaunchLog "S23 paper position state has unparseable expiry_date; leaving it eligible for watcher validation: $($_.FullName)"
                }
            }
            $paths += [string]$_.FullName
        }
    return $paths
}

function Resolve-TfisAbsolutePathText {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PathText
    )

    if ([string]::IsNullOrWhiteSpace($PathText)) {
        return ""
    }

    if ([System.IO.Path]::IsPathRooted($PathText)) {
        return [System.IO.Path]::GetFullPath($PathText)
    }

    return [System.IO.Path]::GetFullPath((Join-Path $repoRoot $PathText))
}

function Resolve-TfisPositionStateDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PathText
    )

    $absolutePath = Resolve-TfisAbsolutePathText -PathText $PathText
    if ([string]::IsNullOrWhiteSpace($absolutePath)) {
        return ""
    }

    if ((Split-Path -Leaf $absolutePath) -eq "paper_position_state.json" -or (Test-Path -Path $absolutePath -PathType Leaf)) {
        return [System.IO.Path]::GetDirectoryName($absolutePath)
    }

    return $absolutePath
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
    $normalizedWatchDirectory = ""
    if ($WatchDirectory) {
        $normalizedWatchDirectory = Resolve-TfisAbsolutePathText -PathText $WatchDirectory
    }
    $normalizedSearchRoot = ""
    if ($SearchRoot) {
        $normalizedSearchRoot = Resolve-TfisAbsolutePathText -PathText $SearchRoot
    }
    $watchArgs = @(
        $watchScript,
        "--tfis-root", $TfisRoot,
        "--config", $Config,
        "--skip-refresh",
        "--timezone", $Timezone
    )
    if ($Mode -eq "state") {
        $watchArgs += "--state-dir"
        $watchArgs += $normalizedWatchDirectory
    }
    elseif ($Mode -eq "order") {
        $watchArgs += "--order-dir"
        $watchArgs += $normalizedWatchDirectory
    }
    else {
        $watchArgs += "--state-search-root"
        $watchArgs += $normalizedSearchRoot
        $watchArgs += "--no-open-ok"
    }

    $labelSource = if ($normalizedWatchDirectory) { $normalizedWatchDirectory } else { $normalizedSearchRoot }
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
    if ($normalizedWatchDirectory) {
        $watchDirectoryText = $normalizedWatchDirectory
    }
    $searchRootText = ""
    if ($normalizedSearchRoot) {
        $searchRootText = $normalizedSearchRoot
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
    $encodedWatchCommand = [Convert]::ToBase64String(
        [System.Text.Encoding]::Unicode.GetBytes($watchCommand)
    )

    $process = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encodedWatchCommand) `
        -WorkingDirectory $repoRoot `
        -WindowStyle Normal `
        -PassThru

    Write-LaunchLog "Started S23 paper watch process PID=$($process.Id), mode=$Mode, directory=$normalizedWatchDirectory, searchRoot=$normalizedSearchRoot"
    Write-LaunchLog "S23 paper watch stdout: $stdoutPath"
    Write-LaunchLog "S23 paper watch stderr: $stderrPath"
}

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

$effectiveRunDate = Get-TfisRunDate

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
    $carryForwardStateDirArg = Resolve-TfisPositionStateDirectory -PathText $CarryForwardStateDir
    $args += "--carry-forward-state-dir"
    $args += $carryForwardStateDirArg
    Write-LaunchLog "Using explicit S23 carry-forward state directory: $carryForwardStateDirArg"
}
else {
    $discoveredCarryForwardStatePaths = @(Get-TfisOpenPositionStatePaths -Date $effectiveRunDate)
    if ($discoveredCarryForwardStatePaths.Count -gt 0) {
        $discoveredCarryForwardStatePath = Resolve-TfisAbsolutePathText -PathText ([string]$discoveredCarryForwardStatePaths[0])
        $discoveredCarryForwardStateDir = Resolve-TfisPositionStateDirectory -PathText $discoveredCarryForwardStatePath
        $args += "--carry-forward-state-dir"
        $args += $discoveredCarryForwardStateDir
        Write-LaunchLog "Passing latest discovered open S23 paper position to supervised decision: $discoveredCarryForwardStatePath"
        Write-LaunchLog "Carry-forward state directory argument: $discoveredCarryForwardStateDir"
    }
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

$noRunReason = Get-TfisNoRunReason -Date $effectiveRunDate
if ($noRunReason) {
    Write-LaunchLog $noRunReason
    Write-LaunchLog "Skipping TFIS S23 morning decision and watcher startup."
    Write-LaunchLog "Wrapper finished with exit code 0."
    exit 0
}

try {
    $marketClosedNoAction = $false
    $pythonOutputPath = Join-Path $logDir "run_s23_fyers_0916_supervised_decision_$stamp.out.log"
    $pythonErrorPath = Join-Path $logDir "run_s23_fyers_0916_supervised_decision_$stamp.err.log"
    Write-LaunchLog "Supervised decision stdout: $pythonOutputPath"
    Write-LaunchLog "Supervised decision stderr: $pythonErrorPath"
    Write-LaunchLog "Starting supervised decision Python process."
    & $pythonExe @args > $pythonOutputPath 2> $pythonErrorPath
    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) {
        $exitCode = 0
    }
    if (Test-Path $pythonOutputPath) {
        Get-Content -Path $pythonOutputPath | ForEach-Object {
            Write-LaunchLog ("PYTHON: {0}" -f $_)
            if ($_ -match "MARKET_CLOSED_NO_ACTION") {
                $marketClosedNoAction = $true
            }
        }
    }
    if (Test-Path $pythonErrorPath) {
        Get-Content -Path $pythonErrorPath | ForEach-Object {
            Write-LaunchLog ("PYTHON_ERR: {0}" -f $_)
            if ($_ -match "MARKET_CLOSED_NO_ACTION") {
                $marketClosedNoAction = $true
            }
        }
    }
    Write-LaunchLog "Morning supervised decision finished with exit code $exitCode."
    if ($marketClosedNoAction) {
        Write-LaunchLog "Market-closed/no-action result detected; skipping S23 paper watcher startup."
    }
    if (($exitCode -eq 0) -and (-not $DisablePositionWatch) -and (-not $marketClosedNoAction)) {
        $metadata = Get-TfisLatestSessionMetadata -Date $effectiveRunDate
        if ($metadata) {
            Write-LaunchLog "Using S23 metadata for watcher startup: $($metadata.FullName)"
            $metadataJson = Get-Content -Path $metadata.FullName -Raw | ConvertFrom-Json
            $statePaths = @()
            $orderPaths = @()
            $stateDirectories = @{}
            $openCarryForwardStatePaths = @(Get-TfisOpenPositionStatePaths -Date $effectiveRunDate)
            if ($openCarryForwardStatePaths.Count -gt 0) {
                foreach ($openStatePath in $openCarryForwardStatePaths) {
                    $openStateDir = Split-Path -Parent ([string]$openStatePath)
                    if (-not $stateDirectories.ContainsKey($openStateDir)) {
                        $statePaths += [string]$openStatePath
                        $stateDirectories[$openStateDir] = $true
                    }
                }
                Write-LaunchLog "Discovered $($openCarryForwardStatePaths.Count) open/carry-forward S23 paper position state file(s) for watcher startup."
            }
            if ($metadataJson.branch_position_state_json) {
                $metadataJson.branch_position_state_json.PSObject.Properties | ForEach-Object {
                    if ($_.Value) {
                        $metadataStateDir = Split-Path -Parent ([string]$_.Value)
                        if (-not $stateDirectories.ContainsKey($metadataStateDir)) {
                            $statePaths += [string]$_.Value
                            $stateDirectories[$metadataStateDir] = $true
                        }
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
                                $statePaths += $derivedStatePath
                                $stateDirectories[$orderDir] = $true
                            }
                            else {
                                $orderPaths += [string]$_.Value
                            }
                        }
                    }
                }
            }
            $watcherStartCount = 0
            if ($statePaths.Count -gt 0) {
                foreach ($statePath in $statePaths) {
                    $stateDir = Split-Path -Parent $statePath
                    Write-LaunchLog "Starting S23 paper position watch for state directory: $stateDir"
                    Start-S23PaperWatchProcess -Mode "state" -WatchDirectory $stateDir
                    $watcherStartCount += 1
                }
                Write-LaunchLog "Started $($statePaths.Count) S23 paper position watch process(es)."
            }
            if ($orderPaths.Count -gt 0) {
                foreach ($orderPath in $orderPaths) {
                    $orderDir = Split-Path -Parent $orderPath
                    Write-LaunchLog "Starting S23 paper order watch for order directory: $orderDir"
                    Start-S23PaperWatchProcess -Mode "order" -WatchDirectory $orderDir
                    $watcherStartCount += 1
                }
                Write-LaunchLog "Started $($orderPaths.Count) S23 paper order watch process(es)."
            }
            if ($watcherStartCount -eq 0) {
                Write-LaunchLog "No new S23 paper position/order state was produced; attempting latest state discovery under $ArtifactRoot."
                Start-S23PaperWatchProcess -Mode "discover" -SearchRoot $ArtifactRoot
            }
        }
        else {
            Write-LaunchLog "No scheduled_run_metadata.json found for $($effectiveRunDate.ToString('yyyy-MM-dd')); attempting open-position discovery under $ArtifactRoot."
            $openStatePaths = @(Get-TfisOpenPositionStatePaths -Date $effectiveRunDate)
            if ($openStatePaths.Count -gt 0) {
                foreach ($openStatePath in $openStatePaths) {
                    $openStateDir = Split-Path -Parent $openStatePath
                    Write-LaunchLog "Starting S23 paper position watch for discovered open state directory: $openStateDir"
                    Start-S23PaperWatchProcess -Mode "state" -WatchDirectory $openStateDir
                }
                Write-LaunchLog "Started $($openStatePaths.Count) discovered S23 paper position watch process(es)."
            }
            else {
                Write-LaunchLog "No open S23 paper positions found; attempting latest-open-state discovery under $ArtifactRoot."
                Start-S23PaperWatchProcess -Mode "discover" -SearchRoot $ArtifactRoot
            }
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
