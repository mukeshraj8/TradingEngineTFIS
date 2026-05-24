from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from tfis.importers.s23_formula_block_discovery import S23FormulaBlockDiscovery


def _build_discovery_workbook(path: Path) -> Path:
    workbook = Workbook()
    ab6 = workbook.active
    ab6.title = "AB6 OS"
    ab6["C163"] = "S23"
    ab6["C164"] = "NIFTY_OP_SELL_WK_DIFF_2D_3D"
    ab6["D162"] = "BULL / BULL CF"
    ab6["F162"] = "Call"
    ab6["G162"] = "( SPT : PRV : 3DLL + 5.00% ) & Round Down"
    ab6["G163"] = "( SPT : PRV : 3DLL ) & Round Down - 1"
    ab6["H162"] = "SPT : PRV : 3DLL * 1.20%"
    ab6["H163"] = "SPT : PRV : 3DLL * 0.90%"
    ab6["I162"] = "500 Lots"
    ab6["M162"] = "OPT : PRV : 3DLL - 7.50%"
    ab6["O162"] = "CE : Entry  - 60.00%"
    ab6["M163"] = "Min ( CE : Entry  + 60.00% & OPT : PRV : 2DHH + 7.00% )"
    ab6["H160"] = "Yes"
    ab6["L175"] = "09:24:59"
    ab6["C176"] = "09:29:59"

    for sheet_name, coord_a, coord_b in (
        ("AB14", "E48", "E49"),
        ("AB15", "C13", "G13"),
        ("AB16", "E102", "E105"),
    ):
        sheet = workbook.create_sheet(sheet_name)
        sheet[coord_a] = "S23"
        sheet[coord_b] = "NIFTY_OP_SELL_WK_DIFF_2D_3D"

    workbook.save(path)
    return path


def test_s23_formula_discovery_collects_candidates_and_tags(tmp_path: Path) -> None:
    workbook_path = _build_discovery_workbook(tmp_path / "s23_discovery.xlsx")

    discovery = S23FormulaBlockDiscovery(workbook_path).discover()

    ab6_cells = discovery["sheets"]["AB6 OS"]["nearby_cells"]
    assert any(cell["coordinate"] == "G162" for cell in ab6_cells)
    assert any("START_STRIKE" in cell["tags"] for cell in ab6_cells if cell["coordinate"] == "G162") is False

    start_strike = discovery["field_candidates"]["start_strike_formula"]
    assert start_strike["confidence"] == "high"
    assert start_strike["candidate_cells"][0]["coordinate"] == "G162"

    entry_time = discovery["field_candidates"]["entry_time"]
    assert any(cell["coordinate"] == "L175" for cell in entry_time["candidate_cells"])
    assert discovery["field_candidates"]["carry_forward_allowed"]["confidence"] == "medium"


def test_s23_formula_discovery_writes_markdown(tmp_path: Path) -> None:
    workbook_path = _build_discovery_workbook(tmp_path / "s23_discovery.xlsx")
    markdown_path = tmp_path / "S23_formula_block_discovery.md"

    discovery = S23FormulaBlockDiscovery(workbook_path).discover()
    S23FormulaBlockDiscovery.write_markdown(discovery, markdown_path)

    text = markdown_path.read_text(encoding="utf-8")
    assert "Field Candidates" in text
    assert "safe_to_generate_yaml" not in text
    assert "start_strike_formula" in text
