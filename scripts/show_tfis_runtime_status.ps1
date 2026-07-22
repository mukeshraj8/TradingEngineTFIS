param(
    [string]$TfisRoot,
    [int]$DashboardPort = 8765,
    [switch]$RequireToken
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$runtimeProcessHelperPath = Join-Path $scriptDir "tfis_runtime_process_helpers.ps1"
$operatorControlHelperPath = Join-Path $scriptDir "tfis_operator_control_helpers.ps1"
. $runtimeProcessHelperPath
. $operatorControlHelperPath

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

Write-Host "RepoRoot: $repoRoot"
Write-Host "TfisRoot: $TfisRoot"
Write-Host "GlobalPause: $(if (Test-Path $globalPausePath) { 'YES' } else { 'NO' })"
Write-Host "PausedStrategies: $(if ($pausedStrategies.Count -gt 0) { $pausedStrategies -join ', ' } else { 'none' })"
Write-Host "DashboardPortReady: $(if (Test-TfisDashboardPortReady -Port $DashboardPort) { 'YES' } else { 'NO' })"

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$guardrailScript = Join-Path $scriptDir "show_paper_runtime_guardrail_status.py"
$brokerHealthScript = Join-Path $scriptDir "show_paper_runtime_broker_health_status.py"
$heartbeatScript = Join-Path $scriptDir "show_paper_runtime_heartbeat_status.py"
$orderRoutingScript = Join-Path $scriptDir "show_paper_runtime_order_routing_status.py"
$reconciliationScript = Join-Path $scriptDir "show_paper_runtime_reconciliation_status.py"
$freshEntryHandoffScript = Join-Path $scriptDir "show_paper_runtime_fresh_entry_handoff_status.py"
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
    Write-Host "LatestControlEvent: $($latestEvent.action) scope=$($latestEvent.scope) strategy=$($latestEvent.strategy_code) at=$($latestEvent.occurred_at)"
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
