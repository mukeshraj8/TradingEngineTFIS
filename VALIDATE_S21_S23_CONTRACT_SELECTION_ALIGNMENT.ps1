$ErrorActionPreference = "Stop"

Write-Host "1. Syntax"
.\.venv\Scripts\python.exe -m py_compile `
  src\tfis\strategy_engine\s21.py `
  src\tfis\paper\s21_live_decision.py `
  src\tfis\replay\s21_replay.py `
  tests\unit\test_s21_contract_selection_s23_alignment.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "2. S21 contract-selection alignment tests"
Remove-Item -Recurse -Force .pytest_tmp\s21_s23_selection -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_s21_contract_selection_s23_alignment.py `
  tests\unit\test_s21_workbook_certified_rules.py `
  tests\unit\test_s21_all_branches.py `
  --basetemp=.pytest_tmp\s21_s23_selection `
  -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "3. S23 non-regression: business selector tests only"
Remove-Item -Recurse -Force .pytest_tmp\s21_s23_selection_guard -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_s23_paper_contract_selection.py `
  --basetemp=.pytest_tmp\s21_s23_selection_guard `
  -q
exit $LASTEXITCODE
