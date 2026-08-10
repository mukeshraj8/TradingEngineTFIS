$ErrorActionPreference = "Stop"

$env:PYTHONPATH = "src"

Write-Host "== HSRE M5 S23 JAN 2024 validation =="

Write-Host "== Syntax checks =="
.\.venv\Scripts\python.exe -m py_compile `
  src\tfis\backtest\hsre_s23_month_run.py `
  scripts\run_hsre_s23_january_2024.py `
  tests\integration\test_hsre_s23_january_2024_real_data.py

Write-Host "== Focused S23 authority / recalculation / paper parity tests =="
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_s23_entry_missed.py `
  tests\unit\test_s23_live_decision_builder.py `
  tests\unit\test_s23_recalculation.py `
  -q

Write-Host "== HSRE M4 Jan-3 lifecycle regression =="
.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_hsre_s23_trade_lifecycle_real_data.py `
  -q -s

Write-Host "== HSRE M5 January regression =="
.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_hsre_s23_january_2024_real_data.py `
  -q -s

Write-Host "== Generate authoritative January 2024 report =="
.\.venv\Scripts\python.exe scripts\run_hsre_s23_january_2024.py `
  --data-root D:\HistoricalData\Nifty `
  --output-dir reports\hsre\S23\2024-01

Write-Host "== Determinism re-run and hash comparison =="
$checkDir = "reports\hsre\S23\2024-01_determinism_check"
.\.venv\Scripts\python.exe scripts\run_hsre_s23_january_2024.py `
  --data-root D:\HistoricalData\Nifty `
  --output-dir $checkDir

$primary = Get-Content reports\hsre\S23\2024-01\summary.json | ConvertFrom-Json
$repeat = Get-Content "$checkDir\summary.json" | ConvertFrom-Json
$names = @(
  "daily_decisions.csv",
  "trades.csv",
  "non_trades.csv",
  "rejected_candidates_summary.csv",
  "entry_distance.csv"
)

foreach ($name in $names) {
  $left = $primary.hashes.PSObject.Properties[$name].Value
  $right = $repeat.hashes.PSObject.Properties[$name].Value
  if ($left -ne $right) {
    throw "Determinism hash mismatch for $name : $left != $right"
  }
}

Write-Host "== M5 validation complete =="
Write-Host "Observed trading days:" $primary.date_coverage.observed_trading_days
Write-Host "Final orders ready:" $primary.funnel.final_orders_ready
Write-Host "Entries triggered:" $primary.trade_metrics.entries_triggered
Write-Host "Net point P&L:" $primary.trade_metrics.net_total_points
Write-Host "Rupee P&L status:" $primary.rupee_pnl_status
