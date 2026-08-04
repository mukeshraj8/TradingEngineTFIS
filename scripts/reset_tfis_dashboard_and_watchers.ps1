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
    [switch]$RecoverSharedSupervisor,
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
    $matches = @(Get-TfisRuntimeProcesses -RepoRoot $repoRoot -RuntimePattern $pattern)
    if ($matches.Count -gt 0) {
        return $matches
    }
    return @(Get-TfisPortOwnerProcesses -Port $DashboardPort)
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
    connect_paper_broker_runtime,
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
    if provider not in prepared_providers:
        prepare_paper_broker_runtime_environment(
            runtime.config,
            tfis_root=tfis_root,
            skip_refresh=False,
        )
        print('Prepared TFIS broker runtime auth for provider=' + provider)
        prepared_providers.add(provider)
    try:
        health = connect_paper_broker_runtime(
            strategy_code=spec.strategy_code,
            provider=runtime.config.broker.provider,
            adapter=runtime.adapter,
        )
        print(
            'Confirmed TFIS broker runtime health for strategy='
            + spec.strategy_code
            + ' provider='
            + provider
            + ' state='
            + health.connection_state.value
        )
    finally:
        try:
            runtime.adapter.disconnect()
        except Exception:
            pass
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
    $wrapperProcesses = @()
    foreach ($wrapperPathText in $wrapperPaths) {
        $wrapperPath = Resolve-TfisPath ([string]$wrapperPathText)
        if (-not (Test-Path $wrapperPath)) {
            throw "Missing TFIS morning startup wrapper: $wrapperPath"
        }
        $wrapperArgs = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", $wrapperPath,
            "-TfisRoot", $TfisRoot,
            "-RunDate", $RunDate.ToString("o"),
            "-SkipRefresh",
            "-DisablePositionWatch"
        )
        Write-Host "Launching TFIS morning wrapper with shared auth prepared: $wrapperPath"
        $wrapperProcess = Start-Process `
            -FilePath "powershell.exe" `
            -ArgumentList $wrapperArgs `
            -WorkingDirectory $repoRoot `
            -PassThru `
            -WindowStyle Normal
        $wrapperProcesses += [PSCustomObject]@{
            Path = $wrapperPath
            Process = $wrapperProcess
        }
        Write-Host "Started TFIS morning wrapper PID=$($wrapperProcess.Id) path=$wrapperPath"
    }

    foreach ($wrapperLaunch in $wrapperProcesses) {
        $wrapperProcess = $wrapperLaunch.Process
        $wrapperPath = $wrapperLaunch.Path
        Write-Host "Waiting for TFIS morning wrapper PID=$($wrapperProcess.Id) path=$wrapperPath"
        $wrapperProcess.WaitForExit()
        if ($wrapperProcess.ExitCode -ne 0) {
            $script:MorningWrapperFailures += [PSCustomObject]@{
                Path = $wrapperPath
                ExitCode = $wrapperProcess.ExitCode
            }
            Write-Host "WARNING: TFIS morning startup wrapper failed with exit code $($wrapperProcess.ExitCode): $wrapperPath"
        }
        else {
            Write-Host "TFIS morning wrapper completed successfully: $wrapperPath"
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

function Assert-TfisStatusScriptPass {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptRelativePath,
        [Parameter(Mandatory = $true)]
        [string]$StatusLabel
    )

    $scriptPath = Resolve-TfisPath $ScriptRelativePath
    if (-not (Test-Path $scriptPath)) {
        throw "Missing TFIS recovery safety script: $scriptPath"
    }
    $lines = @(& $pythonExe $scriptPath 2>$null)
    if ($LASTEXITCODE -ne 0) {
        throw "TFIS supervisor recovery safety check failed: $StatusLabel exited with code $LASTEXITCODE."
    }
    $failures = @($lines | Where-Object { $_ -match "status=FAIL" })
    if ($failures.Count -gt 0) {
        throw "TFIS supervisor recovery is not safe: $StatusLabel reported failure: $($failures -join '; ')"
    }
    Write-Host "TFIS supervisor recovery safety check passed: $StatusLabel"
}

function Invoke-TfisSharedSupervisorRecovery {
    if (-not (Test-TfisMarketSessionActive -Date $RunDate)) {
        throw (
            "Shared-supervisor-only recovery is intended for active market recovery. " +
            "Use -MorningStartup before market, or the normal reset path outside market hours."
        )
    }

    $runtimeProcesses = @(Get-TfisRuntimeProcesses -RepoRoot $repoRoot)
    $logicalRuntimeProcesses = @(Get-TfisLogicalRuntimeProcesses -Processes $runtimeProcesses)
    $supervisorProcesses = @($logicalRuntimeProcesses | Where-Object { $_.Role -eq "supervisor" })
    if ($supervisorProcesses.Count -gt 0) {
        throw "Refusing supervisor recovery because a shared supervisor already appears to be running."
    }

    $unsafeProcesses = @(
        $logicalRuntimeProcesses |
        Where-Object { $_.Role -in @("morning_strategy", "runtime_startup", "runtime_stop", "position_watcher") }
    )
    if ($unsafeProcesses.Count -gt 0) {
        $unsafeText = @(
            $unsafeProcesses |
            ForEach-Object { "role=$($_.Role) pids=$($_.ProcessIds -join ',')" }
        )
        throw "Refusing supervisor recovery while other runtime launch/recovery work is active: $($unsafeText -join '; ')"
    }

    Assert-TfisStatusScriptPass -ScriptRelativePath "scripts/show_paper_runtime_guardrail_status.py" -StatusLabel "PaperGuardrails"
    Assert-TfisStatusScriptPass -ScriptRelativePath "scripts/show_paper_runtime_waiting_order_status.py" -StatusLabel "WaitingOrders"
    Assert-TfisStatusScriptPass -ScriptRelativePath "scripts/show_paper_runtime_reconciliation_status.py" -StatusLabel "RuntimeReconciliation"
    Assert-TfisStatusScriptPass -ScriptRelativePath "scripts/show_paper_runtime_order_routing_status.py" -StatusLabel "OrderRoutingSafety"

    $supervisorProcess = Start-TfisPaperLifecycleSupervisorProcess `
        -RepoRoot $repoRoot `
        -TfisRoot $TfisRoot `
        -TargetsConfig (Resolve-TfisPath $TargetsConfig) `
        -DashboardOutputRoot $DashboardOutputRoot `
        -DashboardPort $DashboardPort `
        -SessionDate $RunDate `
        -DisableDashboardRebuild `
        -SkipRefresh

    Write-Host "Started shared TFIS paper lifecycle supervisor recovery PID=$($supervisorProcess.Id)"
}

$resetStopwatch = [System.Diagnostics.Stopwatch]::StartNew()

Write-Host "============================================================"
if ($MorningStartup) {
    Write-Host "TFIS APPLICATION MORNING STARTUP"
    Write-Host "This command prepares auth once, starts the dashboard, runs configured strategy wrappers, and starts one shared supervisor."
}
elseif ($RecoverSharedSupervisor) {
    Write-Host "TFIS SHARED SUPERVISOR RECOVERY"
    Write-Host "This command performs an active-market safety check and starts only the shared supervisor."
}
else {
    Write-Host "TFIS DASHBOARD/SUPERVISOR RESET"
    Write-Host "This command stops and restarts the TFIS paper runtime."
    Write-Host "Use scripts\refresh_tfis_operator_dashboard.ps1 when you only want a dashboard rebuild during market hours."
}
Write-Host "============================================================"

if ($RecoverSharedSupervisor) {
    Invoke-TfisSharedSupervisorRecovery
    Write-Host ("TFIS shared supervisor recovery complete in {0:n1}s." -f $resetStopwatch.Elapsed.TotalSeconds)
    exit 0
}

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
