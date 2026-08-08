$ErrorActionPreference = "Stop"

Write-Host "1. Syntax"
.\.venv\Scripts\python.exe -m py_compile `
  scripts\collect_s21_replay_option_evidence.py `
  scripts\certify_s21_entry_distance.py `
  scripts\run_s21_historical_certification.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "2. Aug-04 full-session cache + offline certification smoke"
.\.venv\Scripts\python.exe scripts\run_s21_historical_certification.py `
  --start-date 2026-08-04 `
  --end-date 2026-08-04 `
  --max-days 1
exit $LASTEXITCODE
