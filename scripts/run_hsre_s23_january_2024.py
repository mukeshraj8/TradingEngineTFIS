from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tfis.backtest.hsre_s23_month_run import run_hsre_s23_january_2024


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run HSRE S23 end-to-end for observed January 2024 NIFTY sessions."
    )
    parser.add_argument(
        "--data-root",
        default=r"D:\HistoricalData\Nifty",
        help="Historical NIFTY data root.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path("reports") / "hsre" / "S23" / "2024-01"),
        help="Report output directory.",
    )
    args = parser.parse_args()

    result = run_hsre_s23_january_2024(
        data_root=args.data_root,
        output_dir=args.output_dir,
    )
    print(
        "HSRE_M5_S23_JAN2024 "
        f"output={result.output_dir} "
        f"sessions={len(result.sessions)} "
        f"runtime_seconds={result.runtime_seconds:.3f}"
    )
    print(json.dumps(result.summary["funnel"], indent=2, sort_keys=True))
    print(json.dumps(result.summary["trade_metrics"], indent=2, sort_keys=True))
    print(json.dumps(result.hashes, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
