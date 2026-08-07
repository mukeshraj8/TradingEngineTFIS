$ErrorActionPreference = "Stop"
$Repo = "D:\TradingEngineTFIS"
Set-Location $Repo

Write-Host "1. Syntax / focused S21 selection tests"
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_s21_all_branches.py `
  tests\unit\test_s23_paper_contract_selection.py `
  tests\unit\test_paper_runtime_strategy_trust_status.py `
  tests\unit\test_paper_morning_supervised_runtime.py `
  --basetemp=.pytest_tmp\s21_fix `
  -q

Write-Host "2. S21 / paper runtime regression slice"
.\.venv\Scripts\python.exe -m pytest `
  tests\unit -q `
  --basetemp=.pytest_tmp\s21_unit

Write-Host "3. Architecture + project validation"
.\.venv\Scripts\python.exe -m pytest tests\architecture -q --basetemp=.pytest_tmp\s21_arch
.\.venv\Scripts\python.exe scripts\validate_strategy_configs.py
.\.venv\Scripts\python.exe scripts\validate_project.py

git diff --check
