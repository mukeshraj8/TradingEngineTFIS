param(
    [string]$TfisRoot,
    [string]$DashboardOutputRoot = "tmp/operator_dashboard",
    [int]$DashboardPort = 8765,
    [string]$S23Config = "config/paper.s23.fyers_connect_test.yaml",
    [string]$S23ArtifactRoot = "data/strategies/S23/fyers_morning_supervised_decision",
    [string]$S21Config = "config/paper.s21.fyers_connect_test.yaml",
    [string]$S21ArtifactRoot = "data/strategies/S21/fyers_morning_supervised_decision",
    [string]$Timezone = "Asia/Kolkata"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
if (-not $TfisRoot) {
    $TfisRoot = $repoRoot
}
Set-Location $repoRoot

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Missing python executable: $pythonExe"
}

function Resolve-TfisPath {
    param([string]$PathText)
    if ([System.IO.Path]::IsPathRooted($PathText)) {
        return [System.IO.Path]::GetFullPath($PathText)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $repoRoot $PathText))
}

function New-TfisRegexAlternation {
    param([string[]]$Values)

    $parts = @()
    foreach ($value in $Values) {
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            $parts += [Regex]::Escape($value)
        }
    }
    $parts = $parts | Select-Object -Unique
    if ($parts.Count -eq 0) {
        return ""
    }
    if ($parts.Count -eq 1) {
        return $parts[0]
    }
    return "(?:" + ($parts -join "|") + ")"
}

function Get-TfisProcessCandidates {
    $nameFilter = "Name = 'python.exe' OR Name = 'pythonw.exe' OR Name = 'powershell.exe' OR Name = 'pwsh.exe'"
    return @(
        Get-CimInstance Win32_Process -Filter $nameFilter -ErrorAction SilentlyContinue
    )
}

function Get-TfisRuntimeProcesses {
    param([string]$RuntimePattern)

    $repoPattern = [Regex]::Escape($repoRoot)
    $effectivePattern = if ([string]::IsNullOrWhiteSpace($RuntimePattern)) {
        'build_operator_dashboard\.py|serve_operator_dashboard\.py|run_s23_paper_position_watch\.py|start_s21_paper_watchers_from_metadata\.ps1|start_s23_paper_watchers_from_metadata\.ps1|run_s21_banknifty_0916_supervised_decision\.py|run_s23_fyers_0916_supervised_decision\.py'
    }
    else {
        $RuntimePattern
    }
    return @(
        Get-TfisProcessCandidates |
        Where-Object {
            $cmd = $_.CommandLine
            if (-not $cmd) {
                return $false
            }
            if ($cmd -notmatch $repoPattern) {
                return $false
            }
            return $cmd -match $effectivePattern
        } |
        Sort-Object ProcessId
    )
}

function Get-LatestSessionDate {
    param([string]$ArtifactRoot)
    $artifactRootPath = Resolve-TfisPath $ArtifactRoot
    if (-not (Test-Path $artifactRootPath)) {
        return $null
    }
    $dir = Get-ChildItem -Directory $artifactRootPath |
        Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}$' } |
        Sort-Object Name -Descending |
        Select-Object -First 1
    if (-not $dir) {
        return $null
    }
    return $dir.Name
}

function Test-TfisWatchablePositionState {
    param([string]$StateDirectory)

    $statePath = Join-Path (Resolve-TfisPath $StateDirectory) "paper_position_state.json"
    if (-not (Test-Path $statePath)) {
        return $false
    }

    try {
        $stateJson = Get-Content -Path $statePath -Raw | ConvertFrom-Json
    }
    catch {
        Write-Host "Skipping unreadable paper position state: $statePath"
        return $false
    }

    $status = [string]$stateJson.lifecycle_status
    return $status -in @(
        "PAPER_POSITION_OPEN",
        "PAPER_POSITION_CARRIED_FORWARD",
        "PAPER_POSITION_RESUMED"
    )
}

