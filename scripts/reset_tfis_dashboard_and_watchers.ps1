param(
    [string]$TfisRoot,
    [string]$DashboardOutputRoot = "tmp/operator_dashboard",
    [int]$DashboardPort = 8765,
    [string]$TargetsConfig = "config/paper_lifecycle_supervisor_targets.yaml",
    [string]$S23Config = "config/paper.s23.fyers_connect_test.yaml",
    [string]$S23ArtifactRoot = "data/strategies/S23/fyers_morning_supervised_decision",
    [string]$S21Config = "config/paper.s21.fyers_connect_test.yaml",
    [string]$S21ArtifactRoot = "data/strategies/S21/fyers_morning_supervised_decision",
    [string]$Timezone = "Asia/Kolkata",
    [switch]$MorningStartup,
    [switch]$SkipAuthPreparation,
    [datetime]$RunDate = (Get-Date),
    [switch]$ForceInMarketReset,
    [string]$TradingHolidayCalendar = "config/nse_trading_holidays_2026.json"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$paperPositionHelperPath = Join-Path $scriptDir "tfis_paper_position_state_helpers.ps1"
$supervisorHelperPath = Join-Path $scriptDir "tfis_paper_lifecycle_supervisor_helpers.ps1"
$runtimeProcessHelperPath = Join-Path $scriptDir "tfis_runtime_process_helpers.ps1"
$tradingCalendarHelperPath = Join-Path $scriptDir "tfis_trading_calendar_helpers.ps1"
. $paperPositionHelperPath
. $supervisorHelperPath
. $runtimeProcessHelperPath
. $tradingCalendarHelperPath
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

function Get-TfisMorningStartupWrapperPaths {
    $targetsConfigPath = Resolve-TfisPath $TargetsConfig
    if (-not (Test-Path $targetsConfigPath)) {
        throw "Missing TFIS lifecycle supervisor targets config: $targetsConfigPath"
    }

    $pythonCode = @'
import sys
from pathlib import Path

import yaml

data = yaml.safe_load(Path(sys.argv[1]).read_text(encoding='utf-8')) or {}
wrappers = []
for target in data.get('targets', []):
    wrapper = (target.get('wrapper_script_path') or '').strip()
    if wrapper and wrapper not in wrappers:
        wrappers.append(wrapper)
for wrapper in wrappers:
    print(wrapper)
'@
    $wrappers = @(& $pythonExe -c $pythonCode $targetsConfigPath)
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to load TFIS morning startup wrappers from $targetsConfigPath"
    }
    return @($wrappers | Where-Object { $_ })
}

function Invoke-TfisRuntimeAuthPreparation {
    $targetsConfigPath = Resolve-TfisPath $TargetsConfig
    $pythonCode = @'
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
src_root = repo_root / 'src'
if str(src_root) not in sys.path:
    sys.path.insert(0, str(src_root))

from tfis.paper import (
    load_paper_broker_runtime,
    load_paper_lifecycle_supervisor_target_specs,
    prepare_paper_broker_runtime_environment,
)

tfis_root = Path(sys.argv[2])
targets_config = Path(sys.argv[3])
prepared_providers = set()
for spec in load_paper_lifecycle_supervisor_target_specs(targets_config, repo_root=repo_root):
    runtime = load_paper_broker_runtime(spec.config_path)
    provider = runtime.config.broker.provider.strip().lower()
    if provider in prepared_providers:
        continue
    prepare_paper_broker_runtime_environment(
        runtime.config,
        tfis_root=tfis_root,
        skip_refresh=False,
    )
    print('Prepared TFIS broker runtime auth for provider=' + provider)
    prepared_providers.add(provider)
'@
    Write-Host "Preparing TFIS broker runtime auth once per configured provider."
    & $pythonExe -c $pythonCode $repoRoot $TfisRoot $targetsConfigPath
    if ($LASTEXITCODE -ne 0) {
        throw "TFIS broker runtime auth preparation failed with exit code $LASTEXITCODE."
    }
}

function Invoke-TfisMorningStartupWrappers {
    $wrapperPaths = @(Get-TfisMorningStartupWrapperPaths)
    if ($wrapperPaths.Count -eq 0) {
        throw "No TFIS morning startup wrappers configured in $TargetsConfig"
    }

    $script:MorningWrapperFailures = @()
    foreach ($wrapperPathText in $wrapperPaths) {
        $wrapperPath = Resolve-TfisPath ([string]$wrapperPathText)
        if (-not (Test-Path $wrapperPath)) {
            throw "Missing TFIS morning startup wrapper: $wrapperPath"
        }
        Write-Host "Starting TFIS morning wrapper with shared auth prepared: $wrapperPath"
        & powershell.exe `
            -NoProfile `
            -ExecutionPolicy Bypass `
            -File $wrapperPath `
            -TfisRoot $TfisRoot `
            -RunDate $RunDate `
            -SkipRefresh `
            -DisablePositionWatch
        if ($LASTEXITCODE -ne 0) {
            $script:MorningWrapperFailures += [PSCustomObject]@{
                Path = $wrapperPath
                ExitCode = $LASTEXITCODE
            }
            Write-Host "WARNING: TFIS morning startup wrapper failed with exit code $LASTEXITCODE`: $wrapperPath"
        }
    }
}

