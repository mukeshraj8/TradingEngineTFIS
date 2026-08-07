$ErrorActionPreference = "Stop"

Write-Host "1. S23 startup/regression guard (must remain green)"
Remove-Item -Recurse -Force .pytest_tmp\s21_safe_s23_guard -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_s23_live_decision_builder.py `
  tests\unit\test_s23_live_decision_timeline.py `
  tests\unit\test_s23_paper_contract_selection.py `
  tests\unit\test_s23_live_decision_task.py `
  tests\unit\test_s23_supervised_decision_process_lock.py `
  --basetemp=.pytest_tmp\s21_safe_s23_guard `
  -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "2. S21 rule/config guard"
Remove-Item -Recurse -Force .pytest_tmp\s21_safe_rules -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_s21_all_branches.py `
  tests\unit\test_paper_runtime_strategy_trust_status.py `
  tests\unit\test_paper_morning_supervised_runtime.py `
  --basetemp=.pytest_tmp\s21_safe_rules `
  -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "3. Syntax"
.\.venv\Scripts\python.exe -m py_compile `
  src\tfis\paper\s21_live_decision.py `
  src\tfis\paper\live_decision_timeline_runner.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "S21 SAFE ISOLATED PATCH VALIDATION PASSED"
