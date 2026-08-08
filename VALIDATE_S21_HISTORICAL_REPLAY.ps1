$ErrorActionPreference = "Stop"

Write-Host "1. Syntax"
.\.venv\Scripts\python.exe -m py_compile `
  src\tfis\replay\s21_replay.py `
  scripts\run_s21_historical_replay.py `
  tests\unit\test_s21_historical_replay.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "2. Pure S21 replay tests"
Remove-Item -Recurse -Force .pytest_tmp\s21_replay -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_s21_historical_replay.py `
  --basetemp=.pytest_tmp\s21_replay `
  -q
exit $LASTEXITCODE
