from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_validate_strategy_configs_script_passes_for_current_configs() -> None:
    env = os.environ.copy()
    pythonpath = str(ROOT / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = pythonpath if not existing else f"{pythonpath}{os.pathsep}{existing}"

    result = subprocess.run(
        [sys.executable, "scripts/validate_strategy_configs.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "LEGACY PASS config\\strategies\\legacy\\S23_NIFTY_OP_SELL_WK_DIFF_2D_3D.yaml" in result.stdout
    assert (
        "PASS config\\strategies\\options_sell\\nifty\\S23_NIFTY_OP_SELL_WK_DIFF_2D_3D\\strategy.yaml"
        in result.stdout
    )
    assert (
        "PASS config\\strategies\\options_sell\\nifty\\S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT\\strategy.yaml"
        in result.stdout
    )
    assert (
        "PASS config\\strategies\\options_sell\\nifty\\S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL\\strategy.yaml"
        in result.stdout
    )
    assert (
        "PASS config\\strategies\\options_sell\\nifty\\S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT\\strategy.yaml"
        in result.stdout
    )
