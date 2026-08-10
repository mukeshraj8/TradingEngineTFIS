from __future__ import annotations

from datetime import date, time
from pathlib import Path

from tfis.backtest.hsre_market_context import (
    NiftyHsreMarketContextBuilder,
    packet_to_dict,
)
from tfis.backtest.nifty_hsre_data_adapter import NiftyHsreHistoricalMarketDataProvider


def _write_spot(
    root: Path,
    session: date,
    rows: list[tuple[str, float, float, float, float]],
) -> Path:
    path = root / "spot" / f"{session.year}" / f"{session.month}" / f"nifty_spot{session:%d_%m_%Y}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["date,time,symbol,open,high,low,close"]
    for raw_time, open_, high, low, close in rows:
        lines.append(f"{session.isoformat()},{raw_time},NIFTY,{open_},{high},{low},{close}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_session(
    root: Path,
    session: date,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
) -> None:
    _write_spot(
        root,
        session,
        [
            ("09:15:00", open_, high, low, close),
            ("15:30:00", close, close, close, close),
        ],
    )


def _builder(root: Path) -> NiftyHsreMarketContextBuilder:
    return NiftyHsreMarketContextBuilder(NiftyHsreHistoricalMarketDataProvider(root))


def test_market_levels_use_completed_prior_sessions_and_partial_current_day(tmp_path: Path) -> None:
    for day, high, low in [
        (1, 101.0, 91.0),
        (2, 102.0, 92.0),
        (3, 103.0, 93.0),
        (4, 104.0, 94.0),
    ]:
        _write_session(tmp_path, date(2024, 1, day), open_=100.0, high=high, low=low, close=100.0)
    _write_spot(
        tmp_path,
        date(2024, 1, 5),
        [
            ("09:15:00", 100.0, 105.0, 99.0, 101.0),
            ("09:16:00", 101.0, 106.0, 98.0, 102.0),
            ("09:17:00", 102.0, 999.0, 1.0, 103.0),
        ],
    )

    packet = _builder(tmp_path).build_context(session_date=date(2024, 1, 5))

    assert packet.market_levels is not None
    assert packet.market_levels.d2hh == 104.0
    assert packet.market_levels.d3hh == 104.0
    assert packet.market_levels.d4hh == 104.0
    assert packet.market_levels.d4ll == 91.0
    assert packet.market_levels.current_day_high == 106.0
    assert packet.market_levels.current_day_low == 98.0
    assert packet.current_day_high_through_evaluation == 106.0
    assert packet.current_day_low_through_evaluation == 98.0
    assert packet.current_day_provenance is not None
    assert packet.current_day_provenance.last_timestamp == "2024-01-05T09:16:00"


def test_context_at_0925_excludes_0926_extreme(tmp_path: Path) -> None:
    for offset, session in enumerate(
        [date(2023, 12, 26), date(2023, 12, 27), date(2023, 12, 28), date(2023, 12, 29)],
        start=1,
    ):
        _write_session(tmp_path, session, open_=100.0, high=100.0 + offset, low=90.0, close=99.0)
    _write_spot(
        tmp_path,
        date(2024, 1, 1),
        [
            ("09:15:00", 100.0, 101.0, 99.0, 100.0),
            ("09:25:00", 100.0, 103.0, 98.0, 102.0),
            ("09:26:00", 102.0, 777.0, 7.0, 103.0),
        ],
    )

    packet = _builder(tmp_path).build_context(
        session_date=date(2024, 1, 1),
        evaluation_time=time(9, 25),
    )

    assert packet.market_levels is not None
    assert packet.market_levels.current_day_high == 103.0
    assert packet.market_levels.current_day_low == 98.0
    assert packet.current_day_provenance is not None
    assert packet.current_day_provenance.last_timestamp == "2024-01-01T09:25:00"


def test_weekly_and_monthly_provenance_uses_exact_observed_partial_inputs(tmp_path: Path) -> None:
    for session in [date(2023, 12, 26), date(2023, 12, 27), date(2023, 12, 28), date(2023, 12, 29)]:
        _write_session(tmp_path, session, open_=95.0, high=100.0, low=90.0, close=96.0)
    _write_spot(
        tmp_path,
        date(2024, 1, 1),
        [
            ("09:15:00", 100.0, 101.0, 99.0, 100.0),
            ("09:16:00", 100.0, 103.0, 99.0, 102.0),
            ("15:30:00", 102.0, 999.0, 1.0, 103.0),
        ],
    )

    packet = _builder(tmp_path).build_context(session_date=date(2024, 1, 1))

    assert [item.label for item in packet.weekly_context_provenance] == ["2023-W52", "2024-W01"]
    assert [item.label for item in packet.monthly_context_provenance] == ["2023-12", "2024-01"]
    assert packet.weekly_context_provenance[-1].source_sessions == ("2024-01-01",)
    assert packet.weekly_context_provenance[-1].last_timestamp == "2024-01-01T09:16:00"
    assert packet.monthly_context_provenance[-1].source_sessions == ("2024-01-01",)
    assert packet.monthly_context_provenance[-1].last_timestamp == "2024-01-01T09:16:00"


