from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = ROOT / "scripts" / "validate_strategy_configs.py"


def _load_validator_module():
    spec = importlib.util.spec_from_file_location("tfis_validate_strategy_configs", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load validate_strategy_configs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_valid_folder_strategy(base_dir: Path) -> Path:
    strategy_file = base_dir / "strategy.yaml"
    _write(
        strategy_file,
        "\n".join(
            [
                "strategy_code: S23",
                "unique_code: NIFTY_OP_SELL_WK_DIFF_2D_3D",
                "symbol: NIFTY",
                "segment: OPTIONS_SELL",
                "expiry_type: WEEKLY",
                "rollover_policy: T_MINUS_1",
                "no_carry_past_expiry: true",
                "allowed_monthly_statuses:",
                "  - BULL",
                "option_type: CALL",
                'entry_time: "09:24:59"',
                'recalculation_time: "09:29:59"',
                "minimum_oi: 500",
                "carry_forward_allowed: true",
            ]
        ),
    )
    _write(
        base_dir / "formulas.yaml",
        "\n".join(
            [
                'start_strike_formula: "ROUND_DOWN(PRV_3DLL + PARAM(strike_buffer_pct)%)"',
                'end_strike_formula: "ROUND_DOWN(PRV_3DLL) - PARAM(strike_step)"',
                'ideal_premium_formula: "PRV_3DLL * PARAM(ideal_premium_pct)%"',
                'minimum_premium_formula: "PRV_3DLL * PARAM(minimum_premium_pct)%"',
                'entry_formula: "OPT_PRV_3DLL - PARAM(entry_discount_pct)%"',
                'target_formula: "ENTRY - PARAM(target_pct)%"',
                'stoploss_formula: "MIN(ENTRY + PARAM(sl_entry_pct)%, OPT_PRV_2DHH + PARAM(sl_reference_pct)%)"',
            ]
        ),
    )
    _write(
        base_dir / "parameters.yaml",
        "\n".join(
            [
                "strike_buffer_pct: 1.2",
                "strike_step: 50.0",
                "ideal_premium_pct: 1.2",
                "minimum_premium_pct: 0.9",
                "entry_discount_pct: 7.5",
                "target_pct: 60.0",
                "sl_entry_pct: 60.0",
                "sl_reference_pct: 7.0",
            ]
        ),
    )
    _write(base_dir / "notes.md", "# Notes\n")
    _write(
        base_dir / "excel_crosscheck.yaml",
        "\n".join(
            [
                "strategy_code: S23",
                "unique_code: NIFTY_OP_SELL_WK_DIFF_2D_3D",
                "source_sheet: AB6 OS",
                "source_branch: Bull/Bull CF Call",
                "source_cells:",
                "  start_strike_formula: G162",
                "sample_calculation:",
                "  expected:",
                "    ideal_premium: 264",
            ]
        ),
    )
    return strategy_file


def test_valid_folder_strategy_with_crosscheck_passes(tmp_path: Path) -> None:
    validator = _load_validator_module()
    strategy_file = _build_valid_folder_strategy(tmp_path / "S23")

    ok, message = validator.validate_folder_strategy(strategy_file)

    assert ok is True
    assert message == ""


def test_missing_excel_crosscheck_fails(tmp_path: Path) -> None:
    validator = _load_validator_module()
    strategy_file = _build_valid_folder_strategy(tmp_path / "S23")
    (strategy_file.parent / "excel_crosscheck.yaml").unlink()

    ok, message = validator.validate_folder_strategy(strategy_file)

    assert ok is False
    assert "missing required files: excel_crosscheck.yaml" == message


def test_missing_formulas_yaml_fails(tmp_path: Path) -> None:
    validator = _load_validator_module()
    strategy_file = _build_valid_folder_strategy(tmp_path / "S23")
    (strategy_file.parent / "formulas.yaml").unlink()

    ok, message = validator.validate_folder_strategy(strategy_file)

    assert ok is False
    assert "missing required files: formulas.yaml" == message


def test_legacy_yaml_still_allowed_and_identified(tmp_path: Path) -> None:
    validator = _load_validator_module()
    legacy_file = tmp_path / "legacy" / "S23.yaml"
    _write(
        legacy_file,
        "\n".join(
            [
                "strategy_code: S23",
                "unique_code: NIFTY_OP_SELL_WK_DIFF_2D_3D",
                "symbol: NIFTY",
                "segment: OPTIONS_SELL",
                "expiry_type: WEEKLY",
                "rollover_policy: T_MINUS_1",
                "no_carry_past_expiry: true",
                "allowed_monthly_statuses:",
                "  - BULL",
                "option_type: CALL",
                'entry_time: "09:24:59"',
                'recalculation_time: "09:29:59"',
                'start_strike_formula: "ROUND_DOWN(PRV_3DLL + 5%)"',
                'end_strike_formula: "ROUND_DOWN(PRV_3DLL) - 1"',
                'ideal_premium_formula: "PRV_3DLL + 1.20%"',
                'minimum_premium_formula: "PRV_3DLL + 0.90%"',
                'entry_formula: "PRV_3DLL - 7.50%"',
                'target_formula: "ENTRY - 60%"',
                'stoploss_formula: "MIN(ENTRY + 60%, PRV_2DHH + 7%)"',
                "minimum_oi: 500",
                "carry_forward_allowed: true",
            ]
        ),
    )

    ok, message = validator.validate_legacy_strategy(legacy_file)

    assert ok is True
    assert message == ""
