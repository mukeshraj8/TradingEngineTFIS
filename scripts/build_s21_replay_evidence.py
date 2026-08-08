from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.replay.s21_evidence import (
    build_base_evidence_from_certification,
    merge_option_evidence,
)
from tfis.replay.s21_evidence import load_s21_replay_evidence
from tfis.strategy_engine.s21 import S21StrategyEngine


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a sealed S21 replay evidence file from archived TFIS data. "
            "No network or broker calls are made."
        )
    )
    parser.add_argument("--certification-root", required=True)
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--option-evidence-dir")
    args = parser.parse_args()

    path = build_base_evidence_from_certification(
        repo_root=REPO_ROOT,
        certification_root=args.certification_root,
        session_date=args.session_date,
        output_path=args.output,
    )
    if args.option_evidence_dir:
        merge_option_evidence(
            evidence_path=path,
            option_evidence_dir=args.option_evidence_dir,
        )

    evidence = load_s21_replay_evidence(path)
    required = S21StrategyEngine().required_candidate_symbols(evidence)
    available = set(evidence.option_historical_references)

    print(f"Evidence file: {path}")
    missing = []
    for leg, symbols in required.items():
        leg_missing = [symbol for symbol in symbols if symbol not in available]
        print(f"{leg}: candidates={len(symbols)} missing_history={len(leg_missing)}")
        for symbol in leg_missing:
            missing.append(symbol)

    if missing:
        manifest = Path(args.output).with_suffix(".missing_option_history.txt")
        manifest.write_text(
            "\n".join(sorted(set(missing))) + "\n",
            encoding="utf-8",
        )
        print(f"Missing option-history manifest: {manifest}")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
