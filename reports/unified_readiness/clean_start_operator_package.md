# Clean-Start Operator Package

- Captured At: `2026-08-04T12:24:26.134392+05:30`
- Authoritative Readiness Verdict: `NO_GO_FOR_NEXT_COMPLETE_UNIFIED_SESSION`
- External Broker Order Authority: `NONE`

## Commands

1. `refresh_fyers_token`
   - Command: `.\.venv\Scripts\python.exe scripts\fyers_token_refresh.py --prepare`
   - Expect: Token/session prepared for read-only diagnostics.
2. `run_broker_diagnostics`
   - Command: `.\.venv\Scripts\python.exe scripts\run_broker_diagnostics.py --broker fyers`
   - Expect: authentication_status=AUTHENTICATED and order_write_status=NOT_AUTHORIZED
3. `graceful_stop_existing_supervisor_if_active`
   - Command: `New-Item -ItemType File -Force tmp\tfis_supervisor_state\continuous_unified_supervisor.stop`
   - Expect: Existing late-start supervisor shuts down cleanly and the active lock clears.
4. `run_complete_session_preflight`
   - Command: `.\.venv\Scripts\python.exe scripts\run_tfis_internal_paper.py --preflight-complete-session`
   - Expect: READY_FOR_COMPLETE_UNIFIED_SESSION
5. `start_unified_supervisor`
   - Command: `.\.venv\Scripts\python.exe scripts\run_tfis_internal_paper.py --continuous-supervisor --poll-seconds 5 --dashboard-port 8766`
   - Expect: Fresh before-market-open unified supervisor session starts on the optimized path.
6. `start_dashboard`
   - Command: `.\.venv\Scripts\python.exe scripts\run_tfis_dashboard.py --serve --port 8766`
   - Expect: Local read-only dashboard available at http://127.0.0.1:8766/index.html

## Must Verify

- `reports/unified_readiness/authoritative_readiness_projection.json`
- `reports/live_supervisor/complete_session_preflight.json`
- `tmp/tfis_supervisor_state/heartbeat.json`
- `tmp/tfis_dashboard_v1/api/snapshot.json`
