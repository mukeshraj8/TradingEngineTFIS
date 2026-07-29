from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.adapters.legacy_policies import (  # noqa: E402
    build_captured_parity_report,
    write_captured_parity_reports,
)


def main() -> int:
    case_paths = (
        REPO_ROOT / "tests" / "fixtures" / "paper" / "s23_archive_ingress_dry_run.jsonl",
        REPO_ROOT / "tests" / "fixtures" / "paper" / "s23_fyers_prelude.jsonl",
    )
    report = build_captured_parity_report(
        root=REPO_ROOT,
        case_paths=case_paths,
        generated_at=datetime(2026, 7, 29, 0, 0, tzinfo=timezone.utc),
    )
    paths = write_captured_parity_reports(
        report,
        REPO_ROOT / "reports" / "phase2d",
    )
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