def test_insufficient_daily_lookback_fails_closed(tmp_path: Path) -> None:
    _write_spot(
        tmp_path,
        date(2024, 1, 1),
        [("09:15:00", 100.0, 101.0, 99.0, 100.0), ("09:16:00", 100.0, 101.0, 99.0, 100.0)],
    )

    packet = _builder(tmp_path).build_context(session_date=date(2024, 1, 1))

    assert packet.context_status == "INSUFFICIENT_DAILY_LOOKBACK"
    assert packet.market_levels is None
    assert packet.monthly_status is None


def test_missing_previous_month_fails_closed_without_s23_execution(tmp_path: Path) -> None:
    for day in range(1, 6):
        _write_session(tmp_path, date(2024, 1, day), open_=100.0, high=101.0, low=99.0, close=100.0)
    _write_spot(
        tmp_path,
        date(2024, 1, 8),
        [("09:15:00", 100.0, 102.0, 99.0, 101.0), ("09:16:00", 101.0, 103.0, 99.0, 102.0)],
    )

    packet = _builder(tmp_path).build_context(session_date=date(2024, 1, 8))

    assert packet.market_levels is not None
    assert packet.context_status == "INSUFFICIENT_MONTHLY_LOOKBACK"
    assert packet.monthly_status is None


def test_unknown_monthly_status_fails_closed(tmp_path: Path) -> None:
    for session in [date(2023, 12, 26), date(2023, 12, 27), date(2023, 12, 28), date(2023, 12, 29)]:
        _write_session(tmp_path, session, open_=95.0, high=100.0, low=90.0, close=95.0)
    _write_spot(
        tmp_path,
        date(2024, 1, 1),
        [("09:15:00", 95.0, 99.0, 91.0, 95.0), ("09:16:00", 95.0, 100.0, 90.0, 95.0)],
    )

    packet = _builder(tmp_path).build_context(session_date=date(2024, 1, 1))

    assert packet.context_status == "INSUFFICIENT_MONTHLY_STATUS_LOOKBACK"
    assert packet.monthly_status == "UNKNOWN"


def test_stable_packet_hash_and_packet_dict_are_deterministic(tmp_path: Path) -> None:
    for session in [date(2023, 12, 26), date(2023, 12, 27), date(2023, 12, 28), date(2023, 12, 29)]:
        _write_session(tmp_path, session, open_=95.0, high=100.0, low=90.0, close=96.0)
    _write_spot(
        tmp_path,
        date(2024, 1, 1),
        [("09:15:00", 100.0, 101.0, 99.0, 100.0), ("09:16:00", 100.0, 103.0, 99.0, 102.0)],
    )
    builder = _builder(tmp_path)

    first = builder.build_context(session_date=date(2024, 1, 1))
    second = builder.build_context(session_date=date(2024, 1, 1))

    assert builder.stable_packet_hash(first) == builder.stable_packet_hash(second)
    assert packet_to_dict(first) == packet_to_dict(second)
    assert first.context_status == "READY"
    assert first.monthly_status == "BULL_CF"


def test_january_eligibility_discovers_first_ready_dates(tmp_path: Path) -> None:
    for session in [date(2023, 12, 26), date(2023, 12, 27), date(2023, 12, 28), date(2023, 12, 29)]:
        _write_session(tmp_path, session, open_=95.0, high=100.0, low=90.0, close=96.0)
    for session in [date(2024, 1, 1), date(2024, 1, 2)]:
        _write_spot(
            tmp_path,
            session,
            [("09:15:00", 100.0, 101.0, 99.0, 100.0), ("09:16:00", 100.0, 103.0, 99.0, 102.0)],
        )

    eligibility = _builder(tmp_path).discover_january_eligibility(year=2024)

    assert eligibility.first_underlying_lookback_ready == "2024-01-01"
    assert eligibility.first_monthly_status_ready == "2024-01-01"
    assert eligibility.first_fully_context_ready == "2024-01-01"
    assert eligibility.evaluated_sessions[0]["context_status"] == "READY"