function Get-TfisLivePositionStateDirectories {
    param(
        [string]$ArtifactRoot,
        [datetime]$EffectiveDate
    )

    $artifactRootPath = Resolve-TfisPath $ArtifactRoot
    if (-not (Test-Path $artifactRootPath)) {
        return @()
    }

    $stateDirectories = @()
    Get-ChildItem -Path $artifactRootPath -Recurse -Filter "paper_position_state.json" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        ForEach-Object {
            $statePath = $_.FullName
            $stateDir = Split-Path -Parent $statePath

            try {
                $stateJson = Get-Content -Path $statePath -Raw | ConvertFrom-Json
            }
            catch {
                Write-Host "Skipping unreadable paper position state during recovery scan: $statePath"
                return
            }

            $status = [string]$stateJson.lifecycle_status
            if ($status -notin @("PAPER_POSITION_OPEN", "PAPER_POSITION_CARRIED_FORWARD", "PAPER_POSITION_RESUMED")) {
                return
            }

            if ($false -eq [bool]$stateJson.carry_forward_allowed) {
                Write-Host "Skipping non-carry-forward paper position state during recovery scan: $statePath"
                return
            }

            if ($stateJson.expiry_date) {
                try {
                    $expiryDate = [datetime]::Parse([string]$stateJson.expiry_date).Date
                    if ($expiryDate -lt $EffectiveDate.Date) {
                        Write-Host "Skipping expired paper position state during recovery scan: $statePath"
                        return
                    }
                }
                catch {
                    Write-Host "Paper position state has unparseable expiry_date; keeping it eligible for recovery scan: $statePath"
                }
            }

            $stateDirectories += $stateDir
        }

    return $stateDirectories | Select-Object -Unique
}

function Wait-ForNoTfisRuntimeProcesses {
    param(
        [int[]]$ProcessIds = @(),
        [int]$TimeoutSeconds = 12
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $remaining = @()
        if ($ProcessIds.Count -gt 0) {
            foreach ($processId in $ProcessIds | Select-Object -Unique) {
                try {
                    $null = Get-Process -Id $processId -ErrorAction Stop
                    $remaining += $processId
                }
                catch {
                    continue
                }
            }
        }
        else {
            $remaining = @(Get-TfisRuntimeProcesses | Select-Object -ExpandProperty ProcessId)
        }
        if ($remaining.Count -eq 0) {
            return
        }
        Start-Sleep -Milliseconds 500
    }

    $remainingDetails = @(
        Get-TfisRuntimeProcesses | ForEach-Object {
            "PID=$($_.ProcessId)"
        }
    )
    throw "Timed out waiting for TFIS runtime processes to exit: $($remainingDetails -join ', ')"
}

function Stop-TfisProcessTree {
    param([int]$ProcessId)

    $taskkillExe = Join-Path $env:SystemRoot "System32\taskkill.exe"
    if (Test-Path $taskkillExe) {
        & $taskkillExe /PID $ProcessId /T /F 2>$null | Out-Null
        return
    }

    Stop-Process -Id $ProcessId -Force -ErrorAction Stop
}

function Wait-ForDashboardReady {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 15
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $client = [System.Net.Sockets.TcpClient]::new()
            try {
                $asyncResult = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
                if ($asyncResult.AsyncWaitHandle.WaitOne(500) -and $client.Connected) {
                    $client.EndConnect($asyncResult)
                    return $true
                }
            }
            finally {
                $client.Dispose()
            }
        }
        catch {
        }

        Start-Sleep -Milliseconds 250
    }

    return $false
}

function Get-TfisExistingDashboardProcess {
    $portPattern = [Regex]::Escape("--port")
    $outputRootPattern = New-TfisRegexAlternation @($DashboardOutputRoot, (Resolve-TfisPath $DashboardOutputRoot))
    $pattern = "serve_operator_dashboard\.py.*$([Regex]::Escape('--output-root'))\s+$outputRootPattern.*$portPattern\s+$DashboardPort(?:\s|$)"
    return @(Get-TfisRuntimeProcesses -RuntimePattern $pattern)
}

function Get-TfisExistingWatcherProcess {
    param(
        [string]$Mode,
        [string]$Directory,
        [string]$ConfigPath
    )

    $modeFlag = if ($Mode -eq "state") { "--state-dir" } else { "--order-dir" }
    $modePattern = [Regex]::Escape($modeFlag)
    $directoryPattern = New-TfisRegexAlternation @($Directory, (Resolve-TfisPath $Directory))
    $configPattern = New-TfisRegexAlternation @($ConfigPath, (Resolve-TfisPath $ConfigPath))
    $pattern = "run_s23_paper_position_watch\.py.*$([Regex]::Escape('--config'))\s+$configPattern.*$modePattern\s+$directoryPattern(?:\s|$)"
    return @(Get-TfisRuntimeProcesses -RuntimePattern $pattern)
}

