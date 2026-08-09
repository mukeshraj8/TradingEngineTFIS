from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path

import pytest

from tfis.backtest.nifty_hsre_data_adapter import (
    HsreDataError,
    NiftyHsreHistoricalMarketDataProvider,
    parse_nifty_option_symbol,
)
from tfis.domain.enums import OptionType


def _write_spot(root: Path, session: date, rows: list[tuple[str, float, float, float, float]]) -> Path:
    path = root / "spot" / f"{session.year}" / f"{session.month}" / f"nifty_spot{session:%d_%m_%Y}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["date,time,symbol,open,high,low,close"]
    for raw_time, open_, high, low, close in rows:
        lines.append(f"{session.isoformat()},{raw_time},NIFTY,{open_},{high},{low},{close}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_options(
    root: Path,
    session: date,
    rows: list[tuple[str, str, float, float, float, float, float, int]],
) -> Path:
    path = root / "options" / f"{session.year}" / f"{session.month}" / f"nifty_options_{session:%d_%m_%Y}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["date,time,symbol,open,high,low,close,oi,volume"]
    for raw_time, symbol, open_, high, low, close, oi, volume in rows:
        lines.append(
            f"{session.isoformat()},{raw_time},{symbol},{open_},{high},{low},{close},{oi},{volume}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_option_symbol_parser_handles_ce_pe_and_feb_expiry() -> None:
    ce = parse_nifty_option_symbol("NIFTY04JAN2421700CE")
    pe = parse_nifty_option_symbol("NIFTY04JAN2421700PE")
    feb = parse_nifty_option_symbol("NIFTY01FEB2422000CE")

    assert ce.underlying == "NIFTY"
    assert ce.expiry == date(2024, 1, 4)
    assert ce.strike == 21700
    assert ce.option_type is OptionType.CALL
    assert pe.option_type is OptionType.PUT
    assert feb.expiry == date(2024, 2, 1)
    assert feb.strike == 22000


@pytest.mark.parametrize(
    "symbol",
    ["", "NIFTY2024010421700CE", "NIFTY04JAX2421700CE", "NIFTY04JAN24CE"],
)
def test_option_symbol_parser_fails_closed_for_malformed_symbols(symbol: str) -> None:
    with pytest.raises(HsreDataError):
        parse_nifty_option_symbol(symbol)


def test_daily_file_resolution_uses_parsed_session_date(tmp_path: Path) -> None:
    session = date(2024, 1, 5)
    spot = _write_spot(tmp_path, session, [("09:15:00", 1, 2, 0.5, 1.5)])
    options = _write_options(
        tmp_path,
        session,
        [("09:16:00", "NIFTY11JAN2421700CE", 10, 11, 9, 10.5, 100, 1)],
    )
    provider = NiftyHsreHistoricalMarketDataProvider(tmp_path)

    assert provider.resolve_spot_file(session) == spot
    assert provider.resolve_option_file(session) == options
    with pytest.raises(HsreDataError, match="Missing spot file"):
        provider.resolve_spot_file(date(2024, 1, 6))


def test_spot_minute_api_is_chronological_exact_and_no_lookahead(tmp_path: Path) -> None:
    session = date(2024, 1, 5)
    _write_spot(
        tmp_path,
        session,
        [
            ("09:17:00", 3, 4, 2, 3.5),
            ("09:15:00", 1, 2, 0.5, 1.5),
            ("09:16:00", 2, 3, 1, 2.5),
        ],
    )
    provider = NiftyHsreHistoricalMarketDataProvider(tmp_path)

    bars = provider.get_spot_session_bars(session)
    assert [bar.timestamp.time() for bar in bars] == [
        time(9, 15),
        time(9, 16),
        time(9, 17),
    ]
    assert provider.get_spot_bar(session, time(9, 16)).close == 2.5
    through = provider.get_spot_bars_through(session, time(9, 16))
    assert [bar.timestamp.time() for bar in through] == [time(9, 15), time(9, 16)]
    assert all(bar.timestamp.time() <= time(9, 16) for bar in through)


def test_exact_option_chain_does_not_substitute_later_minutes(tmp_path: Path) -> None:
    session = date(2024, 1, 5)
    _write_options(
        tmp_path,
        session,
        [
            ("09:16:00", "NIFTY11JAN2421700CE", 10, 11, 9, 10.5, 100, 1),
            ("09:17:00", "NIFTY11JAN2421800CE", 20, 21, 19, 20.5, 200, 2),
        ],
    )
    provider = NiftyHsreHistoricalMarketDataProvider(tmp_path)

    chain = provider.get_option_chain(session, time(9, 16), exact=True)
    assert [row.identity.raw_symbol for row in chain] == ["NIFTY11JAN2421700CE"]
    assert chain[0].ltp == 10.5
    assert chain[0].oi == 100
    assert chain[0].bid is None
    assert chain[0].ask is None
    assert chain[0].bid_ask_source is None
    with pytest.raises(HsreDataError, match="Non-exact option-chain"):
        provider.get_option_chain(session, time(9, 16), exact=False)


def test_negative_and_blank_oi_fail_closed(tmp_path: Path) -> None:
    session = date(2024, 1, 5)
    _write_options(
        tmp_path,
        session,
        [("09:16:00", "NIFTY11JAN2421700CE", 10, 11, 9, 10.5, -1, 1)],
    )
    provider = NiftyHsreHistoricalMarketDataProvider(tmp_path)
    with pytest.raises(HsreDataError, match="negative OI"):
        provider.get_option_session_bars(session)

    blank_root = tmp_path / "blank"
    path = _write_options(
        blank_root,
        session,
        [("09:16:00", "NIFTY11JAN2421700CE", 10, 11, 9, 10.5, 0, 1)],
    )
    path.write_text(
        path.read_text(encoding="utf-8").replace(",0,1\n", ",,1\n"),
        encoding="utf-8",
    )
    with pytest.raises(HsreDataError, match="missing oi"):
        NiftyHsreHistoricalMarketDataProvider(blank_root).get_option_session_bars(session)


def test_prior_contract_history_excludes_current_and_cannot_cross_identity(tmp_path: Path) -> None:
    identity = parse_nifty_option_symbol("NIFTY11JAN2421700PE")
    _write_options(
        tmp_path,
        date(2024, 1, 8),
        [
            ("09:15:00", "NIFTY11JAN2421700PE", 10, 13, 9, 11, 100, 1),
            ("09:16:00", "NIFTY11JAN2421700PE", 11, 14, 8, 12, 100, 1),
            ("09:16:00", "NIFTY11JAN2421700CE", 99, 99, 99, 99, 100, 1),
            ("09:16:00", "NIFTY04JAN2421700PE", 88, 88, 88, 88, 100, 1),
            ("09:16:00", "NIFTY11JAN2421800PE", 77, 77, 77, 77, 100, 1),
        ],
    )
    _write_options(
        tmp_path,
        date(2024, 1, 9),
        [("09:16:00", "NIFTY11JAN2421700PE", 20, 24, 18, 22, 100, 1)],
    )
    _write_options(
        tmp_path,
        date(2024, 1, 10),
        [("09:16:00", "NIFTY11JAN2421700PE", 30, 40, 20, 35, 100, 1)],
    )
    provider = NiftyHsreHistoricalMarketDataProvider(tmp_path)

    prior = provider.get_prior_contract_daily_bars(
        session_date=date(2024, 1, 10),
        identity=identity,
        limit=3,
    )
    assert [bar.session_date for bar in prior] == [date(2024, 1, 8), date(2024, 1, 9)]
    assert prior[0].high == 14
    assert prior[0].low == 8
    assert all(bar.identity == identity for bar in prior)


def test_daily_aggregation_records_completeness_without_synthesizing(tmp_path: Path) -> None:
    session = date(2024, 1, 5)
    _write_spot(
        tmp_path,
        session,
        [
            ("09:15:00", 1, 2, 0.5, 1.5),
            ("09:17:00", 2, 4, 1, 3.5),
        ],
    )
    daily = NiftyHsreHistoricalMarketDataProvider(tmp_path).aggregate_spot_session(session)

    assert daily.open == 1
    assert daily.high == 4
    assert daily.low == 0.5
    assert daily.close == 3.5
    assert daily.completeness.observed_minutes == 2
    assert daily.completeness.expected_minutes_required is False
    assert daily.completeness.missing_minutes_synthesized is False


def test_january_2024_expiry_transition_is_discovered_from_symbols(tmp_path: Path) -> None:
    expectations = {
        date(2024, 1, 1): date(2024, 1, 4),
        date(2024, 1, 4): date(2024, 1, 4),
        date(2024, 1, 5): date(2024, 1, 11),
        date(2024, 1, 11): date(2024, 1, 11),
        date(2024, 1, 12): date(2024, 1, 18),
        date(2024, 1, 18): date(2024, 1, 18),
        date(2024, 1, 19): date(2024, 1, 25),
        date(2024, 1, 25): date(2024, 1, 25),
        date(2024, 1, 29): date(2024, 2, 1),
        date(2024, 1, 31): date(2024, 2, 1),
    }
    symbol_by_expiry = {
        date(2024, 1, 4): "NIFTY04JAN2421700CE",
        date(2024, 1, 11): "NIFTY11JAN2421700CE",
        date(2024, 1, 18): "NIFTY18JAN2421700CE",
        date(2024, 1, 25): "NIFTY25JAN2421700CE",
        date(2024, 2, 1): "NIFTY01FEB2421700CE",
    }
    for session, expiry in expectations.items():
        _write_options(
            tmp_path,
            session,
            [("09:16:00", symbol_by_expiry[expiry], 10, 11, 9, 10.5, 100, 1)],
        )
    provider = NiftyHsreHistoricalMarketDataProvider(tmp_path)

    for session, expected_expiry in expectations.items():
        assert provider.get_available_expiries(session) == (expected_expiry,)


def test_daily_cache_is_bounded(tmp_path: Path) -> None:
    for day in range(1, 4):
        session = date(2024, 1, day)
        _write_spot(tmp_path, session, [("09:15:00", day, day, day, day)])
    provider = NiftyHsreHistoricalMarketDataProvider(tmp_path, max_cached_sessions=2)

    provider.get_spot_session_bars(date(2024, 1, 1))
    provider.get_spot_session_bars(date(2024, 1, 2))
    provider.get_spot_session_bars(date(2024, 1, 3))

    assert list(provider._spot_cache) == [date(2024, 1, 2), date(2024, 1, 3)]
