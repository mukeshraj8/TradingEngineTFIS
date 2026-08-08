$ErrorActionPreference = "Stop"

Write-Host "1. S23 shared runtime non-regression guard"
Remove-Item -Recurse -Force .pytest_tmp\s21_single_s23 -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_s23_live_decision_builder.py `
  tests\unit\test_s23_live_decision_timeline.py `
  tests\unit\test_s23_paper_contract_selection.py `
  --basetemp=.pytest_tmp\s21_single_s23 `
  -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "2. S21 strategy-session policy + rule validation"
Remove-Item -Recurse -Force .pytest_tmp\s21_single -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_s21_strategy_session.py `
  tests\unit\test_s21_all_branches.py `
  tests\unit\test_paper_runtime_strategy_trust_status.py `
  --basetemp=.pytest_tmp\s21_single `
  -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "3. S21 startup script syntax/help"
.\.venv\Scripts\python.exe -m py_compile `
  src\tfis\paper\s21_live_decision.py `
  src\tfis\paper\s21_strategy_session.py `
  scripts\run_s21_banknifty_0916_supervised_decision.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

.\.venv\Scripts\python.exe scripts\run_s21_banknifty_0916_supervised_decision.py --help | Out-Null
exit $LASTEXITCODE
