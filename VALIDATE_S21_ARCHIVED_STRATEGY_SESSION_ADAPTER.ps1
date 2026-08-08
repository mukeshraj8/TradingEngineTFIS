$ErrorActionPreference = "Stop"

Write-Host "1. Syntax"
.\.venv\Scripts\python.exe -m py_compile `
  src\tfis\replay\s21_archived_session.py `
  scripts\prepare_s21_archived_strategy_sessions.py `
  scripts\run_s21_archived_strategy_session_certification.py `
  tests\unit\test_s21_archived_strategy_session_adapter.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "2. Adapter unit tests"
Remove-Item -Recurse -Force .pytest_tmp\s21_archived_adapter -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_s21_archived_strategy_session_adapter.py `
  --basetemp=.pytest_tmp\s21_archived_adapter `
  -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "3. Discover real durable S21 sessions (read-only)"
.\.venv\Scripts\python.exe scripts\prepare_s21_archived_strategy_sessions.py `
  --index-only
exit $LASTEXITCODE