function Stop-TfisRuntimeProcesses {
    $processes = @(Get-TfisRuntimeProcesses)
    $targetProcessIds = @()

    foreach ($proc in $processes) {
        if ($proc.ProcessId -eq $PID) {
            continue
        }
        $targetProcessIds += $proc.ProcessId
        Write-Host "Stopping TFIS process PID=$($proc.ProcessId)"
        try {
            Stop-TfisProcessTree -ProcessId $proc.ProcessId
        }
        catch {
            Write-Host "TFIS process PID=$($proc.ProcessId) already exited"
        }
    }

    if ($targetProcessIds.Count -gt 0) {
        Wait-ForNoTfisRuntimeProcesses -ProcessIds $targetProcessIds
    }
}

function Get-WatchTargets {
    param([string]$ArtifactRoot, [string]$SessionDate)
    $artifactRootPath = Resolve-TfisPath $ArtifactRoot
    $effectiveDate = [datetime]::Parse($SessionDate)
    $dayRoot = Join-Path $artifactRootPath $SessionDate
    $targets = @()
    $stateDirectories = @{}

    foreach ($stateDir in @(Get-TfisLivePositionStateDirectories -ArtifactRoot $ArtifactRoot -EffectiveDate $effectiveDate)) {
        if (Test-TfisWatchablePositionState -StateDirectory $stateDir) {
            $stateDirectories[$stateDir] = $true
            $targets += [pscustomobject]@{ Mode = "state"; Directory = $stateDir }
        }
    }

    if (Test-Path $dayRoot) {
        $metadata = Get-ChildItem -Path $dayRoot -Recurse -Filter "scheduled_run_metadata.json" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($metadata) {
            $metadataJson = Get-Content -Path $metadata.FullName -Raw | ConvertFrom-Json
            $sessionIsToday = $SessionDate -eq (Get-Date).ToString("yyyy-MM-dd")
            if ($metadataJson.branch_position_state_json) {
                $metadataJson.branch_position_state_json.PSObject.Properties | ForEach-Object {
                    if ($_.Value) {
                        $stateDir = Split-Path -Parent ([string]$_.Value)
                        if ((-not $stateDirectories.ContainsKey($stateDir)) -and (Test-TfisWatchablePositionState -StateDirectory $stateDir)) {
                            $stateDirectories[$stateDir] = $true
                            $targets += [pscustomobject]@{ Mode = "state"; Directory = $stateDir }
                        }
                    }
                }
            }
            if ($metadataJson.branch_order_state_json -and $sessionIsToday) {
                $metadataJson.branch_order_state_json.PSObject.Properties | ForEach-Object {
                    if ($_.Value) {
                        $orderDir = Split-Path -Parent ([string]$_.Value)
                        if (-not $stateDirectories.ContainsKey($orderDir)) {
                            $derivedStatePath = Join-Path $orderDir "paper_position_state.json"
                            if ((Test-Path $derivedStatePath) -and (Test-TfisWatchablePositionState -StateDirectory $orderDir)) {
                                $stateDirectories[$orderDir] = $true
                                $targets += [pscustomobject]@{ Mode = "state"; Directory = $orderDir }
                            }
                            else {
                                $targets += [pscustomobject]@{ Mode = "order"; Directory = $orderDir }
                            }
                        }
                    }
                }
            }
            elseif ($metadataJson.branch_order_state_json) {
                Write-Host "Skipping stale waiting-order watcher startup for prior session $SessionDate under $ArtifactRoot"
            }
        }
    }

    return $targets
}

