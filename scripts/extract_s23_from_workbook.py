from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tfis.importers import S23ExcelExtractor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only S23 extractor for the TFIS workbook."
    )
    parser.add_argument("--workbook", required=True, help="Path to the TFIS workbook")
    parser.add_argument(
        "--strategy-code",
        default="S23",
        help="Strategy code to inspect. Only S23 is supported in this prototype.",
    )
    parser.add_argument("--out", required=True, help="Path for candidate JSON output")
    parser.add_argument(
        "--comparison-out",
        required=True,
        help="Path for markdown comparison output",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.strategy_code.upper() != "S23":
        parser.error("This prototype currently supports only --strategy-code S23")

    extractor = S23ExcelExtractor(Path(args.workbook), strategy_code="S23")
    candidate = extractor.extract_candidate()
    comparison = extractor.compare_with_manual_yaml(
        PROJECT_ROOT / "config" / "strategies" / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D.yaml"
    )

    extractor.write_json(candidate, args.out)
    extractor.write_comparison_markdown(comparison, args.comparison_out)

    print(f"Candidate written to {Path(args.out)}")
    print(f"Comparison written to {Path(args.comparison_out)}")
    print(
        "safe_to_generate_yaml="
        f"{str(comparison['recommendation']['safe_to_generate_yaml']).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
