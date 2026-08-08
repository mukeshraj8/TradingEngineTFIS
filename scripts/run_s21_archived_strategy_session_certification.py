from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.replay.s21_archived_session import S21ArchivedStrategySessionAdapter


def run(cmd: list[str]) -> int:
    print("\n>", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=str(REPO_ROOT)).returncode


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Certify all durable S21 strategy-session dates through the existing "
            "historical certification runner without copying archived market evidence."
        )
    )
    ap.add_argument(
        "--source-root",
        default="data/strategies/S21/fyers_morning_supervised_decision",
    )
    ap.add_argument(
        "--compatibility-root",
        default="reports/s21_archived_session_views",
    )
    ap.add_argument(
        "--output-root",
        default="reports/s21_archived_session_certification",
    )
    ap.add_argument("--start-date")
    ap.add_argument("--end-date")
    args = ap.parse_args()

    adapter = S21ArchivedStrategySessionAdapter(REPO_ROOT / args.source_root)
    dates = list(adapter.discover_dates())

    if args.start_date:
        lower = date.fromisoformat(args.start_date)
        dates = [d for d in dates if d >= lower]
    if args.end_date:
        upper = date.fromisoformat(args.end_date)
        dates = [d for d in dates if d <= upper]

    if not dates:
        raise SystemExit("No matching durable S21 sessions discovered.")

    for d in dates:
        adapter.materialize_compatibility_view(
            session_date=d,
            compatibility_root=REPO_ROOT / args.compatibility_root,
        )

    output_root = REPO_ROOT / args.output_root
    output_root.mkdir(parents=True, exist_ok=True)

    results = []
    python = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    historical = REPO_ROOT / "scripts" / "run_s21_historical_certification.py"

    # Run exact archived dates one at a time. This deliberately avoids treating
    # calendar dates with no strategy artifact as certification failures.
    for idx, d in enumerate(dates, 1):
        per_day_out = output_root / d.isoformat()
        print(
            f"\n{'='*100}\n"
            f"[{idx}/{len(dates)}] ARCHIVED S21 CERTIFICATION {d.isoformat()}\n"
            f"{'='*100}"
        )
        rc = run([
            str(python),
            str(historical),
            "--start-date", d.isoformat(),
            "--end-date", d.isoformat(),
            "--certification-root", str(REPO_ROOT / args.compatibility_root),
            "--output-root", str(per_day_out),
        ])
        summary_path = per_day_out / "summary.json"
        payload = None
        if summary_path.exists():
            try:
                payload = json.loads(summary_path.read_text(encoding="utf-8"))
            except Exception:
                payload = None
        results.append({
            "session_date": d.isoformat(),
            "exit_code": rc,
            "summary_path": str(summary_path),
            "summary": payload.get("summary") if isinstance(payload, dict) else None,
        })

    combined = {
        "source_root": str(REPO_ROOT / args.source_root),
        "compatibility_root": str(REPO_ROOT / args.compatibility_root),
        "dates": [d.isoformat() for d in dates],
        "results": results,
    }
    combined_path = output_root / "archived_session_certification_index.json"
    combined_path.write_text(
        json.dumps(combined, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"\nCombined index: {combined_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