function Start-WatcherProcesses {
    param(
        [string]$StrategyCode,
        [string]$ConfigPath,
        [string]$ArtifactRoot,
        [string]$ProcessLockRoot,
        [string]$SessionDate
    )

    $targets = Get-WatchTargets -ArtifactRoot $ArtifactRoot -SessionDate $SessionDate
    if ($targets.Count -eq 0) {
        Write-Host "No watcher targets found for $StrategyCode on $SessionDate"
        return
    }

    $seenTargets = @{}
    foreach ($target in $targets) {
        $resolvedTargetDirectory = Resolve-TfisPath $target.Directory
        $targetKey = "{0}|{1}" -f $target.Mode, $resolvedTargetDirectory
        if ($seenTargets.ContainsKey($targetKey)) {
            Write-Host "Skipping duplicate $StrategyCode watcher target mode=$($target.Mode) dir=$resolvedTargetDirectory"
            continue
        }
        $seenTargets[$targetKey] = $true

        $existingProcess = @(Get-TfisExistingWatcherProcess -Mode $target.Mode -Directory $target.Directory -ConfigPath $ConfigPath)
        if ($existingProcess.Count -gt 0) {
            Write-Host "Skipping $StrategyCode watcher start because matching process is already running: PID=$($existingProcess[0].ProcessId) mode=$($target.Mode) dir=$resolvedTargetDirectory"
            continue
        }

        $args = @(
            (Resolve-TfisPath "scripts/run_s23_paper_position_watch.py"),
            "--tfis-root", $TfisRoot,
            "--config", (Resolve-TfisPath $ConfigPath),
            "--skip-refresh",
            "--timezone", $Timezone,
            "--process-lock-root", $ProcessLockRoot,
            "--dashboard-output-root", $DashboardOutputRoot,
            "--s23-artifact-root", $ArtifactRoot
        )
        if ($target.Mode -eq "state") {
            $args += "--state-dir"
            $args += $target.Directory
        }
        else {
            $args += "--order-dir"
            $args += $target.Directory
        }

        $process = Start-Process `
            -FilePath $pythonExe `
            -ArgumentList $args `
            -WorkingDirectory $repoRoot `
            -WindowStyle Normal `
            -PassThru

        Write-Host "Started $StrategyCode watcher PID=$($process.Id) mode=$($target.Mode) dir=$($target.Directory)"
    }
}

$resetStopwatch = [System.Diagnostics.Stopwatch]::StartNew()

Stop-TfisRuntimeProcesses
Write-Host ("Stopped prior TFIS runtime in {0:n1}s" -f $resetStopwatch.Elapsed.TotalSeconds)

& $pythonExe (Resolve-TfisPath "scripts/build_operator_dashboard.py") --output-root $DashboardOutputRoot
Write-Host ("Built TFIS dashboard in {0:n1}s total" -f $resetStopwatch.Elapsed.TotalSeconds)

$existingDashboard = @(Get-TfisExistingDashboardProcess)
if ($existingDashboard.Count -gt 0) {
    Write-Host "Skipping TFIS dashboard start because matching server is already running: PID=$($existingDashboard[0].ProcessId) URL=http://127.0.0.1:$DashboardPort/index.html"
}
else {
    $dashboardProcess = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList @((Resolve-TfisPath "scripts/serve_operator_dashboard.py"), "--output-root", $DashboardOutputRoot, "--port", "$DashboardPort", "--skip-build") `
        -WorkingDirectory $repoRoot `
        -WindowStyle Normal `
        -PassThru
    Write-Host "Started TFIS dashboard PID=$($dashboardProcess.Id) URL=http://127.0.0.1:$DashboardPort/index.html"
    if (Wait-ForDashboardReady -Port $DashboardPort) {
        Write-Host "TFIS dashboard is accepting connections."
    }
    else {
        Write-Host "WARNING: TFIS dashboard process started but port $DashboardPort is not accepting connections yet."
    }
}

$s23SessionDate = Get-LatestSessionDate -ArtifactRoot $S23ArtifactRoot
if ($s23SessionDate) {
    Start-WatcherProcesses `
        -StrategyCode "S23" `
        -ConfigPath $S23Config `
        -ArtifactRoot $S23ArtifactRoot `
        -ProcessLockRoot "tmp/process_locks/s23_paper_watch" `
        -SessionDate $s23SessionDate
}
else {
    Write-Host "No S23 session directory found under $S23ArtifactRoot"
}

$s21SessionDate = Get-LatestSessionDate -ArtifactRoot $S21ArtifactRoot
if ($s21SessionDate) {
    Start-WatcherProcesses `
        -StrategyCode "S21" `
        -ConfigPath $S21Config `
        -ArtifactRoot $S21ArtifactRoot `
        -ProcessLockRoot "tmp/process_locks/s21_paper_watch" `
        -SessionDate $s21SessionDate
}
else {
    Write-Host "No S21 session directory found under $S21ArtifactRoot"
}

Write-Host ("TFIS dashboard/watcher reset complete in {0:n1}s." -f $resetStopwatch.Elapsed.TotalSeconds)
