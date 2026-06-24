from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tfis.importers import load_strategy_rule  # noqa: E402
from tfis.rules import S23_LEG_RULES, validate_s23_strategy_rule_matches_matrix  # noqa: E402


STRATEGY_ROOT = ROOT / "config" / "strategies" / "options_sell" / "nifty"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate configured S23 strategy folders against the corrected rule-sheet matrix."
    )
    parser.add_argument(
        "--strategy-root",
        type=Path,
        default=STRATEGY_ROOT,
        help="Directory containing S23 strategy folders.",
    )
    args = parser.parse_args()

    failures: list[str] = []
    for unique_code in sorted(S23_LEG_RULES):
        folder = args.strategy_root / f"S23_{unique_code}"
        if unique_code == "NIFTY_OP_SELL_WK_DIFF_2D_3D":
            folder = args.strategy_root / unique_code.replace(
                "NIFTY_OP_SELL_WK_DIFF_2D_3D",
                "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
            )
        if not folder.exists():
            failures.append(f"{unique_code}: missing folder {folder}")
            continue
        rule = load_strategy_rule(folder)
        mismatches = validate_s23_strategy_rule_matches_matrix(rule)
        if mismatches:
            failures.append(f"{unique_code}: " + "; ".join(mismatches))
        else:
            print(f"OK {unique_code}")

    if failures:
        print("S23 rule matrix validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("S23 rule matrix validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
