from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.adapters.legacy_policies import (  # noqa: E402
    build_s23_synthetic_golden_packet,
    captured_cases_to_packets,
    write_decision_packet_reports,
)


def main() -> int:
    golden = build_s23_synthetic_golden_packet()
    captured = captured_cases_to_packets(
        (
            REPO_ROOT / "tests" / "fixtures" / "paper" / "s23_archive_ingress_dry_run.jsonl",
            REPO_ROOT / "tests" / "fixtures" / "paper" / "s23_fyers_prelude.jsonl",
        )
    )
    paths = write_decision_packet_reports(
        (golden, *captured),
        REPO_ROOT / "reports" / "phase2d1",
    )
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
