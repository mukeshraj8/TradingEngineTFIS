from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "convert_tradingengine_capture_to_tfis_ingress.py"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "paper" / "tradingengine_capture_adapter"


def test_converter_cli_writes_audit_and_market_events(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.json"
    output_path = tmp_path / "market_events.jsonl"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--context-session-dir",
            str(FIXTURE_ROOT / "context_session"),
            "--option-quotes-csv",
            str(FIXTURE_ROOT / "NIFTY50_option_quotes_20260527.csv"),
            "--selected-contract-symbol",
            "NSE:NIFTY2660223200CE",
            "--audit-json",
            str(audit_path),
            "--output-jsonl",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert audit_path.exists()
    assert output_path.exists()
    audit_payload = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit_payload["recommendation"] == "usable"
    lines = [line for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 6
