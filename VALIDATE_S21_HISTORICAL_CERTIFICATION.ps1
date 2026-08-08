$ErrorActionPreference = "Stop"

Write-Host "1. Syntax"
.\.venv\Scripts\python.exe -m py_compile scripts\run_s21_historical_certification.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "2. One-day cached-evidence smoke: 2026-08-04"
.\.venv\Scripts\python.exe scripts\run_s21_historical_certification.py `
  --start-date 2026-08-04 `
  --end-date 2026-08-04 `
  --max-days 1
exit $LASTEXITCODE
