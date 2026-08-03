from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.broker.authentication import BrokerSessionStatus
from tfis.broker.authentication.fyers import FyersAuthenticationAdapter
from tfis.fyers_read_only import (
    FyersReadOnlyAdapter,
    FyersReadOnlyStatus,
    canonical_hash,
    classify_monthly_expiries,
    redact_sensitive,
)


IST = ZoneInfo("Asia/Kolkata")
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "data" / "strategies" / "S22" / "fyers_read_only_snapshots"
DEFAULT_SYMBOL = "RELIANCE"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture a read-only FYERS S22 stock metadata snapshot.")
    parser.add_argument("--capture-read-only", action="store_true", help="Run the real FYERS read-only capture.")
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--strike-count", type=int, default=50)
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help="Underlying stock symbol, for example RELIANCE, TCS, or INFY.")
    parser.add_argument(
        "--session-date",
        type=date.fromisoformat,
        help="Trading date/session date in YYYY-MM-DD. Defaults to the current India date.",
    )
    parser.add_argument(
        "--allow-refresh",
        action="store_true",
        help="Allow the canonical FYERS refresh/login flow before read-only capture.",
    )
    args = parser.parse_args(argv)

    captured_at = datetime.now(tz=IST)
    symbol = _normalized_symbol(args.symbol)
    session_date = args.session_date or captured_at.date()
    fyers_underlying = _fyers_underlying_symbol(symbol)
    intended_requests = [
        "validate_session",
        "fetch_symbol_master:NSE",
        "fetch_symbol_master:NSEFO",
        f"fetch_historical_candles:{fyers_underlying}:daily",
        f"fetch_option_chain:{fyers_underlying}:near_monthly",
        f"fetch_option_chain:{fyers_underlying}:next_monthly",
    ]
    if not args.capture_read_only:
        _print_summary(
            {
                "verdict": "DRY_RUN_ONLY",
                "authority": "FYERS_READ_ONLY_DATA_ACQUISITION",
                "external_order_authority": "NONE",
                "symbol": symbol,
                "session_date": session_date.isoformat(),
                "intended_requests": intended_requests,
                "operator_action": "Rerun with --capture-read-only after approved FYERS token setup.",
            }
        )
        return 0

    auth_adapter = FyersAuthenticationAdapter(tfis_root=REPO_ROOT, logical_account_ref="s22-reliance-read-only")
    auth_result = auth_adapter.authenticate(allow_refresh=args.allow_refresh, validate_session=True)
    if auth_result.status != BrokerSessionStatus.AUTHENTICATED or auth_result.session is None:
        reason = auth_result.failure.message if auth_result.failure else auth_result.status.value
        _print_summary(_auth_required(reason, intended_requests, auth_status=auth_result.status.value))
        return 2
    adapter = FyersReadOnlyAdapter.from_validated_session(
        auth_result.session,
        now_provider=lambda: datetime.now(tz=IST),
    )

    nse_master = adapter.fetch_symbol_master("NSE")
    nsefo_master = adapter.fetch_symbol_master("NSEFO")
    if nse_master.status != FyersReadOnlyStatus.SUCCESS or nsefo_master.status != FyersReadOnlyStatus.SUCCESS:
        _print_summary(
            {
                "verdict": "BLOCKED_METADATA",
                "authority": "FYERS_READ_ONLY_DATA_ACQUISITION",
                "external_order_authority": "NONE",
                "nse_status": nse_master.status.value,
                "nsefo_status": nsefo_master.status.value,
                "warnings": list(nse_master.warnings + nsefo_master.warnings),
            }
        )
        return 3

    all_records = tuple(nse_master.payload) + tuple(nsefo_master.payload)
    stock_records = tuple(record for record in all_records if _record_matches_symbol(record, symbol))
    expiry_classification = classify_monthly_expiries(stock_records, underlying=symbol, as_of=session_date)

    completed_history_to = _last_completed_weekday(session_date)
    history = adapter.fetch_historical_candles(
        symbol=fyers_underlying,
        resolution="D",
        range_from=completed_history_to - timedelta(days=180),
        range_to=completed_history_to,
        exclude_incomplete_after=datetime.combine(completed_history_to, datetime.max.time(), tzinfo=IST),
    )

    option_chains = []
    for expiry in (expiry_classification.near_monthly_expiry, expiry_classification.next_monthly_expiry):
        if expiry is None:
            continue
        option_chains.append(
            adapter.fetch_option_chain(
                underlying=fyers_underlying,
                expiry=expiry,
                strike_count=args.strike_count,
                instrument_records=stock_records,
            )
        )

    snapshot_id = f"s22-{symbol.lower()}-fyers-{captured_at.strftime('%Y%m%dT%H%M%S%z')}"
    output_dir = args.artifact_root / captured_at.date().isoformat() / snapshot_id
    output_dir.mkdir(parents=True, exist_ok=False)

    snapshot = {
        "schema_version": "s22.stock.fyers_read_only_snapshot.v2",
        "snapshot_id": snapshot_id,
        "authority": "FYERS_READ_ONLY_DATA_ACQUISITION",
        "external_order_authority": "NONE",
        "captured_at": captured_at.isoformat(),
        "capture_date": captured_at.date().isoformat(),
        "session_date": session_date.isoformat(),
        "provider": "FYERS",
        "instrument": symbol,
        "underlying_symbol": fyers_underlying,
        "session": auth_result.to_dict(),
        "symbol_master": {
            "nse_status": nse_master.status.value,
            "nsefo_status": nsefo_master.status.value,
            "nse_hash": nse_master.source_hash,
            "nsefo_hash": nsefo_master.source_hash,
            "underlying_record_count": len(stock_records),
            "underlying_records": [record.to_dict() for record in stock_records],
        },
        "expiry_classification": expiry_classification.to_dict(),
        "history": history.to_dict(),
        "option_chains": [result.to_dict() for result in option_chains],
        "redaction_audit": {
            "credentials_in_snapshot": False,
            "redaction_applied": True,
            "hash": canonical_hash({"snapshot_id": snapshot_id, "redaction": "applied"}),
        },
    }
    _write_json(output_dir / "snapshot.json", snapshot)

    required_gaps = _required_gaps(symbol, stock_records, expiry_classification, history, option_chains)
    summary = {
        "verdict": "CAPTURE_COMPLETE" if not required_gaps else "BLOCKED_METADATA",
        "snapshot_id": snapshot_id,
        "snapshot_path": str(output_dir / "snapshot.json"),
        "symbol": symbol,
        "session_date": session_date.isoformat(),
        "required_gaps": required_gaps,
        "external_order_authority": "NONE",
    }
    _write_json(output_dir / "summary.json", summary)
    _print_summary(summary)
    return 0 if not required_gaps else 3


