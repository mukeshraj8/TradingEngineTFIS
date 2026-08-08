$ErrorActionPreference = "Stop"

Write-Host "1. Syntax"
.\.venv\Scripts\python.exe -m py_compile `
  src\tfis\strategy_engine\s21.py `
  src\tfis\paper\s21_live_decision.py `
  src\tfis\paper\s21_strategy_session.py `
  tests\unit\test_s21_workbook_certified_rules.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "2. Workbook-certified S21 tests"
Remove-Item -Recurse -Force .pytest_tmp\s21_workbook_certified -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_s21_workbook_certified_rules.py `
  tests\unit\test_s21_all_branches.py `
  tests\unit\test_paper_runtime_strategy_trust_status.py `
  --basetemp=.pytest_tmp\s21_workbook_certified `
  -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "3. S23 shared-runtime non-regression guard"
Remove-Item -Recurse -Force .pytest_tmp\s21_workbook_s23_guard -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_s23_live_decision_builder.py `
  tests\unit\test_s23_live_decision_timeline.py `
  tests\unit\test_s23_paper_contract_selection.py `
  --basetemp=.pytest_tmp\s21_workbook_s23_guard `
  -q
exit $LASTEXITCODE
