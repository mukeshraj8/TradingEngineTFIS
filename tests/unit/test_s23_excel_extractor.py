from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from tfis.importers import S23ExcelExtractor


def _build_s23_workbook(path: Path) -> Path:
    workbook = Workbook()
    ab2 = workbook.active
    ab2.title = "AB2"
    ab2["B28"] = "S23"
    ab2["C28"] = "OPTIONS SELL"
    ab2["E28"] = "NIFTY"
    ab2["F28"] = "WEEKLY"
    ab2["H28"] = "DIFF"
    ab2["I28"] = "2D"
    ab2["J28"] = "3D"

    ab6 = workbook.create_sheet("AB6 OS")
    ab6["C163"] = "S23"
    ab6["C164"] = "NIFTY_OP_SELL_WK_DIFF_2D_3D"

    workbook.save(path)
    return path


def _build_manual_yaml(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "strategy_code: S23",
                "unique_code: NIFTY_OP_SELL_WK_DIFF_2D_3D",
                "symbol: NIFTY",
                "segment: OPTIONS_SELL",
                "allowed_monthly_statuses:",
                "  - BULL",
                "  - BULL_CF",
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
        encoding="utf-8",
    )
    return path


def test_s23_extractor_returns_normalized_candidate(tmp_path: Path) -> None:
    workbook_path = _build_s23_workbook(tmp_path / "s23.xlsx")

    candidate = S23ExcelExtractor(workbook_path).extract_candidate()

    assert candidate["strategy_code"] == "S23"
    assert candidate["unique_code"] == "NIFTY_OP_SELL_WK_DIFF_2D_3D"
    assert candidate["symbol"] == "NIFTY"
    assert candidate["segment"] == "OPTIONS_SELL"
    assert candidate["expiry_type"] == "WEEKLY"
    assert candidate["diff_basis"] == "DIFF"
    assert candidate["entry_window_basis"] == "2D"
    assert candidate["reference_window_basis"] == "3D"
    assert candidate["extraction_confidence"] == "medium"
    assert "start_strike_formula" in candidate["unresolved_fields"]
    assert len(candidate["source_anchors"]) == 6


def test_s23_extractor_comparison_marks_yaml_as_not_safe_yet(tmp_path: Path) -> None:
    workbook_path = _build_s23_workbook(tmp_path / "s23.xlsx")
    yaml_path = _build_manual_yaml(tmp_path / "S23.yaml")
    extractor = S23ExcelExtractor(workbook_path)

    comparison = extractor.compare_with_manual_yaml(yaml_path)

    assert comparison["matched_fields"]["strategy_code"]["candidate"] == "S23"
    assert comparison["matched_fields"]["segment"]["candidate"] == "OPTIONS_SELL"
    assert comparison["matched_fields"]["unique_code"]["candidate"] == "NIFTY_OP_SELL_WK_DIFF_2D_3D"
    assert "entry_time" in comparison["fields_present_only_in_manual_yaml"]
    assert "start_strike_formula" in comparison["fields_missing_from_excel_extraction"]
    assert comparison["recommendation"]["safe_to_generate_yaml"] is False


def test_s23_extractor_writes_comparison_markdown(tmp_path: Path) -> None:
    workbook_path = _build_s23_workbook(tmp_path / "s23.xlsx")
    yaml_path = _build_manual_yaml(tmp_path / "S23.yaml")
    extractor = S23ExcelExtractor(workbook_path)
    comparison_path = tmp_path / "comparison.md"

    comparison = extractor.compare_with_manual_yaml(yaml_path)
    extractor.write_comparison_markdown(comparison, comparison_path)

    text = comparison_path.read_text(encoding="utf-8")
    assert "safe_to_generate_yaml" in text
    assert "Fields Missing From Excel Extraction" in text
