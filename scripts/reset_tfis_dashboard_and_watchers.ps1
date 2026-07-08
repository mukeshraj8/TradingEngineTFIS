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

function Get-TfisRuntimeProcesses {
    param([string]$RuntimePattern)

    $repoPattern = [Regex]::Escape($repoRoot)
    $effectivePattern = if ([string]::IsNullOrWhiteSpace($RuntimePattern)) {
        'serve_operator_dashboard\.py|run_s23_paper_position_watch\.py|start_s21_paper_watchers_from_metadata\.ps1|start_s23_paper_watchers_from_metadata\.ps1|run_s21_banknifty_0916_supervised_decision\.py|run_s23_fyers_0916_supervised_decision\.py'
    }
    else {
        $RuntimePattern
    }
    return @(
        Get-CimInstance Win32_Process |
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

function Wait-ForNoTfisRuntimeProcesses {
    param([int]$TimeoutSeconds = 20)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $remaining = @(Get-TfisRuntimeProcesses)
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

    foreach ($proc in $processes) {
        if ($proc.ProcessId -eq $PID) {
            continue
        }
        Write-Host "Stopping TFIS process PID=$($proc.ProcessId)"
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
        }
        catch {
            Write-Host "TFIS process PID=$($proc.ProcessId) already exited"
        }
    }

    if ($processes.Count -gt 0) {
        Wait-ForNoTfisRuntimeProcesses
    }
}

function Get-WatchTargets {
    param([string]$ArtifactRoot, [string]$SessionDate)
    $artifactRootPath = Resolve-TfisPath $ArtifactRoot
    $dayRoot = Join-Path $artifactRootPath $SessionDate
    if (-not (Test-Path $dayRoot)) {
        return @()
    }
    $metadata = Get-ChildItem -Path $dayRoot -Recurse -Filter "scheduled_run_metadata.json" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $metadata) {
        return @()
    }
    $metadataJson = Get-Content -Path $metadata.FullName -Raw | ConvertFrom-Json
    $targets = @()
    $stateDirectories = @{}
    if ($metadataJson.branch_position_state_json) {
        $metadataJson.branch_position_state_json.PSObject.Properties | ForEach-Object {
            if ($_.Value) {
                $stateDir = Split-Path -Parent ([string]$_.Value)
                $stateDirectories[$stateDir] = $true
                $targets += [pscustomobject]@{ Mode = "state"; Directory = $stateDir }
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
                        $targets += [pscustomobject]@{ Mode = "state"; Directory = $orderDir }
                    }
                    else {
                        $targets += [pscustomobject]@{ Mode = "order"; Directory = $orderDir }
                    }
                }
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

Stop-TfisRuntimeProcesses

& $pythonExe (Resolve-TfisPath "scripts/build_operator_dashboard.py") --output-root $DashboardOutputRoot

$existingDashboard = @(Get-TfisExistingDashboardProcess)
if ($existingDashboard.Count -gt 0) {
    Write-Host "Skipping TFIS dashboard start because matching server is already running: PID=$($existingDashboard[0].ProcessId) URL=http://127.0.0.1:$DashboardPort/index.html"
}
else {
    $dashboardProcess = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList @((Resolve-TfisPath "scripts/serve_operator_dashboard.py"), "--output-root", $DashboardOutputRoot, "--port", "$DashboardPort") `
        -WorkingDirectory $repoRoot `
        -WindowStyle Normal `
        -PassThru
    Write-Host "Started TFIS dashboard PID=$($dashboardProcess.Id) URL=http://127.0.0.1:$DashboardPort/index.html"
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

Write-Host "TFIS dashboard/watcher reset complete."
