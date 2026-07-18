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
$runtimeProcessHelperPath = Join-Path $scriptDir "tfis_runtime_process_helpers.ps1"
. $paperPositionHelperPath
. $supervisorHelperPath
. $runtimeProcessHelperPath
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
    return @(Get-TfisRuntimeProcesses -RepoRoot $repoRoot -RuntimePattern $pattern)
}

$resetStopwatch = [System.Diagnostics.Stopwatch]::StartNew()

Stop-TfisRuntimeProcesses -RepoRoot $repoRoot -CurrentProcessId $PID
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
