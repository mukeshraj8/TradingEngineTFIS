from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.paper import load_paper_runtime_strategy_trust_statuses


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show controlled-paper strategy trust evidence for configured TFIS paper targets."
    )
    parser.add_argument(
        "--targets-config",
        default="config/paper_lifecycle_supervisor_targets.yaml",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    statuses = load_paper_runtime_strategy_trust_statuses(
        REPO_ROOT / args.targets_config,
        repo_root=REPO_ROOT,
    )
    for status in statuses:
        print(
            "StrategyTrustStatus: "
            f"strategy={status.strategy_code} "
            f"status={status.status} "
            f"trust_level={status.trust_level} "
            f"checked_rules={status.checked_rule_count} "
            f"issues={status.issue_count} "
            f"message={status.message}"
        )
    return 0 if all(status.status == "PASS" for status in statuses) else 1


if __name__ == "__main__":
    raise SystemExit(main())
