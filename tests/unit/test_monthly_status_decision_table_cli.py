from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _run_cli(tmp_path: Path, *, include_markdown: bool) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    json_output = tmp_path / "monthly_status_decision_table.json"
    markdown_output = tmp_path / "monthly_status_decision_table.md"
    env = os.environ.copy()
    pythonpath = str(ROOT / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = pythonpath if not existing else f"{pythonpath}{os.pathsep}{existing}"

    command = [
        sys.executable,
        "scripts/run_monthly_status_decision_table.py",
        "--instrument-group",
        "nifty",
        "--pmh",
        "100",
        "--pml",
        "90",
        "--cmh",
        "102",
        "--cml",
        "91",
        "--pwh",
        "101",
        "--pwl",
        "92",
        "--cwh",
        "102",
        "--cwl",
        "93",
        "--current-price",
        "103",
        "--out",
        str(json_output),
    ]
    if include_markdown:
        command.extend(["--markdown-out", str(markdown_output)])

    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, json_output, markdown_output


def test_cli_creates_json_and_candidate_rows(tmp_path: Path) -> None:
    result, json_output, _ = _run_cli(tmp_path, include_markdown=False)

    assert result.returncode == 0, result.stdout + result.stderr
    assert json_output.is_file()

    report = json.loads(json_output.read_text(encoding="utf-8"))
    assert report["instrument_group"] == "nifty"
    assert report["thresholds"]["a_pct"] == 0.75

    trigger_names = {candidate["trigger_name"] for candidate in report["candidates"]}
    assert "BULL_A_THRESHOLD" in trigger_names
    assert "BEAR_A_THRESHOLD" in trigger_names
    assert "REVERSAL_BULL_C_THRESHOLD" in trigger_names
    assert "REVERSAL_BEAR_C_THRESHOLD" in trigger_names


def test_cli_optionally_creates_markdown(tmp_path: Path) -> None:
    result, _, markdown_output = _run_cli(tmp_path, include_markdown=True)

    assert result.returncode == 0, result.stdout + result.stderr
    assert markdown_output.is_file()

    markdown = markdown_output.read_text(encoding="utf-8")
    assert "Monthly Status Decision Table" in markdown
    assert "This is diagnostic only and does not select final monthly status." in markdown
    assert "BULL_A_THRESHOLD" in markdown
    assert "REVERSAL_BEAR_C_THRESHOLD" in markdown


def test_missing_bullish_and_bearish_values_create_unresolved_rows(tmp_path: Path) -> None:
    result, json_output, _ = _run_cli(tmp_path, include_markdown=False)

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(json_output.read_text(encoding="utf-8"))
    candidates = {candidate["trigger_name"]: candidate for candidate in report["candidates"]}

    assert candidates["BULL_CF_B_THRESHOLD"]["condition_met"] is None
    assert candidates["BULL_CF_B_THRESHOLD"]["threshold_value"] is None
    assert candidates["BULL_CF_B_THRESHOLD"]["confidence"] == "LOW"
    assert candidates["BEAR_CF_B_THRESHOLD"]["condition_met"] is None
    assert candidates["BEAR_CF_B_THRESHOLD"]["threshold_value"] is None
    assert candidates["BEAR_CF_B_THRESHOLD"]["confidence"] == "LOW"
