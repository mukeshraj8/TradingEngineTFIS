from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tfis.adapters.legacy_policies import (
    run_gap_missed_entry_parity,
    write_gap_missed_entry_parity_reports,
)


def main() -> None:
    report = run_gap_missed_entry_parity()
    paths = write_gap_missed_entry_parity_reports(
        report,
        ROOT / "reports" / "phase3c",
    )
    summary = report.summary
    print("PHASE3C_GAP_MISSED_ENTRY_PARITY_REPORT")
    print(f"total_cases={summary['total_cases']}")
    print(f"passed_cases={summary['passed_cases']}")
    print(f"mismatched_cases={summary['mismatched_cases']}")
    print(f"fail_closed_cases={summary['fail_closed_cases']}")
    for key, path in sorted(paths.items()):
        print(f"{key}={path}")


if __name__ == "__main__":
    main()
