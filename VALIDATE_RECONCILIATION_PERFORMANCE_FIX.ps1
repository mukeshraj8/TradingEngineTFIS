$ErrorActionPreference = "Stop"

Write-Host "1. Syntax"
.\.venv\Scripts\python.exe -m py_compile `
  src\tfis\paper\runtime_reconciliation_status.py `
  src\tfis\paper\runtime_fresh_entry_handoff_status.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "2. Previously hanging S23 test"
Remove-Item -Recurse -Force .pytest_tmp\reconciliation_perf_single -ErrorAction SilentlyContinue
$sw = [System.Diagnostics.Stopwatch]::StartNew()
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_s23_live_decision_timeline.py::test_morning_supervised_runner_computes_but_blocks_fresh_order_when_position_open `
  --basetemp=.pytest_tmp\reconciliation_perf_single `
  -q
$sw.Stop()
Write-Host ("Elapsed: {0:N2} seconds" -f $sw.Elapsed.TotalSeconds)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "3. S23 shared-runtime guard"
Remove-Item -Recurse -Force .pytest_tmp\reconciliation_perf_guard -ErrorAction SilentlyContinue
$sw2 = [System.Diagnostics.Stopwatch]::StartNew()
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_s23_live_decision_builder.py `
  tests\unit\test_s23_live_decision_timeline.py `
  tests\unit\test_s23_paper_contract_selection.py `
  --basetemp=.pytest_tmp\reconciliation_perf_guard `
  -q
$sw2.Stop()
Write-Host ("Guard elapsed: {0:N2} seconds" -f $sw2.Elapsed.TotalSeconds)
exit $LASTEXITCODE
