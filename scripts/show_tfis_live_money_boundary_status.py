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

from tfis.paper.live_money_boundary_status import load_live_money_boundary_status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show the TFIS live-money execution/reconciliation boundary."
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    status = load_live_money_boundary_status()
    if args.json:
        print(json.dumps(asdict(status), indent=2, sort_keys=True))
        return 0
    print(
        "LiveMoneyBoundary: "
        f"status={status.status} "
        f"live_money_ready={str(status.live_money_ready).lower()} "
        f"paper_runtime_safe={str(status.paper_runtime_safe).lower()} "
        f"order_routing_enabled={str(status.order_routing_enabled).lower()} "
        f"message={status.message}"
    )
    for gate in status.gates:
        print(
            "LiveMoneyGate: "
            f"code={gate.code} "
            f"status={gate.status} "
            f"required_before_live={str(gate.required_before_live).lower()} "
            f"description={gate.description}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
