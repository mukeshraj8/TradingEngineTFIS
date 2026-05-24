from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tfis.backtest import (
    ParameterSweepTradeOutputs,
    ParameterSweepVariantResult,
    build_parameter_sweep_ranking,
    calculate_risk_reward_metrics,
)


ROOT = Path(__file__).resolve().parents[2]


def _variant(
    *,
    variant_id: str,
    accepted: bool,
    rejection_reason: str | None,
    entry_price: float,
    stoploss_price: float,
    target_price: float,
) -> ParameterSweepVariantResult:
    trade_outputs = ParameterSweepTradeOutputs(
        start_strike=23100,
        entry_price=entry_price,
        target_price=target_price,
        stoploss_price=stoploss_price,
        ideal_premium=264.0,
        minimum_premium=198.0,
    )
    risk_distance, reward_distance, reward_risk_ratio = calculate_risk_reward_metrics(
        trade_outputs
    )
    return ParameterSweepVariantResult(
        variant_id=variant_id,
        parameters={"target_pct": 60.0},
        success=True,
        error=None,
        result=None,
        metrics=None,
        accepted=accepted,
        rejection_reason=rejection_reason,
        trade_outputs=trade_outputs,
        risk_distance=risk_distance,
        reward_distance=reward_distance,
        reward_risk_ratio=reward_risk_ratio,
    )


def test_reward_risk_metrics_are_computed() -> None:
    trade_outputs = ParameterSweepTradeOutputs(
        start_strike=23100,
        entry_price=203.5,
        target_price=80.0,
        stoploss_price=320.0,
        ideal_premium=264.0,
        minimum_premium=198.0,
    )

    risk_distance, reward_distance, reward_risk_ratio = calculate_risk_reward_metrics(
        trade_outputs
    )

    assert risk_distance == pytest.approx(116.5)
    assert reward_distance == pytest.approx(123.5)
    assert reward_risk_ratio == pytest.approx(123.5 / 116.5)


def test_ranking_prefers_accepted_variants() -> None:
    ranking = build_parameter_sweep_ranking(
        [
            _variant(
                variant_id="variant_rejected",
                accepted=False,
                rejection_reason="Rejected: max_trades_per_day reached",
                entry_price=203.5,
                stoploss_price=220.0,
                target_price=100.0,
            ),
            _variant(
                variant_id="variant_accepted",
                accepted=True,
                rejection_reason=None,
                entry_price=203.5,
                stoploss_price=320.0,
                target_price=80.0,
            ),
        ]
    )

    assert ranking[0].variant_id == "variant_accepted"
    assert ranking[1].variant_id == "variant_rejected"


def test_parameter_sweep_script_writes_markdown_and_valid_json(tmp_path: Path) -> None:
    json_path = tmp_path / "parameter_sweep.json"
    markdown_path = tmp_path / "parameter_sweep.md"
    env = os.environ.copy()
    pythonpath = str(ROOT / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = pythonpath if not existing else f"{pythonpath}{os.pathsep}{existing}"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_parameter_sweep.py",
            "--experiment",
            "config/experiments/S23_parameter_sweep.yaml",
            "--out",
            str(json_path),
            "--markdown-out",
            str(markdown_path),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")

    assert report["summary"]["total_variants"] == 18
    assert "ranking" in report
    assert report["ranking"][0]["rank"] == 1
    assert report["variants"][0]["trade_outputs"]["entry_price"] == pytest.approx(203.5)
    assert "# Parameter Sweep Summary" in markdown
    assert "## Top 10 Ranked Variants" in markdown
