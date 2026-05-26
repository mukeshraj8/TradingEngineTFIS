from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "report_comparison"


def _load_compare_script_module():
    script_path = ROOT / "scripts" / "compare_backtest_reports.py"
    spec = importlib.util.spec_from_file_location("compare_backtest_reports_script", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load compare_backtest_reports.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compare_backtest_reports_cli_uses_small_fixture_reports() -> None:
    out_path = Path("D:/TradingEngineProd/tmp_pytest_compare/comparison.json")
    markdown_path = Path("D:/TradingEngineProd/tmp_pytest_compare/comparison.md")

    module = _load_compare_script_module()
    argv = [
        "compare_backtest_reports.py",
        "--report",
        f"base={FIXTURES / 'base.json'}",
        "--report",
        f"option_chain={FIXTURES / 'advanced.json'}",
        "--max-trades",
        "2",
        "--timeout-seconds",
        "5",
        "--out",
        str(out_path),
        "--markdown-out",
        str(markdown_path),
    ]
    written: dict[str, str] = {}

    def _capture_write_text(self: Path, data: str, encoding: str | None = None) -> int:
        written[str(self)] = data
        return len(data)

    with patch("sys.argv", argv):
        with patch.object(Path, "mkdir", return_value=None):
            with patch.object(Path, "write_text", new=_capture_write_text):
                assert module.main() == 0

    payload = json.loads(written[str(out_path)])
    assert payload["baseline_label"] == "base"
    assert payload["apples_to_apples"] is True
    assert payload["reports"][1]["enable_option_chain_selection"] is True
    assert payload["comparisons"][0]["label"] == "option_chain"
    assert written[str(markdown_path)].startswith("# S23 Backtest Mode Comparison")
