from __future__ import annotations

"""Separate read-only evidence collector for S21 replay.

This utility is deliberately NOT imported by the replay or strategy engine.

Recommended workflow:
1. collect candidate completed-daily history only;
2. merge and run the pure replay;
3. collect minute bars only for the selected contracts if the replay asks for
   ORPT/RC evidence.

This avoids fetching intraday bars for every candidate contract.
"""

import argparse
import hashlib
import json
import re
import sys
import time as time_module
from datetime import date, datetime, time, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.brokers.fyers_token import prepare_fyers_env_from_tfis
from tfis.paper.live_ingress import PaperLiveIngressConfig
from tfis.paper.lifecycle_runtime_config import (
    PaperLifecycleBrokerConfig,
    build_paper_broker_adapter_from_broker_config,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect read-only option history evidence into a standalone directory."
    )
    parser.add_argument("--symbols-file", required=True)
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--config", default="config/paper.s21.fyers_connect_test.yaml")
    parser.add_argument("--output-root", required=True)
    parser.add_argument(
        "--mode",
        choices=("daily", "minute", "both"),
        default="daily",
        help=(
            "Default is daily. Use minute only after the pure strategy engine has "
            "identified selected contracts."
        ),
    )
    parser.add_argument(
        "--minute-from",
        default="09:24",
        help="Minute-history start HH:MM. Default preserves ORPT/RC collection.",
    )
    parser.add_argument(
        "--minute-to",
        default="09:30",
        help="Minute-history end HH:MM. Use 15:30 for full-session fill certification.",
    )
    parser.add_argument(
        "--request-delay-seconds",
        type=float,
        default=0.60,
        help="Minimum delay after each broker request to reduce FYERS 429 risk.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Retries for FYERS rate-limit errors using exponential backoff.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Ignore valid cached evidence and fetch again.",
    )
    args = parser.parse_args()

    session_date = date.fromisoformat(args.session_date)
    minute_from = time.fromisoformat(args.minute_from)
    minute_to = time.fromisoformat(args.minute_to)
    if minute_to <= minute_from:
        raise SystemExit("--minute-to must be later than --minute-from")
    symbols = sorted(
        {
            line.strip()
            for line in Path(args.symbols_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    )
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    prepare_fyers_env_from_tfis(tfis_root=REPO_ROOT, skip_refresh=False)
    config = PaperLiveIngressConfig.from_yaml(args.config)
    adapter = build_paper_broker_adapter_from_broker_config(
        PaperLifecycleBrokerConfig(
            provider=config.broker.provider,
            timezone=config.broker.timezone,
            payload_fixture_path=config.broker.payload_fixture_path,
            capture_stream_events=config.broker.capture_stream_events,
            option_chain_strike_count=config.broker.option_chain_strike_count,
        )
    )
    adapter.connect()

    failures: list[dict[str, str]] = []
    try:
        for index, symbol in enumerate(symbols, 1):
            print(f"[{index}/{len(symbols)}] {symbol}")
            symbol_dir = output_root / _safe_symbol_dir(symbol)
            symbol_dir.mkdir(parents=True, exist_ok=True)
            (symbol_dir / "symbol.json").write_text(
                json.dumps(
                    {"symbol": symbol, "directory": symbol_dir.name},
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            try:
                if args.mode in ("daily", "both"):
                    daily_path = symbol_dir / "daily_references.json"
                    if (
                        not args.force_refresh
                        and _valid_daily_cache(
                            daily_path,
                            symbol=symbol,
                            session_date=session_date,
                        )
                    ):
                        print("  CACHE_HIT daily")
                    else:
                        try:
                            _with_rate_limit_retry(
                                lambda: _collect_daily(
                                    adapter=adapter,
                                    symbol=symbol,
                                    session_date=session_date,
                                    output_path=daily_path,
                                ),
                                symbol=symbol,
                                kind="daily",
                                max_retries=args.max_retries,
                                request_delay_seconds=args.request_delay_seconds,
                            )
                        except Exception as exc:
                            if "daily history payload returned no candles" in str(exc).lower():
                                daily_path.write_text(
                                    json.dumps(
                                        {
                                            "symbol": symbol,
                                            "session_date": session_date.isoformat(),
                                            "source": "FYERS_READ_ONLY_NO_COMPLETED_DAILY_CANDLES",
                                            "completed_bar_count": 0,
                                            "references": {},
                                            "availability": "NO_CANDLES_RETURNED",
                                        },
                                        indent=2,
                                        sort_keys=True,
                                    ),
                                    encoding="utf-8",
                                )
                                print("  NO_CANDLES: recorded as authoritative negative evidence")
                            else:
                                raise

                if args.mode in ("minute", "both"):
                    minute_path = symbol_dir / "minute_bars.json"
                    if (
                        not args.force_refresh
                        and _minute_cache_covers(
                            minute_path,
                            symbol=symbol,
                            session_date=session_date,
                            requested_from=minute_from,
                            requested_to=minute_to,
                        )
                    ):
                        print(
                            f"  CACHE_HIT minute "
                            f"{minute_from.isoformat(timespec='minutes')}-"
                            f"{minute_to.isoformat(timespec='minutes')}"
                        )
                    else:
                        _with_rate_limit_retry(
                            lambda: _collect_minute(
                                adapter=adapter,
                                symbol=symbol,
                                session_date=session_date,
                                output_path=minute_path,
                                from_time=minute_from,
                                to_time=minute_to,
                            ),
                            symbol=symbol,
                            kind="minute",
                            max_retries=args.max_retries,
                            request_delay_seconds=args.request_delay_seconds,
                        )
            except Exception as exc:
                failures.append(
                    {
                        "symbol": symbol,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                print(f"  FAILED: {type(exc).__name__}: {exc}")

    finally:
        adapter.disconnect()

    summary = {
        "session_date": session_date.isoformat(),
        "mode": args.mode,
        "symbols_requested": len(symbols),
        "failure_count": len(failures),
        "failures": failures,
    }
    (output_root / "collection_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    if failures:
        print(f"Completed with {len(failures)} failures. See collection_summary.json.")
        return 2

    print(f"Collected {len(symbols)} symbols successfully in {args.mode} mode.")
    return 0


def _collect_daily(*, adapter, symbol: str, session_date: date, output_path: Path) -> None:
    raw_symbol = adapter.to_fyers_option_symbol(symbol)
    bars = adapter.get_daily_bars_for_symbol(
        raw_symbol=raw_symbol,
        normalized_symbol=symbol,
        session_date=session_date,
        lookback_days=14,
        continuous=False,
    )
    completed = [
        bar
        for bar in bars
        if bar.bar_start.date() < session_date
        and bar.high is not None
        and bar.low is not None
    ]
    refs = {}
    if len(completed) >= 3:
        last2 = completed[-2:]
        last3 = completed[-3:]
        refs = {
            "OPT_PRV_2DHH": max(float(x.high) for x in last2),
            "OPT_PRV_2DLL": min(float(x.low) for x in last2),
            "OPT_PRV_3DHH": max(float(x.high) for x in last3),
            "OPT_PRV_3DLL": min(float(x.low) for x in last3),
        }

    output_path.write_text(
        json.dumps(
            {
                "symbol": symbol,
                "session_date": session_date.isoformat(),
                "source": "FYERS_READ_ONLY_COMPLETED_DAILY_HISTORY",
                "completed_bar_count": len(completed),
                "references": refs,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _collect_minute(
    *,
    adapter,
    symbol: str,
    session_date: date,
    output_path: Path,
    from_time: time,
    to_time: time,
) -> None:
    bars = adapter.get_option_bars(
        symbol,
        session_date=session_date,
        from_time=from_time,
        to_time=to_time,
        interval_minutes=1,
    )
    output_path.write_text(
        json.dumps(
            {
                "symbol": symbol,
                "session_date": session_date.isoformat(),
                "source": "FYERS_READ_ONLY_OPTION_MINUTE_HISTORY",
                "requested_from": from_time.isoformat(timespec="minutes"),
                "requested_to": to_time.isoformat(timespec="minutes"),
                "bars": [
                    {
                        "bar_start": bar.bar_start.isoformat(),
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                    }
                    for bar in bars
                ],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )



def _load_json_if_valid(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _valid_daily_cache(path: Path, *, symbol: str, session_date: date) -> bool:
    payload = _load_json_if_valid(path)
    return bool(
        payload
        and payload.get("symbol") == symbol
        and payload.get("session_date") == session_date.isoformat()
        and (
            isinstance(payload.get("references"), dict)
            or payload.get("availability") == "NO_CANDLES_RETURNED"
        )
    )


def _minute_cache_covers(
    path: Path,
    *,
    symbol: str,
    session_date: date,
    requested_from: time,
    requested_to: time,
) -> bool:
    payload = _load_json_if_valid(path)
    if not payload:
        return False
    if payload.get("symbol") != symbol or payload.get("session_date") != session_date.isoformat():
        return False

    cached_from = payload.get("requested_from")
    cached_to = payload.get("requested_to")
    if cached_from and cached_to:
        try:
            return (
                time.fromisoformat(str(cached_from)) <= requested_from
                and time.fromisoformat(str(cached_to)) >= requested_to
            )
        except ValueError:
            pass

    # Backward-compatible inference for older cache files that lack coverage
    # metadata. A 09:24-09:30 file must not be mistaken for full-session data.
    bars = payload.get("bars")
    if not isinstance(bars, list) or not bars:
        return False
    timestamps = []
    for row in bars:
        if not isinstance(row, dict) or not row.get("bar_start"):
            continue
        try:
            timestamps.append(datetime.fromisoformat(str(row["bar_start"])))
        except Exception:
            continue
    if not timestamps:
        return False
    start_t = min(timestamps).timetz().replace(tzinfo=None)
    end_t = max(timestamps).timetz().replace(tzinfo=None)
    # One-minute bars: a bar starting at 15:29 covers through 15:30.
    inferred_end = (
        datetime.combine(session_date, end_t) + timedelta(minutes=1)
    ).time()
    return start_t <= requested_from and inferred_end >= requested_to


def _is_rate_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "429" in message or "request limit reached" in message or "rate limit" in message


def _with_rate_limit_retry(
    operation,
    *,
    symbol: str,
    kind: str,
    max_retries: int,
    request_delay_seconds: float,
):
    attempt = 0
    while True:
        try:
            result = operation()
            if request_delay_seconds > 0:
                time_module.sleep(request_delay_seconds)
            return result
        except Exception as exc:
            if not _is_rate_limit_error(exc) or attempt >= max_retries:
                raise
            wait_seconds = min(60.0, 2.0 ** (attempt + 1))
            attempt += 1
            print(
                f"  RATE_LIMIT {kind} {symbol}: retry {attempt}/{max_retries} "
                f"after {wait_seconds:.1f}s"
            )
            time_module.sleep(wait_seconds)


def _safe_symbol_dir(symbol: str) -> str:
    # Windows cannot use ':' and several other characters in directory names.
    base = re.sub(r'[^A-Za-z0-9._-]+', '_', symbol).strip("._")
    digest = hashlib.sha1(symbol.encode("utf-8")).hexdigest()[:10]
    return f"{base[:100]}__{digest}"


if __name__ == "__main__":
    raise SystemExit(main())
