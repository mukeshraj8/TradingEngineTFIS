$ErrorActionPreference = "Stop"

.\.venv\Scripts\python.exe -m py_compile src\tfis\replay\s21_evidence.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

.\.venv\Scripts\python.exe scripts\build_s21_replay_evidence.py `
  --certification-root reports\s21_certification_input `
  --session-date 2026-08-06 `
  --output reports\s21_replay_evidence\2026-08-06\s21_replay_evidence.json

exit $LASTEXITCODE
