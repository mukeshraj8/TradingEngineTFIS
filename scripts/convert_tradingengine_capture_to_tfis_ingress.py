from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.paper.tradingengine_capture_adapter import (
    TradingEngineCaptureAdapterError,
    build_capture_audit,
    convert_capture_to_normalized_market_events,
    discover_context_session_dir,
    infer_option_quotes_path,
    render_audit_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit or convert read-only TradingEngine capture sessions into TFIS "
            "normalized S23 market-event JSONL."
        )
    )
    parser.add_argument(
        "--context-session-dir",
        help="Path to one TradingEngine context session directory containing ticks_context.csv.",
    )
    parser.add_argument(
        "--option-quotes-csv",
        help="Path to the matching NIFTY option quote CSV for the session date.",
    )
    parser.add_argument(
        "--tradingdata-root",
        help=(
            "Optional TradingData root. When supplied with --session-date, the script "
            "can auto-discover the context session folder and option quote CSV."
        ),
    )
    parser.add_argument(
        "--session-date",
        help="Session date in YYYY-MM-DD format when using --tradingdata-root discovery.",
    )
    parser.add_argument(
        "--audit-json",
        help="Optional output path for the audit JSON report.",
    )
    parser.add_argument(
        "--output-jsonl",
        help=(
            "Optional output path for TFIS normalized market-event JSONL. "
            "When omitted, the script runs in audit-only mode."
        ),
    )
    parser.add_argument(
        "--selected-contract-symbol",
        help=(
            "Required when emitting JSONL. Pass the raw TradingEngine/Fyers option "
            "symbol, for example NSE:NIFTY2660223200CE."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        context_session_dir = args.context_session_dir
        option_quotes_csv = args.option_quotes_csv
        if context_session_dir is None:
            if not args.tradingdata_root or not args.session_date:
                raise TradingEngineCaptureAdapterError(
                    "Provide --context-session-dir directly, or provide both "
                    "--tradingdata-root and --session-date."
                )
            context_session_dir = discover_context_session_dir(
                tradingdata_root=args.tradingdata_root,
                session_date=args.session_date,
            )
        if option_quotes_csv is None:
            if not args.tradingdata_root:
                raise TradingEngineCaptureAdapterError(
                    "Provide --option-quotes-csv directly, or provide --tradingdata-root "
                    "so the matching option quote archive can be inferred."
                )
            option_quotes_csv = infer_option_quotes_path(
                tradingdata_root=args.tradingdata_root,
                session_date=args.session_date,
            )
        audit = build_capture_audit(
            context_session_dir=context_session_dir,
            option_quotes_path=option_quotes_csv,
        )
        audit_json = render_audit_json(audit)
        if args.audit_json:
            audit_path = Path(args.audit_json)
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            audit_path.write_text(audit_json, encoding="utf-8")
        else:
            print(audit_json, end="")

        if not args.output_jsonl:
            return 0

        if not args.selected_contract_symbol:
            raise TradingEngineCaptureAdapterError(
                "--selected-contract-symbol is required when --output-jsonl is used."
            )
        artifact = convert_capture_to_normalized_market_events(
            context_session_dir=context_session_dir,
            option_quotes_path=option_quotes_csv,
            selected_contract_symbol=args.selected_contract_symbol,
            output_jsonl_path=args.output_jsonl,
        )
    except TradingEngineCaptureAdapterError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote normalized JSONL: {artifact.output_jsonl_path}")
    print(
        "Normalized selected contract: "
        f"{artifact.normalized_selected_contract_symbol}"
    )
    print(f"Output event count: {artifact.output_event_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
