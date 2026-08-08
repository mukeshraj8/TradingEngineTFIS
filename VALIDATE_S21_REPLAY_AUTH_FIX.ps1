$ErrorActionPreference = "Stop"

.\.venv\Scripts\python.exe -m py_compile scripts\run_s21_historical_replay.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

.\.venv\Scripts\python.exe scripts\run_s21_historical_replay.py --help | Out-Null
exit $LASTEXITCODE
