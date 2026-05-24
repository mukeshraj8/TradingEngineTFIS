from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from tfis.importers import ExcelWorkbookProfiler, profile_workbook


def test_excel_workbook_profiler_reports_structure_and_hits(tmp_path: Path) -> None:
    workbook_path = tmp_path / "tfis_profile_input.xlsx"
    out_path = tmp_path / "workbook_profile.json"

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Strategies"
    sheet["A1"] = "Strategy Code"
    sheet["B1"] = "Unique Code"
    sheet["A2"] = "S23"
    sheet["B2"] = "NIFTY_OP_SELL_WK_DIFF_2D_3D"
    sheet["C2"] = 500
    second = workbook.create_sheet("Notes")
    second["A1"] = "S24"
    workbook.save(workbook_path)

    profile = profile_workbook(workbook_path, out_path)

    assert profile["sheet_names"] == ["Strategies", "Notes"]
    strategies = profile["sheets"][0]
    assert strategies["row_count"] >= 2
    assert strategies["column_count"] >= 3
    assert strategies["non_empty_cell_count"] == 5
    assert strategies["likely_strategy_code_locations"] == [
        {"cell": "A2", "value": "S23"}
    ]
    assert strategies["likely_unique_code_locations"] == [
        {"cell": "B2", "value": "NIFTY_OP_SELL_WK_DIFF_2D_3D"}
    ]
    assert out_path.exists()


def test_excel_workbook_profiler_raises_for_missing_workbook(tmp_path: Path) -> None:
    profiler = ExcelWorkbookProfiler(tmp_path / "missing.xlsx")

    try:
        profiler.profile()
    except FileNotFoundError as exc:
        assert "Workbook not found" in str(exc)
    else:
        raise AssertionError("Expected FileNotFoundError for missing workbook")
