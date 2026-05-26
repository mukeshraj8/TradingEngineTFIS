from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "backtest"
DAILY_MULTI_CSV = FIXTURES / "s23_daily_multi.csv"
OPTION_MULTI_CSV = FIXTURES / "s23_option_levels_multi.csv"
OPTION_INTRADAY_CSV = FIXTURES / "s23_option_intraday.csv"
OPTION_CHAIN_CSV = FIXTURES / "s23_option_chain.csv"
CONTRACT_INTRADAY_CSV = FIXTURES / "s23_contract_intraday.csv"
MONTHLY_CSV = FIXTURES / "s23_monthly.csv"
WEEKLY_CSV = FIXTURES / "s23_weekly.csv"
STRATEGY_ROOT = "config/strategies/options_sell/nifty"


def _output_path(name: str) -> Path:
    output_dir = ROOT / "tmp"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / name


def _env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath = str(ROOT / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = pythonpath if not existing else f"{pythonpath}{os.pathsep}{existing}"
    return env


def _run_contract_specific_backtest(
    *,
    enable_contract_specific_lifecycle: bool,
    output_name: str,
) -> dict[str, object]:
    output_path = _output_path(output_name)
    command = [
        sys.executable,
        "scripts/run_backtest.py",
        "--strategy-root",
        STRATEGY_ROOT,
        "--use-monthly-status-engine",
        "--monthly-csv",
        str(MONTHLY_CSV),
        "--weekly-csv",
        str(WEEKLY_CSV),
        "--daily-csv",
        str(DAILY_MULTI_CSV),
        "--option-levels-csv",
        str(OPTION_MULTI_CSV),
        "--option-intraday-csv",
        str(OPTION_INTRADAY_CSV),
        "--option-chain-csv",
        str(OPTION_CHAIN_CSV),
        "--enable-option-chain-selection",
        "--historical",
        "--eod-policy",
        "square_off_at_close",
        "--out",
        str(output_path),
    ]
    if enable_contract_specific_lifecycle:
        command.extend(
            [
                "--enable-s23-recalculation",
                "--contract-intraday-csv",
                str(CONTRACT_INTRADAY_CSV),
                "--enable-contract-specific-lifecycle",
            ]
        )

    result = subprocess.run(
        command,
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(output_path.read_text(encoding="utf-8"))


def test_default_behavior_is_unchanged_without_contract_specific_flag(
) -> None:
    report = _run_contract_specific_backtest(
        enable_contract_specific_lifecycle=False,
        output_name="historical_contract_specific_default.json",
    )

    assert "enable_contract_specific_lifecycle" not in report
    first_eval = report["evaluations"][0]
    assert "contract_specific_lifecycle" not in first_eval["validation"]


def test_contract_specific_lifecycle_uses_selected_contract_series_when_available(
) -> None:
    report = _run_contract_specific_backtest(
        enable_contract_specific_lifecycle=True,
        output_name="historical_contract_specific_enabled.json",
    )

    evaluation = next(
        item
        for item in report["evaluations"]
        if item["validation"]["option_chain_selection"]["selected_contract"]["symbol"]
        == "NIFTY_20260528_22100_CE"
        and item["validation"]["contract_specific_lifecycle"]["lifecycle_price_source"]
        == "contract_specific_series"
    )
    audit = evaluation["validation"]["contract_specific_lifecycle"]

    assert report["enable_contract_specific_lifecycle"] is True
    assert audit["selected_contract_symbol"] == "NIFTY_20260528_22100_CE"
    assert audit["lifecycle_price_source"] == "contract_specific_series"
    assert audit["warning"] is None


def test_contract_specific_lifecycle_falls_back_to_generic_series_with_warning(
) -> None:
    report = _run_contract_specific_backtest(
        enable_contract_specific_lifecycle=True,
        output_name="historical_contract_specific_fallback.json",
    )

    evaluation = next(
        item
        for item in report["evaluations"]
        if item["validation"]["option_chain_selection"]["selected_contract"]["symbol"]
        == "NIFTY_20260528_22300_PE"
    )
    audit = evaluation["validation"]["contract_specific_lifecycle"]

    assert audit["lifecycle_price_source"] == "generic_option_series"
    assert "fell back to generic option intraday series" in audit["warning"]
