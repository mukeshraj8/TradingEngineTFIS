param(
    [string]$TfisRoot,
    [int]$DashboardPort = 8765,
    [switch]$RequireToken,
    [datetime]$RunDate = (Get-Date),
    [string]$TradingHolidayCalendar = "config/nse_trading_holidays_2026.json"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$runtimeProcessHelperPath = Join-Path $scriptDir "tfis_runtime_process_helpers.ps1"
$operatorControlHelperPath = Join-Path $scriptDir "tfis_operator_control_helpers.ps1"
$tradingCalendarHelperPath = Join-Path $scriptDir "tfis_trading_calendar_helpers.ps1"
. $runtimeProcessHelperPath
. $operatorControlHelperPath
. $tradingCalendarHelperPath

if (-not $TfisRoot) {
    $TfisRoot = $repoRoot
}

Set-Location $repoRoot
$Host.UI.RawUI.WindowTitle = "TFIS Runtime Status"

function Test-TfisDashboardPortReady {
    param(
        [int]$Port,
        [int]$TimeoutMilliseconds = 500
    )

    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        try {
            $asyncResult = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
            if ($asyncResult.AsyncWaitHandle.WaitOne($TimeoutMilliseconds) -and $client.Connected) {
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
    return $false
}

function Get-TfisRestartRecoveryStatus {
    param(
        [bool]$DashboardReady,
        [int]$DashboardProcessCount,
        [int]$SupervisorProcessCount,
        [int]$OtherProcessCount,
        [bool]$WaitingOrderFailure,
        [string]$MarketSessionPhase
    )

    $pending = @()
    if ($WaitingOrderFailure) {
        $pending += "resolve_stale_waiting_orders"
    }
    if (-not $DashboardReady) {
        $pending += "start_or_recover_dashboard"
    }
    if ($SupervisorProcessCount -eq 0) {
        if ($MarketSessionPhase -eq "ACTIVE_MARKET") {
            $pending += "start_shared_supervisor"
        }
        elseif ($MarketSessionPhase -eq "PRE_MARKET") {
            $pending += "run_morning_startup"
        }
    }
    if (($DashboardProcessCount -eq 0) -and ($SupervisorProcessCount -eq 0) -and ($OtherProcessCount -eq 0) -and (-not $DashboardReady)) {
        if ($MarketSessionPhase -eq "PRE_MARKET") {
            $status = "READY_FOR_MORNING_STARTUP"
            $pending = @("run_morning_startup")
            $message = "TFIS appears stopped before market; run reset_tfis_dashboard_and_watchers.ps1 -MorningStartup for the scheduled app startup path."
        }
        elseif ($MarketSessionPhase -eq "ACTIVE_MARKET") {
            $status = "ACTION_REQUIRED"
            $pending = @("start_or_recover_dashboard", "start_shared_supervisor")
            $message = "TFIS appears stopped during active market; operator recovery is required."
        }
        else {
            $status = "STOPPED_AFTER_MARKET"
            $pending = @("none")
            $message = "TFIS appears stopped outside active market hours; no same-day supervisor restart is required."
        }
    }
    elseif ($pending.Count -gt 0) {
        $status = "ACTION_REQUIRED"
        $message = "TFIS runtime is partially available; review pending action(s): $($pending -join ', ')."
    }
    elseif (($MarketSessionPhase -eq "POST_MARKET") -and ($SupervisorProcessCount -eq 0)) {
        $status = "AFTER_MARKET_IDLE"
        $pending = @("none")
        $message = "Market lifecycle window has ended; dashboard/status may remain available and no shared supervisor restart is required."
    }
    else {
        $status = "RUNNING"
        $pending = @("none")
        $message = "Dashboard and shared supervisor are visible, and no stale waiting-order recovery action is pending."
    }

    return [PSCustomObject]@{
        Status = $status
        PendingActions = $pending
        Message = $message
    }
}

function Get-TfisMarketSessionPhase {
    param([datetime]$Date)

    $effectiveDate = Get-TfisEffectiveRunDate -RunDate $Date
    $noRunReason = Get-TfisNoRunReason -RepoRoot $repoRoot -EffectiveDate $effectiveDate -CalendarPath $TradingHolidayCalendar
    if ($noRunReason) {
        return "CLOSED_DAY"
    }

    $timeOfDay = $Date.TimeOfDay
    if ($timeOfDay -lt ([TimeSpan]::Parse("09:15:00"))) {
        return "PRE_MARKET"
    }
    if ($timeOfDay -lt ([TimeSpan]::Parse("15:30:00"))) {
        return "ACTIVE_MARKET"
    }
    return "POST_MARKET"
}

Write-Host "============================================"
Write-Host "TFIS RUNTIME STATUS"
Write-Host "This window belongs to TradingEngineTFIS only."
Write-Host "============================================"

$controlRoot = Resolve-TfisOperatorControlRoot -RepoRoot $repoRoot
$globalPausePath = Get-TfisGlobalPauseMarkerPath -RepoRoot $repoRoot
$pausedStrategies = @(
    Get-ChildItem -Path $controlRoot -Filter "strategy_*.pause.json" -ErrorAction SilentlyContinue |
    ForEach-Object { $_.BaseName -replace '^strategy_', '' -replace '\.pause$', '' } |
    Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
    Sort-Object -Unique
)
$latestEvent = Get-TfisLatestOperatorControlEvent -RepoRoot $repoRoot
$runtimeProcesses = @(Get-TfisRuntimeProcesses -RepoRoot $repoRoot)
$dashboardProcesses = @($runtimeProcesses | Where-Object { $_.CommandLine -match "serve_operator_dashboard\.py" })
$supervisorProcesses = @($runtimeProcesses | Where-Object { $_.CommandLine -match "run_tfis_paper_lifecycle_supervisor\.py|start_tfis_paper_lifecycle_supervisor\.ps1" })
$otherProcesses = @(
    $runtimeProcesses | Where-Object {
        $_.CommandLine -notmatch "serve_operator_dashboard\.py" -and
        $_.CommandLine -notmatch "run_tfis_paper_lifecycle_supervisor\.py|start_tfis_paper_lifecycle_supervisor\.ps1"
    }
)
$dashboardReady = Test-TfisDashboardPortReady -Port $DashboardPort
$marketSessionPhase = Get-TfisMarketSessionPhase -Date $RunDate

Write-Host "RepoRoot: $repoRoot"
Write-Host "TfisRoot: $TfisRoot"
Write-Host "MarketSessionPhase: $marketSessionPhase"
Write-Host "GlobalPause: $(if (Test-Path $globalPausePath) { 'YES' } else { 'NO' })"
Write-Host "PausedStrategies: $(if ($pausedStrategies.Count -gt 0) { $pausedStrategies -join ', ' } else { 'none' })"
Write-Host "DashboardPortReady: $(if ($dashboardReady) { 'YES' } else { 'NO' })"

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$guardrailScript = Join-Path $scriptDir "show_paper_runtime_guardrail_status.py"
$brokerHealthScript = Join-Path $scriptDir "show_paper_runtime_broker_health_status.py"
$heartbeatScript = Join-Path $scriptDir "show_paper_runtime_heartbeat_status.py"
$lifecycleAuditScript = Join-Path $scriptDir "show_paper_runtime_lifecycle_audit_status.py"
$waitingOrderScript = Join-Path $scriptDir "show_paper_runtime_waiting_order_status.py"
$orderRoutingScript = Join-Path $scriptDir "show_paper_runtime_order_routing_status.py"
$reconciliationScript = Join-Path $scriptDir "show_paper_runtime_reconciliation_status.py"
$freshEntryHandoffScript = Join-Path $scriptDir "show_paper_runtime_fresh_entry_handoff_status.py"
$waitingOrderLines = @()
if ((Test-Path $pythonExe) -and (Test-Path $guardrailScript)) {
    try {
        $guardrailLines = & $pythonExe $guardrailScript 2>$null
        if ($guardrailLines) {
            Write-Host "PaperGuardrails:"
            foreach ($line in $guardrailLines) {
                if (-not [string]::IsNullOrWhiteSpace($line)) {
                    Write-Host (" - {0}" -f $line)
                }
            }
        }
    }
    catch {
        Write-Host "PaperGuardrails: unavailable"
    }
}
else {
    Write-Host "PaperGuardrails: unavailable"
}
if ((Test-Path $pythonExe) -and (Test-Path $brokerHealthScript)) {
    try {
        $brokerHealthArgs = @($brokerHealthScript)
        if ($RequireToken) {
            $brokerHealthArgs += "--require-token"
        }
        $brokerHealthLines = & $pythonExe $brokerHealthArgs 2>$null
        if ($brokerHealthLines) {
            Write-Host "BrokerHealth:"
            foreach ($line in $brokerHealthLines) {
                if (-not [string]::IsNullOrWhiteSpace($line)) {
                    Write-Host (" - {0}" -f $line)
                }
            }
        }
    }
    catch {
        Write-Host "BrokerHealth: unavailable"
    }
}
else {
    Write-Host "BrokerHealth: unavailable"
}
if ((Test-Path $pythonExe) -and (Test-Path $heartbeatScript)) {
    try {
        $heartbeatLines = & $pythonExe $heartbeatScript 2>$null
        if ($heartbeatLines) {
            Write-Host "RuntimeHeartbeats:"
            foreach ($line in $heartbeatLines) {
                if (-not [string]::IsNullOrWhiteSpace($line)) {
                    Write-Host (" - {0}" -f $line)
                }
            }
        }
    }
    catch {
        Write-Host "RuntimeHeartbeats: unavailable"
    }
}
else {
    Write-Host "RuntimeHeartbeats: unavailable"
}

if ((Test-Path $pythonExe) -and (Test-Path $lifecycleAuditScript)) {
    try {
        $lifecycleAuditArgs = @($lifecycleAuditScript)
        if ($marketSessionPhase -ne "ACTIVE_MARKET") {
            $lifecycleAuditArgs += @("--stale-after-seconds", "86400")
        }
        $lifecycleAuditLines = & $pythonExe $lifecycleAuditArgs 2>$null
        if ($lifecycleAuditLines) {
            Write-Host "LifecycleAudit:"
            foreach ($line in $lifecycleAuditLines) {
                if (-not [string]::IsNullOrWhiteSpace($line)) {
                    Write-Host (" - {0}" -f $line)
                }
            }
        }
    }
    catch {
        Write-Host "LifecycleAudit: unavailable"
    }
}
else {
    Write-Host "LifecycleAudit: unavailable"
}

if ((Test-Path $pythonExe) -and (Test-Path $waitingOrderScript)) {
    try {
        $waitingOrderLines = & $pythonExe $waitingOrderScript 2>$null
        if ($waitingOrderLines) {
            Write-Host "WaitingOrders:"
            foreach ($line in $waitingOrderLines) {
                if (-not [string]::IsNullOrWhiteSpace($line)) {
                    Write-Host (" - {0}" -f $line)
                }
            }
        }
    }
    catch {
        Write-Host "WaitingOrders: unavailable"
    }
}
else {
    Write-Host "WaitingOrders: unavailable"
}

$waitingOrderFailure = @($waitingOrderLines | Where-Object { $_ -match "status=FAIL" }).Count -gt 0
$restartRecoveryStatus = Get-TfisRestartRecoveryStatus `
    -DashboardReady:$dashboardReady `
    -DashboardProcessCount $dashboardProcesses.Count `
    -SupervisorProcessCount $supervisorProcesses.Count `
    -OtherProcessCount $otherProcesses.Count `
    -WaitingOrderFailure:$waitingOrderFailure `
    -MarketSessionPhase $marketSessionPhase
Write-Host ("RestartRecoveryStatus: status={0} pending={1} message={2}" -f `
    $restartRecoveryStatus.Status, `
    ($restartRecoveryStatus.PendingActions -join ","), `
    $restartRecoveryStatus.Message)

if ((Test-Path $pythonExe) -and (Test-Path $orderRoutingScript)) {
    try {
        $routingLines = & $pythonExe $orderRoutingScript 2>$null
        if ($routingLines) {
            Write-Host "OrderRoutingSafety:"
            foreach ($line in $routingLines) {
                if (-not [string]::IsNullOrWhiteSpace($line)) {
                    Write-Host (" - {0}" -f $line)
                }
            }
        }
    }
    catch {
        Write-Host "OrderRoutingSafety: unavailable"
    }
}
else {
    Write-Host "OrderRoutingSafety: unavailable"
}

if ((Test-Path $pythonExe) -and (Test-Path $reconciliationScript)) {
    try {
        $reconciliationLines = & $pythonExe $reconciliationScript 2>$null
        if ($reconciliationLines) {
            Write-Host "RuntimeReconciliation:"
            foreach ($line in $reconciliationLines) {
                if (-not [string]::IsNullOrWhiteSpace($line)) {
                    Write-Host (" - {0}" -f $line)
                }
            }
        }
    }
    catch {
        Write-Host "RuntimeReconciliation: unavailable"
    }
}
else {
    Write-Host "RuntimeReconciliation: unavailable"
}

if ((Test-Path $pythonExe) -and (Test-Path $freshEntryHandoffScript)) {
    try {
        $freshEntryLines = & $pythonExe $freshEntryHandoffScript 2>$null
        if ($freshEntryLines) {
            Write-Host "FreshEntryHandoffs:"
            foreach ($line in $freshEntryLines) {
                if (-not [string]::IsNullOrWhiteSpace($line)) {
                    Write-Host (" - {0}" -f $line)
                }
            }
        }
    }
    catch {
        Write-Host "FreshEntryHandoffs: unavailable"
    }
}
else {
    Write-Host "FreshEntryHandoffs: unavailable"
}

if ($null -ne $latestEvent) {
    $latestControlParts = @(
        "$($latestEvent.action)",
        "scope=$($latestEvent.scope)",
        "strategy=$(if ($latestEvent.strategy_code) { $latestEvent.strategy_code } else { 'ALL' })",
        "at=$($latestEvent.occurred_at)",
        "actor=$(if ($latestEvent.actor) { $latestEvent.actor } else { 'unknown' })",
        "reason=$(if ($latestEvent.reason) { $latestEvent.reason } else { 'n/a' })",
        "marker=$(if ($latestEvent.marker_path) { $latestEvent.marker_path } else { 'n/a' })"
    )
    Write-Host "LatestControlEvent: $($latestControlParts -join ' ')"
}
else {
    Write-Host "LatestControlEvent: none"
}

Write-Host "RuntimeProcesses: $($runtimeProcesses.Count)"
Write-Host "DashboardProcesses: $($dashboardProcesses.Count)"
Write-Host "SupervisorProcesses: $($supervisorProcesses.Count)"
Write-Host "OtherTfisProcesses: $($otherProcesses.Count)"
foreach ($proc in $runtimeProcesses) {
    Write-Host (" - PID={0} Name={1}" -f $proc.ProcessId, $proc.Name)
}
