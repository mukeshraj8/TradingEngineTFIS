from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from tfis.backtest.hsre_option_references import (
    NiftyHsreSelectedContractReferenceBuilder,
    option_reference_packet_to_dict,
)
from tfis.backtest.nifty_hsre_data_adapter import (
    NiftyHsreHistoricalMarketDataProvider,
    parse_nifty_option_symbol,
)


def _write_options(
    root: Path,
    session: date,
    rows: list[tuple[str, str, float, float, float, float, int, int]],
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


def _add_contract_day(
    root: Path,
    session: date,
    symbol: str,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    extra_rows: list[tuple[str, str, float, float, float, float, int, int]] | None = None,
) -> None:
    rows = [
        ("09:15:00", symbol, open_, high - 1.0, low + 1.0, open_ + 1.0, 100000, 10),
        ("09:16:00", symbol, open_ + 1.0, high, low, close, 100000, 11),
    ]
    rows.extend(extra_rows or [])
    _write_options(root, session, rows)


def _builder(root: Path) -> NiftyHsreSelectedContractReferenceBuilder:
    return NiftyHsreSelectedContractReferenceBuilder(
        NiftyHsreHistoricalMarketDataProvider(root)
    )


def test_same_contract_2d_and_3d_references_exclude_current_day(tmp_path: Path) -> None:
    identity = parse_nifty_option_symbol("NIFTY04JAN2421700CE")
    for session, high, low in [
        (date(2024, 1, 1), 101.0, 91.0),
        (date(2024, 1, 2), 102.0, 92.0),
        (date(2024, 1, 3), 103.0, 93.0),
    ]:
        _add_contract_day(tmp_path, session, identity.raw_symbol, open_=95.0, high=high, low=low, close=99.0)
    _add_contract_day(
        tmp_path,
        date(2024, 1, 4),
        identity.raw_symbol,
        open_=95.0,
        high=999.0,
        low=1.0,
        close=99.0,
    )

    packet = _builder(tmp_path).build_references(
        session_date=date(2024, 1, 4),
        identity=identity,
    )

    assert packet.status == "READY"
    assert packet.prior_sessions_used == ("2024-01-01", "2024-01-02", "2024-01-03")
    assert packet.opt_prv_2dhh == 103.0
    assert packet.opt_prv_2dll == 92.0
    assert packet.opt_prv_3dhh == 103.0
    assert packet.opt_prv_3dll == 91.0
    assert "2024-01-04" not in packet.prior_exact_contract_sessions_available


def test_expiry_strike_and_option_side_are_never_substituted(tmp_path: Path) -> None:
    identity = parse_nifty_option_symbol("NIFTY04JAN2421700CE")
    wrong_rows = [
        ("09:16:00", "NIFTY04JAN2421750CE", 1.0, 999.0, 1.0, 1.0, 100000, 1),
        ("09:16:00", "NIFTY11JAN2421700CE", 1.0, 888.0, 2.0, 1.0, 100000, 1),
        ("09:16:00", "NIFTY04JAN2421700PE", 1.0, 777.0, 3.0, 1.0, 100000, 1),
    ]
    for session, high, low in [
        (date(2024, 1, 1), 101.0, 91.0),
        (date(2024, 1, 2), 102.0, 92.0),
        (date(2024, 1, 3), 103.0, 93.0),
    ]:
        _add_contract_day(
            tmp_path,
            session,
            identity.raw_symbol,
            open_=95.0,
            high=high,
            low=low,
            close=99.0,
            extra_rows=wrong_rows,
        )

    packet = _builder(tmp_path).build_references(
        session_date=date(2024, 1, 4),
        identity=identity,
    )

    assert packet.status == "READY"
    assert packet.opt_prv_3dhh == 103.0
    assert packet.opt_prv_3dll == 91.0
    assert all(item.high < 777.0 for item in packet.prior_session_provenance)


def test_future_sessions_are_excluded_from_references(tmp_path: Path) -> None:
    identity = parse_nifty_option_symbol("NIFTY04JAN2421700PE")
    for session, high, low in [
        (date(2024, 1, 1), 51.0, 41.0),
        (date(2024, 1, 2), 52.0, 42.0),
        (date(2024, 1, 3), 53.0, 43.0),
        (date(2024, 1, 5), 999.0, 1.0),
    ]:
        _add_contract_day(tmp_path, session, identity.raw_symbol, open_=45.0, high=high, low=low, close=49.0)

    packet = _builder(tmp_path).build_references(
        session_date=date(2024, 1, 4),
        identity=identity,
    )

    assert packet.status == "READY"
    assert packet.opt_prv_3dhh == 53.0
    assert packet.opt_prv_3dll == 41.0
    assert "2024-01-05" not in packet.prior_exact_contract_sessions_available


def test_insufficient_option_lookback_fails_closed_without_defaults(tmp_path: Path) -> None:
    identity = parse_nifty_option_symbol("NIFTY04JAN2421700CE")
    for session, high, low in [
        (date(2024, 1, 2), 102.0, 92.0),
        (date(2024, 1, 3), 103.0, 93.0),
    ]:
        _add_contract_day(tmp_path, session, identity.raw_symbol, open_=95.0, high=high, low=low, close=99.0)

    packet = _builder(tmp_path).build_references(
        session_date=date(2024, 1, 4),
        identity=identity,
    )

    assert packet.status == "INSUFFICIENT_OPTION_LOOKBACK"
    assert packet.two_day_ready is True
    assert packet.three_day_ready is False
    assert packet.opt_prv_2dhh is None
    assert packet.opt_prv_2dll is None
    assert packet.opt_prv_3dhh is None
    assert packet.opt_prv_3dll is None


def test_expiry_roll_uses_actual_same_contract_pre_roll_history(tmp_path: Path) -> None:
    identity = parse_nifty_option_symbol("NIFTY11JAN2421700CE")
    for session, high, low in [
        (date(2024, 1, 2), 202.0, 182.0),
        (date(2024, 1, 3), 203.0, 183.0),
        (date(2024, 1, 4), 204.0, 184.0),
    ]:
        _add_contract_day(tmp_path, session, identity.raw_symbol, open_=190.0, high=high, low=low, close=195.0)

    packet = _builder(tmp_path).build_references(
        session_date=date(2024, 1, 5),
        identity=identity,
    )

    assert packet.status == "READY"
    assert packet.prior_sessions_used == ("2024-01-02", "2024-01-03", "2024-01-04")
    assert packet.opt_prv_2dhh == 204.0
    assert packet.opt_prv_2dll == 183.0
    assert packet.opt_prv_3dhh == 204.0
    assert packet.opt_prv_3dll == 182.0


def test_expiry_roll_without_actual_same_contract_history_fails_closed(tmp_path: Path) -> None:
    identity = parse_nifty_option_symbol("NIFTY11JAN2421700PE")
    _add_contract_day(
        tmp_path,
        date(2024, 1, 4),
        "NIFTY04JAN2421700PE",
        open_=190.0,
        high=999.0,
        low=1.0,
        close=195.0,
    )

    packet = _builder(tmp_path).build_references(
        session_date=date(2024, 1, 5),
        identity=identity,
    )

    assert packet.status == "INSUFFICIENT_OPTION_LOOKBACK"
    assert packet.prior_exact_contract_sessions_available == ()


def test_provenance_records_source_timestamp_ranges_and_files(tmp_path: Path) -> None:
    identity = parse_nifty_option_symbol("NIFTY04JAN2421700CE")
    for session, high, low in [
        (date(2024, 1, 1), 101.0, 91.0),
        (date(2024, 1, 2), 102.0, 92.0),
        (date(2024, 1, 3), 103.0, 93.0),
    ]:
        _add_contract_day(tmp_path, session, identity.raw_symbol, open_=95.0, high=high, low=low, close=99.0)

    packet = _builder(tmp_path).build_references(
        session_date=date(2024, 1, 4),
        identity=identity,
    )

    first = packet.prior_session_provenance[0]
    assert first.session_date == "2024-01-01"
    assert first.first_timestamp == "2024-01-01T09:15:00"
    assert first.last_timestamp == "2024-01-01T09:16:00"
    assert first.observed_minutes == 2
    assert first.missing_minutes_synthesized is False
    assert first.source_files[0].endswith("nifty_options_01_01_2024.csv")


def test_deterministic_hash_and_dict_are_stable(tmp_path: Path) -> None:
    identity = parse_nifty_option_symbol("NIFTY04JAN2421700CE")
    for session, high, low in [
        (date(2024, 1, 1), 101.0, 91.0),
        (date(2024, 1, 2), 102.0, 92.0),
        (date(2024, 1, 3), 103.0, 93.0),
    ]:
        _add_contract_day(tmp_path, session, identity.raw_symbol, open_=95.0, high=high, low=low, close=99.0)
    builder = _builder(tmp_path)

    first = builder.build_references(session_date=date(2024, 1, 4), identity=identity)
    second = builder.build_references(session_date=date(2024, 1, 4), identity=identity)

    assert builder.stable_packet_hash(first) == builder.stable_packet_hash(second)
    assert option_reference_packet_to_dict(first) == option_reference_packet_to_dict(second)


def test_ready_packet_converts_to_existing_option_levels_snapshot(tmp_path: Path) -> None:
    identity = parse_nifty_option_symbol("NIFTY04JAN2421700CE")
    for session, high, low in [
        (date(2024, 1, 1), 101.0, 91.0),
        (date(2024, 1, 2), 102.0, 92.0),
        (date(2024, 1, 3), 103.0, 93.0),
    ]:
        _add_contract_day(tmp_path, session, identity.raw_symbol, open_=95.0, high=high, low=low, close=99.0)
    builder = _builder(tmp_path)
    packet = builder.build_references(session_date=date(2024, 1, 4), identity=identity)

    snapshot = builder.to_option_levels_snapshot(
        packet,
        timestamp=datetime(2024, 1, 4, 9, 16),
    )

    assert snapshot.timestamp == datetime(2024, 1, 4, 9, 16)
    assert snapshot.opt_levels == {
        "OPT_PRV_2DHH": 103.0,
        "OPT_PRV_2DLL": 92.0,
        "OPT_PRV_3DHH": 103.0,
        "OPT_PRV_3DLL": 91.0,
    }


def test_insufficient_packet_cannot_convert_to_option_levels_snapshot(tmp_path: Path) -> None:
    identity = parse_nifty_option_symbol("NIFTY04JAN2421700CE")
    _add_contract_day(tmp_path, date(2024, 1, 3), identity.raw_symbol, open_=95.0, high=103.0, low=93.0, close=99.0)
    builder = _builder(tmp_path)
    packet = builder.build_references(session_date=date(2024, 1, 4), identity=identity)

    with pytest.raises(ValueError, match="Cannot convert"):
        builder.to_option_levels_snapshot(packet)
