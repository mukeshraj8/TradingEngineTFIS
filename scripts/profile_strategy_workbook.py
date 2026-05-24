from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tfis.importers import ExcelWorkbookProfiler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only profiler for TFIS strategy workbooks."
    )
    parser.add_argument("--workbook", required=True, help="Path to the input workbook")
    parser.add_argument("--out", required=True, help="Path to write the profile JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workbook_path = Path(args.workbook)
    out_path = Path(args.out)

    if not workbook_path.exists():
        print(f"Workbook not found: {workbook_path}")
        print(
            "See docs/importer_input_instructions.md for where to place the TFIS workbook."
        )
        return 1

    profiler = ExcelWorkbookProfiler(workbook_path)
    profile = profiler.profile()
    written = profiler.write_json(profile, out_path)

    print(f"Workbook: {workbook_path}")
    print(f"Sheets: {len(profile['sheet_names'])}")
    for sheet in profile["sheets"]:
        print(
            f"- {sheet['name']}: rows={sheet['row_count']} cols={sheet['column_count']} "
            f"non_empty={sheet['non_empty_cell_count']} "
            f"strategy_hits={len(sheet['likely_strategy_code_locations'])} "
            f"unique_code_hits={len(sheet['likely_unique_code_locations'])}"
        )
    print(f"Profile written to: {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
