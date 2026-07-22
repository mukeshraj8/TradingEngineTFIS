from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.paper import load_paper_runtime_broker_health_statuses


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show shared TFIS paper broker-health probe status by strategy."
    )
    parser.add_argument("--targets-config", default="config/paper_lifecycle_supervisor_targets.yaml")
    parser.add_argument("--tfis-root", default=str(REPO_ROOT))
    parser.add_argument(
        "--require-token",
        action="store_true",
        help="Refresh provider auth prerequisites before probing broker health.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    statuses = load_paper_runtime_broker_health_statuses(
        REPO_ROOT / args.targets_config,
        repo_root=REPO_ROOT,
        tfis_root=Path(args.tfis_root),
        skip_refresh=not args.require_token,
    )
    for status in statuses:
        parts = [
            f"BrokerHealthStatus: {status.strategy_code}",
            f"status={status.status}",
        ]
        if status.provider:
            parts.append(f"provider={status.provider}")
        if status.connection_state:
            parts.append(f"state={status.connection_state}")
        if status.is_connected is not None:
            parts.append(f"is_connected={status.is_connected}")
        if status.reconnect_attempts is not None:
            parts.append(f"reconnect_attempts={status.reconnect_attempts}")
        parts.append(f"message={status.message}")
        print(" | ".join(parts))
    return 0 if all(item.status == "PASS" for item in statuses) else 1


if __name__ == "__main__":
    raise SystemExit(main())
