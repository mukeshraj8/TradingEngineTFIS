from __future__ import annotations

import sys
import argparse
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.brokers.fyers_token import (
    FyersTokenRefreshError,
    prepare_fyers_env_from_tfis,
    refresh_fyers_token,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare or refresh the TFIS FYERS token store.")
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Validate the existing token first and refresh only when required.",
    )
    parser.add_argument(
        "--tfis-root",
        default=str(REPO_ROOT),
        help="TFIS repo root that owns .env and data/token_store.json.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.prepare:
            prepared = prepare_fyers_env_from_tfis(
                tfis_root=args.tfis_root,
                skip_refresh=False,
            )
            status = "refreshed" if prepared.refreshed else "reused"
            print(f"FYERS token prepared: {status} {prepared.token_store}")
        else:
            refresh_fyers_token()
    except FyersTokenRefreshError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
