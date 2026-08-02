from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.broker.diagnostics.fyers import FyersDiagnosticProbeConfig, run_fyers_broker_diagnostic
from tfis.broker.authentication import redact_sensitive


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run broker diagnostics without granting trading authority.")
    parser.add_argument("--broker", choices=["fyers"], default="fyers")
    parser.add_argument("--account", default="default", help="Logical account reference; not a secret.")
    parser.add_argument("--environment", default="local")
    parser.add_argument("--tfis-root", default=str(REPO_ROOT))
    parser.add_argument("--configuration-only", action="store_true")
    parser.add_argument("--allow-refresh", action="store_true", help="Allow canonical FYERS token refresh/login flow.")
    parser.add_argument("--check-reference-data", action="store_true")
    parser.add_argument("--check-historical-data", action="store_true")
    parser.add_argument("--check-quote", action="store_true")
    parser.add_argument("--check-option-chain", action="store_true")
    parser.add_argument("--check-account-read", action="store_true")
    parser.add_argument("--underlying-symbol", default="NSE:RELIANCE-EQ")
    parser.add_argument("--json-out", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    probe = FyersDiagnosticProbeConfig(
        check_reference_data=args.check_reference_data,
        check_historical_data=args.check_historical_data,
        check_quote=args.check_quote,
        check_option_chain=args.check_option_chain,
        check_account_read=args.check_account_read,
        underlying_symbol=args.underlying_symbol,
    )
    snapshot = run_fyers_broker_diagnostic(
        tfis_root=args.tfis_root,
        logical_account_ref=args.account,
        environment=args.environment,
        allow_refresh=args.allow_refresh,
        configuration_only=args.configuration_only,
        probe_config=probe,
    )
    payload = snapshot.to_dict()
    rendered = json.dumps(redact_sensitive(payload), indent=2, sort_keys=True)
    print(rendered)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered + "\n", encoding="utf-8")
    return 0 if not snapshot.blocking_reasons else 1


if __name__ == "__main__":
    raise SystemExit(main())
