from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.paper import load_paper_runtime_guardrail_statuses


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show shared TFIS paper runtime guardrail status by strategy."
    )
    parser.add_argument("--targets-config", default="config/paper_lifecycle_supervisor_targets.yaml")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    statuses = load_paper_runtime_guardrail_statuses(
        REPO_ROOT / args.targets_config,
        repo_root=REPO_ROOT,
    )
    if args.json:
        print(
            json.dumps(
                [asdict(status) for status in statuses],
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
        return 0
    for status in statuses:
        parts = [
            f"strategy={status.strategy_code}",
            f"status={status.status}",
        ]
        if status.source_mode:
            parts.append(f"source_mode={status.source_mode}")
        if status.paper_mode_enabled is not None:
            parts.append(f"paper_mode_enabled={str(status.paper_mode_enabled).lower()}")
        if status.no_live_orders_allowed is not None:
            parts.append(f"no_live_orders_allowed={str(status.no_live_orders_allowed).lower()}")
        if status.kill_switch_enabled is not None:
            parts.append(f"kill_switch_enabled={str(status.kill_switch_enabled).lower()}")
        if status.session_kill_switch_active is not None:
            parts.append(
                f"session_kill_switch_active={str(status.session_kill_switch_active).lower()}"
            )
        parts.append(f"message={status.message}")
        print("GuardrailStatus: " + " ".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
