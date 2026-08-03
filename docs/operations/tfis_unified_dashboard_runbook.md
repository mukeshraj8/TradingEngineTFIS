# TFIS Unified Internal-Paper Dashboard Runbook

## Scope

This runbook covers the local, read-only professional TFIS dashboard for the
unified S21/BANKNIFTY, S22/RELIANCE, and S23/NIFTY internal-paper projection.

External broker-order authority remains `NONE`.

## Build Certification Reports

```powershell
.\.venv\Scripts\python.exe scripts\run_tfis_internal_paper.py
```

Outputs are written under `reports/dashboard_v1/`.

## Build Dashboard

```powershell
.\.venv\Scripts\python.exe scripts\run_tfis_dashboard.py
```

The static dashboard is written to `tmp/tfis_dashboard_v1/index.html`.

To serve the dashboard and read-only backend APIs locally:

```powershell
.\.venv\Scripts\python.exe scripts\run_tfis_dashboard.py --serve --port 8766
```

Open `http://127.0.0.1:8766/index.html`.

This command is long-running. Start it from a separate operator terminal and
stop it with `Ctrl+C` when the dashboard review is complete. Automated Codex
validation must not leave this server running; use the bounded smoke helper
instead:

```powershell
.\.venv\Scripts\python.exe scripts\run_dashboard_v1_smoke.py
```

The smoke helper writes:

- `reports/dashboard_v1/dashboard_smoke_test.json`
- `reports/dashboard_v1/dashboard_process_cleanup.json`

## FYERS And Broker Diagnostics

Refresh or prepare the FYERS token from an operator shell:

```powershell
.\.venv\Scripts\python.exe scripts\fyers_token_refresh.py --prepare
```

Run read-only broker diagnostics:

```powershell
.\.venv\Scripts\python.exe scripts\run_broker_diagnostics.py --broker fyers
```

These commands do not grant broker order authority. Authentication/read health
and order-write authority remain separate checks.

## Graceful Shutdown And Port 8766 Troubleshooting

For a normally started operator dashboard, press `Ctrl+C` in the terminal that
is running `scripts/run_tfis_dashboard.py --serve --port 8766`.

If the port appears stale, identify the listener before stopping anything:

```powershell
Get-NetTCPConnection -LocalPort 8766 -State Listen -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'run_tfis_dashboard.py|tfis_dashboard_v1' } | Select-Object ProcessId,CommandLine
```

Stop only a confirmed TFIS dashboard process from this repository. Re-check the
port afterward:

```powershell
Get-NetTCPConnection -LocalPort 8766 -State Listen -ErrorAction SilentlyContinue
```

## Operating Boundaries

- The dashboard consumes read-model JSON only.
- The frontend contains no strategy formulas.
- The dashboard does not submit, modify, cancel, or square off broker orders.
- S22 RELIANCE live opening/ORPT/RC evidence remains pending and is displayed
  as degraded evidence quality until a real FYERS session is captured.

## Continuous Unified Supervisor

Preflight the next complete unified session:

```powershell
.\.venv\Scripts\python.exe scripts\run_tfis_internal_paper.py --preflight-complete-session
```

Run the continuous unified internal-paper supervisor in the foreground:

```powershell
.\.venv\Scripts\python.exe scripts\run_tfis_internal_paper.py --continuous-supervisor --poll-seconds 5 --dashboard-port 8766
```

Example operator background launch:

```powershell
$env:CONFIG_PROFILE='prod'
Start-Process -FilePath '.\.venv\Scripts\python.exe' `
  -ArgumentList @('-u','scripts/run_tfis_internal_paper.py','--continuous-supervisor','--poll-seconds','5','--dashboard-port','8766') `
  -WorkingDirectory 'D:\TradingEngineTFISRefactored' `
  -RedirectStandardOutput 'logs\live_supervisor\continuous_supervisor_stdout.log' `
  -RedirectStandardError 'logs\live_supervisor\continuous_supervisor_stderr.log' `
  -WindowStyle Hidden
```

Supervisor runtime files:

- `tmp/tfis_supervisor_state/heartbeat.json`
- `tmp/tfis_supervisor_state/continuous_unified_supervisor.pid.json`
- `tmp/tfis_supervisor_state/NSE_YYYY-MM-DD_UNIFIED_INTERNAL_PAPER.checkpoint.json`
- `tmp/tfis_dashboard_v1/api/snapshot.json`

Request a clean supervisor stop by creating the stop-signal file:

```powershell
New-Item -ItemType File -Force tmp\tfis_supervisor_state\continuous_unified_supervisor.stop
```

If the process is already stalled and the stop file does not complete the
shutdown, identify the exact repository-owned PID from
`tmp/tfis_supervisor_state/continuous_unified_supervisor.pid.json` and stop
only that TFIS supervisor process.
