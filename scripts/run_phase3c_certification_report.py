from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tfis.adapters.legacy_policies import (
    build_phase3c_certification,
    run_gap_missed_entry_parity,
    write_gap_missed_entry_parity_reports,
    write_phase3c_certification_reports,
)


def main() -> None:
    parity_report = run_gap_missed_entry_parity()
    certification = build_phase3c_certification(parity_report)
    parity_paths = write_gap_missed_entry_parity_reports(
        parity_report,
        ROOT / "reports" / "phase3c",
    )
    certification_paths = write_phase3c_certification_reports(
        certification,
        ROOT / "reports" / "phase3c",
    )
    print("PHASE3C_CERTIFICATION_REPORT")
    print(f"final_verdict={certification['final_verdict']}")
    print(f"total_cases={certification['parity_counts']['total_cases']}")
    print(f"passed_cases={certification['parity_counts']['passed_cases']}")
    print(f"mismatched_cases={certification['parity_counts']['mismatched_cases']}")
    print(f"fail_closed_cases={certification['parity_counts']['fail_closed_cases']}")
    print(f"milestone_status=offline_complete_runtime_deferred")
    for key, path in sorted(parity_paths.items()):
        print(f"parity_{key}={path}")
    for key, path in sorted(certification_paths.items()):
        print(f"certification_{key}={path}")


if __name__ == "__main__":
    main()
