param(
    [string]$DashboardOutputRoot = "tmp/operator_dashboard",
    [int]$DashboardPort = 8765
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "TFIS Operator Dashboard Refresh"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$runtimeProcessHelperPath = Join-Path $scriptDir "tfis_runtime_process_helpers.ps1"
. $runtimeProcessHelperPath

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
    $matches = @(Get-TfisRuntimeProcesses -RepoRoot $repoRoot -RuntimePattern $pattern)
    if ($matches.Count -gt 0) {
        return $matches
    }
    return @(Get-TfisPortOwnerProcesses -Port $DashboardPort)
}

$refreshStopwatch = [System.Diagnostics.Stopwatch]::StartNew()

Write-Host "============================================================"
Write-Host "TFIS OPERATOR DASHBOARD REFRESH"
Write-Host "This command rebuilds/serves the dashboard only."
Write-Host "It does not stop or restart the shared TFIS paper runtime."
Write-Host "============================================================"

& $pythonExe (Resolve-TfisPath "scripts/build_operator_dashboard.py") --output-root $DashboardOutputRoot
Write-Host ("Built TFIS dashboard in {0:n1}s total" -f $refreshStopwatch.Elapsed.TotalSeconds)

$existingDashboard = @(Get-TfisExistingDashboardProcess)
if ($existingDashboard.Count -gt 0) {
    Write-Host "Reusing existing TFIS dashboard server PID=$($existingDashboard[0].ProcessId) URL=http://127.0.0.1:$DashboardPort/index.html"
}
else {
    $dashboardProcess = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList @((Resolve-TfisPath "scripts/serve_operator_dashboard.py"), "--output-root", $DashboardOutputRoot, "--port", "$DashboardPort", "--skip-build") `
        -WorkingDirectory $repoRoot `
        -WindowStyle Normal `
        -PassThru
    Write-Host "Started TFIS dashboard PID=$($dashboardProcess.Id) URL=http://127.0.0.1:$DashboardPort/index.html"
}

if (Wait-ForDashboardReady -Port $DashboardPort) {
    Write-Host "TFIS dashboard is accepting connections."
}
else {
    Write-Host "WARNING: TFIS dashboard was rebuilt but port $DashboardPort is not accepting connections yet."
}

Write-Host ("TFIS operator dashboard refresh complete in {0:n1}s." -f $refreshStopwatch.Elapsed.TotalSeconds)
