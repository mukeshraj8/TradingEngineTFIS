$ErrorActionPreference = "Stop"

Write-Host "1. Syntax"
.\.venv\Scripts\python.exe -m py_compile `
  src\tfis\backtest\nifty_hsre_data_adapter.py `
  tests\unit\test_nifty_hsre_data_adapter.py `
  tests\integration\test_nifty_hsre_real_data.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "2. Focused provider unit tests"
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_nifty_hsre_data_adapter.py `
  -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "3. Optional real-data Jan-1 smoke"
.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_nifty_hsre_real_data.py `
  -q -s
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "4. Baseline regression comparison"
$baselineOutput = & .\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_historical_runner.py `
  tests\unit\test_option_chain_selection.py `
  tests\integration\test_historical_backtest_monthly_status_mode.py `
  tests\integration\test_historical_backtest_s23_recalculation_mode.py `
  tests\integration\test_contract_specific_lifecycle_mode.py `
  -q 2>&1
$baselineExit = $LASTEXITCODE
$baselineText = ($baselineOutput | Out-String)
Write-Host $baselineText

if ($baselineExit -eq 0) {
  Write-Host "Baseline suite unexpectedly passed. Review known-failure notes before proceeding."
  exit 0
}

if ($baselineText -notmatch "7 failed, 21 passed") {
  Write-Host "Baseline failure signature changed. Treat this as a possible regression."
  exit $baselineExit
}

Write-Host "Baseline suite preserved the known 7-failure drift."
exit 0
