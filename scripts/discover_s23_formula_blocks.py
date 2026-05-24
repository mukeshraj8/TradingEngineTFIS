from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tfis.importers.s23_formula_block_discovery import S23FormulaBlockDiscovery


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only discovery of S23 formula blocks in the TFIS workbook."
    )
    parser.add_argument("--workbook", required=True, help="Path to the TFIS workbook")
    parser.add_argument(
        "--strategy-code",
        default="S23",
        help="Strategy code to inspect. Only S23 is supported in this discovery tool.",
    )
    parser.add_argument("--out", required=True, help="Path for JSON discovery output")
    parser.add_argument(
        "--markdown-out",
        required=True,
        help="Path for markdown discovery output",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.strategy_code.upper() != "S23":
        parser.error("This discovery tool currently supports only --strategy-code S23")

    discovery = S23FormulaBlockDiscovery(Path(args.workbook), strategy_code="S23").discover()
    S23FormulaBlockDiscovery.write_json(discovery, args.out)
    S23FormulaBlockDiscovery.write_markdown(discovery, args.markdown_out)

    print(f"Discovery JSON written to {Path(args.out)}")
    print(f"Discovery markdown written to {Path(args.markdown_out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
