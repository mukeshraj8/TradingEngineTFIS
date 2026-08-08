$ErrorActionPreference = "Stop"

Write-Host "1. Syntax"
.\.venv\Scripts\python.exe -m py_compile scripts\explain_s21_contract_selection.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "2. Explain certified Aug-04..Aug-07 decisions"
.\.venv\Scripts\python.exe scripts\explain_s21_contract_selection.py `
  --dates 2026-08-04 2026-08-05 2026-08-06 2026-08-07
exit $LASTEXITCODE