def _normalized_symbol(raw: str) -> str:
    return str(raw).strip().upper()


def _fyers_underlying_symbol(symbol: str) -> str:
    return f"NSE:{symbol}-EQ"


def _record_matches_symbol(record: Any, symbol: str) -> bool:
    underlying = str(getattr(record, "underlying", "") or "").upper()
    source_symbol = str(getattr(record, "source_symbol", "") or "").upper()
    return underlying == symbol or f"NSE:{symbol}" in source_symbol or symbol in source_symbol


def _gap_code(symbol: str, suffix: str) -> str:
    return f"{symbol}_{suffix}"


def _required_gaps(symbol: str, records, expiry_classification, history, option_chains) -> list[str]:
    gaps: list[str] = []
    if not records:
        gaps.append(_gap_code(symbol, "SYMBOL_MASTER_RECORDS_MISSING"))
    option_records = [record for record in records if record.option_type in {"CALL", "PUT"}]
    if not option_records:
        gaps.append(_gap_code(symbol, "OPTION_CONTRACTS_MISSING"))
    if not any(record.lot_size for record in option_records):
        gaps.append(_gap_code(symbol, "OPTION_LOT_SIZE_MISSING"))
    if not any(record.tick_size for record in option_records):
        gaps.append(_gap_code(symbol, "OPTION_TICK_SIZE_MISSING"))
    if expiry_classification.near_monthly_expiry is None:
        gaps.append("NEAR_MONTHLY_EXPIRY_MISSING")
    if expiry_classification.next_monthly_expiry is None:
        gaps.append("NEXT_MONTHLY_EXPIRY_MISSING")
    if history.status != FyersReadOnlyStatus.SUCCESS or not history.payload.candles:
        gaps.append(_gap_code(symbol, "COMPLETED_DAILY_HISTORY_MISSING"))
    if not option_chains:
        gaps.append(_gap_code(symbol, "OPTION_CHAIN_MISSING"))
    if any(result.status != FyersReadOnlyStatus.SUCCESS for result in option_chains):
        gaps.append(_gap_code(symbol, "OPTION_CHAIN_UNAVAILABLE"))
    return gaps


def _last_completed_weekday(value: date) -> date:
    candidate = value - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _auth_required(reason: str, intended_requests: list[str], *, auth_status: str = "AUTHENTICATION_REQUIRED") -> dict[str, Any]:
    return {
        "verdict": "FYERS_AUTHENTICATION_REQUIRED_FOR_CAPTURE",
        "authentication_status": auth_status,
        "authority": "FYERS_READ_ONLY_DATA_ACQUISITION",
        "external_order_authority": "NONE",
        "reason": redact_sensitive({"message": reason})["message"],
        "intended_requests": intended_requests,
        "operator_steps": [
            "Run .\\.venv\\Scripts\\python.exe scripts\\fyers_token_refresh.py --prepare from the TFIS repository.",
            "Complete any FYERS login/TOTP/PIN interaction required by the canonical script outside this capture workflow.",
            "Rerun this script with --capture-read-only.",
        ],
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(redact_sensitive(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _print_summary(value: Mapping[str, Any]) -> None:
    print(json.dumps(redact_sensitive(value), indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
