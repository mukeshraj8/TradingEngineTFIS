param(
    [string]$TfisRoot,
    [string]$DashboardOutputRoot = "tmp/operator_dashboard",
    [int]$DashboardPort = 8765,
    [string]$TargetsConfig = "config/paper_lifecycle_supervisor_targets.yaml",
    [string]$S23Config = "config/paper.s23.fyers_connect_test.yaml",
    [string]$S23ArtifactRoot = "data/strategies/S23/fyers_morning_supervised_decision",
    [string]$S21Config = "config/paper.s21.fyers_connect_test.yaml",
    [string]$S21ArtifactRoot = "data/strategies/S21/fyers_morning_supervised_decision",
    [string]$Timezone = "Asia/Kolkata"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$paperPositionHelperPath = Join-Path $scriptDir "tfis_paper_position_state_helpers.ps1"
$supervisorHelperPath = Join-Path $scriptDir "tfis_paper_lifecycle_supervisor_helpers.ps1"
. $paperPositionHelperPath
. $supervisorHelperPath
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
        'build_operator_dashboard\.py|serve_operator_dashboard\.py|run_s23_paper_position_watch\.py|run_tfis_paper_lifecycle_supervisor\.py|start_tfis_paper_lifecycle_supervisor\.ps1|start_s21_paper_watchers_from_metadata\.ps1|start_s23_paper_watchers_from_metadata\.ps1|run_s21_banknifty_0916_supervised_decision\.py|run_s23_fyers_0916_supervised_decision\.py'
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

$supervisorProcess = Start-TfisPaperLifecycleSupervisorProcess `
    -RepoRoot $repoRoot `
    -TfisRoot $TfisRoot `
    -TargetsConfig (Resolve-TfisPath $TargetsConfig) `
    -DashboardOutputRoot $DashboardOutputRoot `
    -DashboardPort $DashboardPort `
    -SessionDate (Get-Date)

Write-Host "Started shared TFIS paper lifecycle supervisor PID=$($supervisorProcess.Id)"
Write-Host ("TFIS dashboard/supervisor reset complete in {0:n1}s." -f $resetStopwatch.Elapsed.TotalSeconds)
