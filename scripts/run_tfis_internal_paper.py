from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.runtime.multi_strategy import build_unified_runtime_reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic unified S21/S22/S23 internal-paper certification.")
    parser.add_argument("--registry", default="config/internal_paper_strategy_instances.yaml")
    parser.add_argument("--report-dir", default="reports/dashboard_v1")
    args = parser.parse_args(argv)
    reports = build_unified_runtime_reports(REPO_ROOT / args.registry, REPO_ROOT / args.report_dir)
    print("TFIS unified internal-paper certification completed.")
    print(f"Reports: {REPO_ROOT / args.report_dir}")
    print(f"Report count: {len(reports)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
