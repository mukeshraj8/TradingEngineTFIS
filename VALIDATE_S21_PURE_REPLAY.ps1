$ErrorActionPreference = "Stop"

Write-Host "1. Syntax"
.\.venv\Scripts\python.exe -m py_compile `
  src\tfis\strategy_engine\s21.py `
  src\tfis\replay\s21_evidence.py `
  src\tfis\replay\s21_replay.py `
  scripts\build_s21_replay_evidence.py `
  scripts\run_s21_historical_replay.py `
  scripts\collect_s21_replay_option_evidence.py `
  tests\unit\test_s21_pure_strategy_engine.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "2. Pure strategy engine tests"
Remove-Item -Recurse -Force .pytest_tmp\s21_pure_replay -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_s21_pure_strategy_engine.py `
  --basetemp=.pytest_tmp\s21_pure_replay `
  -q
exit $LASTEXITCODE