function Test-TfisMarketSessionActive {
    param([datetime]$Date)

    $effectiveDate = Get-TfisEffectiveRunDate -RunDate $Date
    $noRunReason = Get-TfisNoRunReason -RepoRoot $repoRoot -EffectiveDate $effectiveDate -CalendarPath $TradingHolidayCalendar
    if ($noRunReason) {
        return $false
    }

    $timeOfDay = $Date.TimeOfDay
    return (
        ($timeOfDay -ge ([TimeSpan]::Parse("09:15:00"))) -and
        ($timeOfDay -lt ([TimeSpan]::Parse("15:30:00")))
    )
}

$resetStopwatch = [System.Diagnostics.Stopwatch]::StartNew()

Write-Host "============================================================"
if ($MorningStartup) {
    Write-Host "TFIS APPLICATION MORNING STARTUP"
    Write-Host "This command prepares auth once, starts the dashboard, runs configured strategy wrappers, and starts one shared supervisor."
}
else {
    Write-Host "TFIS DASHBOARD/SUPERVISOR RESET"
    Write-Host "This command stops and restarts the TFIS paper runtime."
    Write-Host "Use scripts\refresh_tfis_operator_dashboard.ps1 when you only want a dashboard rebuild during market hours."
}
Write-Host "============================================================"

if ($MorningStartup) {
    $existingRuntime = @(Get-TfisRuntimeProcesses -RepoRoot $repoRoot)
    if ($existingRuntime.Count -gt 0) {
        Write-Host "Detected existing TFIS runtime process(es); morning startup will not stop them automatically."
        $existingRuntime | ForEach-Object {
            Write-Host "Existing TFIS process PID=$($_.ProcessId)"
        }
    }
}
else {
    if ((Test-TfisMarketSessionActive -Date $RunDate) -and (-not $ForceInMarketReset)) {
        throw (
            "Refusing full TFIS runtime reset during the active market session without -ForceInMarketReset. " +
            "Use scripts\refresh_tfis_operator_dashboard.ps1 for dashboard-only refresh, " +
            "or pass -ForceInMarketReset only for deliberate operator-approved recovery."
        )
    }
    Stop-TfisRuntimeProcesses -RepoRoot $repoRoot -CurrentProcessId $PID
    Write-Host ("Stopped prior TFIS runtime in {0:n1}s" -f $resetStopwatch.Elapsed.TotalSeconds)
}

if ($MorningStartup) {
    if ($SkipAuthPreparation) {
        Write-Host "Skipping TFIS application auth preparation by operator request."
    }
    else {
        Invoke-TfisRuntimeAuthPreparation
    }
}

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

$script:MorningWrapperFailures = @()
if ($MorningStartup) {
    Invoke-TfisMorningStartupWrappers
}

$supervisorProcess = Start-TfisPaperLifecycleSupervisorProcess `
    -RepoRoot $repoRoot `
    -TfisRoot $TfisRoot `
    -TargetsConfig (Resolve-TfisPath $TargetsConfig) `
    -DashboardOutputRoot $DashboardOutputRoot `
    -DashboardPort $DashboardPort `
    -SessionDate $RunDate `
    -SkipRefresh

Write-Host "Started shared TFIS paper lifecycle supervisor PID=$($supervisorProcess.Id)"
if ($script:MorningWrapperFailures.Count -gt 0) {
    foreach ($failure in $script:MorningWrapperFailures) {
        Write-Host "TFIS morning startup wrapper failure: exit_code=$($failure.ExitCode) path=$($failure.Path)"
    }
    throw "TFIS morning startup completed with $($script:MorningWrapperFailures.Count) failed wrapper(s); dashboard and shared supervisor startup were still attempted."
}
if ($MorningStartup) {
    Write-Host ("TFIS application morning startup complete in {0:n1}s." -f $resetStopwatch.Elapsed.TotalSeconds)
}
else {
    Write-Host ("TFIS dashboard/supervisor reset complete in {0:n1}s." -f $resetStopwatch.Elapsed.TotalSeconds)
}
