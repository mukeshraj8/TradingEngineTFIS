from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_s23_tradingengine_capture_ingress_suite.py"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "paper" / "tradingengine_capture_adapter"
CONTEXT_SESSION_DIR = FIXTURE_ROOT / "context_session"
OPTION_QUOTES_CSV = FIXTURE_ROOT / "NIFTY50_option_quotes_20260527.csv"


def _build_tradingdata_root(tmp_path: Path) -> Path:
    tradingdata_root = tmp_path / "TradingData"
    context_target = (
        tradingdata_root
        / "captures"
        / "context_sessions"
        / "2026-05-27"
        / CONTEXT_SESSION_DIR.name
    )
    context_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(CONTEXT_SESSION_DIR, context_target)

    option_target = (
        tradingdata_root
        / "data"
        / "nifty"
        / "20260527"
        / "options"
        / "index"
    )
    option_target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OPTION_QUOTES_CSV, option_target / OPTION_QUOTES_CSV.name)
    return tradingdata_root


def test_capture_ingress_suite_cli_writes_aggregate_outputs(tmp_path: Path) -> None:
    tradingdata_root = _build_tradingdata_root(tmp_path)
    out_root = tmp_path / "suite_out"
    out_json = tmp_path / "suite_summary.json"
    out_md = tmp_path / "suite_summary.md"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--data-root",
            str(tradingdata_root),
            "--dates",
            "2026-05-27",
            "--out-root",
            str(out_root),
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert out_json.exists()
    assert out_md.exists()
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["pass_count"] == 1
    assert payload["rollout_recommendation"] == "GO_FOR_CONTROLLED_PAPER"
