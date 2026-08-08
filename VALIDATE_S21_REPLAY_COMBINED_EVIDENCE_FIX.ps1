$ErrorActionPreference = "Stop"

Write-Host "1. Syntax"
.\.venv\Scripts\python.exe -m py_compile `
  src\tfis\replay\s21_evidence.py `
  src\tfis\strategy_engine\s21.py `
  scripts\collect_s21_replay_option_evidence.py `
  scripts\build_s21_failed_evidence_manifest.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "2. Rebuild August 6 sealed evidence with collected option facts"
.\.venv\Scripts\python.exe scripts\build_s21_replay_evidence.py `
  --certification-root reports\s21_certification_input `
  --session-date 2026-08-06 `
  --output reports\s21_replay_evidence\2026-08-06\s21_replay_evidence.json `
  --option-evidence-dir reports\s21_replay_option_evidence\2026-08-06

exit $LASTEXITCODE
