from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.replay.s21_replay import run_s21_replay


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pure deterministic S21 replay from a sealed evidence JSON file."
    )
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    decision = run_s21_replay(
        evidence_path=args.evidence,
        output_dir=args.output_dir,
    )
    print(
        f"{decision.session_date}: monthly_status={decision.monthly_status}; "
        f"evidence_complete={decision.evidence_complete}"
    )
    for leg in decision.legs:
        print(
            f"  {leg.unique_code}: verdict={leg.verdict}; "
            f"contract={leg.selected_contract}; entry={leg.entry}; "
            f"ORPT={leg.orpt_status}; RC={leg.rc_status}"
        )
    if not decision.evidence_complete:
        print("Evidence gaps:")
        for gap in decision.evidence_gaps:
            print(f"  - {gap}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
