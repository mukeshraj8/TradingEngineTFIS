from __future__ import annotations

from datetime import date
from pathlib import Path

from tfis.domain.enums import OptionType
from tfis.tools.historical_market_explorer import (
    HistoricalMarketExplorerService,
    parse_contract_symbol,
)


def _write_spot(
    root: Path,
    session: date,
    rows: list[tuple[str, float, float, float, float]],
    *,
    instrument: str = "NIFTY",
) -> None:
    path = root / "Nifty" / "spot" / f"{session.year}" / f"{session.month}" / f"nifty_spot{session:%d_%m_%Y}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["date,time,symbol,open,high,low,close"]
    for raw_time, open_, high, low, close in rows:
        lines.append(f"{session.isoformat()},{raw_time},{instrument},{open_},{high},{low},{close}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_options(
    root: Path,
    session: date,
    rows: list[tuple[str, str, float, float, float, float, int, int]],
) -> None:
    path = root / "Nifty" / "options" / f"{session.year}" / f"{session.month}" / f"nifty_options_{session:%d_%m_%Y}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["date,time,symbol,open,high,low,close,oi,volume"]
    for raw_time, symbol, open_, high, low, close, oi, volume in rows:
        lines.append(
            f"{session.isoformat()},{raw_time},{symbol},{open_},{high},{low},{close},{oi},{volume}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fixture(root: Path) -> None:
    for index, session in enumerate(
        [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)],
        start=1,
    ):
        _write_spot(
            root,
            session,
            [
                ("09:15:00", 100 + index, 104 + index, 99 + index, 103 + index),
                ("09:16:00", 103 + index, 106 + index, 102 + index, 105 + index),
                ("09:24:00", 105 + index, 108 + index, 101 + index, 106 + index),
                ("09:29:00", 106 + index, 109 + index, 100 + index, 107 + index),
            ],
        )
    for session, base in [
        (date(2024, 1, 2), 20),
        (date(2024, 1, 3), 30),
        (date(2024, 1, 4), 40),
        (date(2024, 1, 5), 50),
    ]:
        _write_options(
            root,
            session,
            [
                ("09:16:00", "NIFTY11JAN2421700CE", base, base + 2, base - 1, base + 1, 1000 + base, 10),
                ("09:24:00", "NIFTY11JAN2421700CE", base + 1, base + 3, base - 2, base + 2, 1100 + base, 20),
                ("09:29:00", "NIFTY11JAN2421700CE", base + 2, base + 4, base - 3, base + 3, 1200 + base, 30),
                ("09:16:00", "NIFTY11JAN2421800CE", base + 10, base + 12, base + 9, base + 11, 900, 5),
                ("09:16:00", "NIFTY11JAN2421700PE", base + 5, base + 7, base + 4, base + 6, 800, 6),
            ],
        )


def test_symbol_parsing_supports_explorer_contract_identity() -> None:
    identity = parse_contract_symbol("NIFTY11JAN2421700CE")

    assert identity.underlying == "NIFTY"
    assert identity.expiry == date(2024, 1, 11)
    assert identity.strike == 21700
    assert identity.option_type is OptionType.CALL


def test_discovery_dropdowns_and_contract_payload(tmp_path: Path) -> None:
    _fixture(tmp_path)
    service = HistoricalMarketExplorerService(tmp_path)

    sessions = service.sessions("NIFTY")
    assert sessions["common_sessions"] == ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    assert service.expiries("NIFTY", date(2024, 1, 5))["expiries"] == ["2024-01-11"]
    assert service.strikes("NIFTY", date(2024, 1, 5), date(2024, 1, 11), OptionType.CALL)["strikes"] == [21700, 21800]

    payload = service.contract_payload(
        instrument="NIFTY",
        session_date=date(2024, 1, 5),
        expiry=date(2024, 1, 11),
        strike=21700,
        option_type=OptionType.CALL,
    )

    assert payload["selection"]["symbol"] == "NIFTY11JAN2421700CE"
    assert payload["summary"]["day_open"] == 50
    assert payload["summary"]["day_high"] == 54
    assert payload["summary"]["day_low"] == 47
    assert payload["summary"]["day_close"] == 53
    assert payload["summary"]["day_volume"] == 60
    assert payload["summary"]["opening_oi"] == 1050
    assert payload["summary"]["closing_oi"] == 1250
    assert payload["minute_marks"]["premium_0916"]["close"] == 51
    assert payload["minute_marks"]["orpt_0924"]["low"] == 48
    assert payload["minute_marks"]["rc_0929"]["high"] == 54
    assert payload["prior_option_history"]["references"]["OPT_PRV_2DHH"] == 44
    assert payload["prior_option_history"]["references"]["OPT_PRV_2DLL"] == 27
    assert payload["prior_option_history"]["references"]["OPT_PRV_3DHH"] == 44
    assert payload["prior_option_history"]["references"]["OPT_PRV_3DLL"] == 17
    assert payload["prior_spot_history"]["references"]["PRV_4DHH"] == 113
    assert payload["s23_workbook_validation"]["historical_lot_size"] == 50
    assert payload["s23_workbook_validation"]["minimum_oi_units"] == 25000
    assert payload["data_quality"] == []


def test_option_chain_snapshot_and_search_order_visualization(tmp_path: Path) -> None:
    _fixture(tmp_path)
    service = HistoricalMarketExplorerService(tmp_path)

    payload = service.option_chain_payload(
        instrument="NIFTY",
        session_date=date(2024, 1, 5),
        expiry=date(2024, 1, 11),
        selected_strike=21700,
        ideal_premium=60,
        minimum_premium=50,
        minimum_oi=1000,
        start_strike=21700,
        end_strike=21800,
    )

    selected = next(row for row in payload["rows"] if row["selected"])
    assert selected["CE_symbol"] == "NIFTY11JAN2421700CE"
    assert selected["CE_ltp"] == 51
    assert selected["CE_meets_minimum"] is True
    assert selected["CE_meets_ideal"] is False
    assert selected["CE_meets_oi"] is True
    assert [row["strike"] for row in payload["search_order"]["start_to_end"]] == [21700, 21800]
    assert [row["strike"] for row in payload["search_order"]["end_to_start"]] == [21800, 21700]


def test_manual_workbench_lot_size_uses_selected_expiry_date(tmp_path: Path) -> None:
    _fixture(tmp_path)
    service = HistoricalMarketExplorerService(tmp_path)

    jan_2024 = service.lot_size_payload(
        instrument="NIFTY",
        reference_date=date(2024, 1, 18),
    )
    jan_2026 = service.lot_size_payload(
        instrument="NIFTY",
        reference_date=date(2026, 1, 1),
    )
    banknifty = service.lot_size_payload(
        instrument="BANKNIFTY",
        reference_date=date(2024, 1, 18),
    )

    assert jan_2024["lot_size"] == 50
    assert jan_2024["source"] == "date_effective_instrument_schedule"
    assert jan_2026["lot_size"] == 65
    assert banknifty["lot_size"] == 15
    assert banknifty["source"] == "date_effective_instrument_schedule"


def test_manual_strike_scan_prefers_first_ideal_then_minimum(tmp_path: Path) -> None:
    _fixture(tmp_path)
    service = HistoricalMarketExplorerService(tmp_path)

    ideal_payload = service.manual_strike_scan_payload(
        instrument="NIFTY",
        session_date=date(2024, 1, 5),
        expiry=date(2024, 1, 11),
        option_type=OptionType.CALL,
        start_strike=21700,
        end_strike=21800,
        history_sessions=2,
        ideal_premium=60,
        minimum_premium=50,
        minimum_oi=800,
    )

    assert ideal_payload["selected"]["strike"] == 21800
    assert ideal_payload["selected"]["selection_stage"] == "ideal"
    row_21700 = next(row for row in ideal_payload["rows"] if row["strike"] == 21700)
    assert row_21700["OPT_PRV_DHH"] == 44
    assert row_21700["OPT_PRV_DLL"] == 27
    assert row_21700["history_ready"] is True

    fallback_payload = service.manual_strike_scan_payload(
        instrument="NIFTY",
        session_date=date(2024, 1, 5),
        expiry=date(2024, 1, 11),
        option_type=OptionType.CALL,
        start_strike=21700,
        end_strike=21800,
        history_sessions=3,
        ideal_premium=60,
        minimum_premium=50,
        minimum_oi=1000,
    )

    assert fallback_payload["selected"]["strike"] == 21700
    assert fallback_payload["selected"]["selection_stage"] == "minimum"


def test_manual_strike_scan_resolves_factor_based_thresholds(tmp_path: Path) -> None:
    _fixture(tmp_path)
    service = HistoricalMarketExplorerService(tmp_path)

    payload = service.manual_strike_scan_payload(
        instrument="NIFTY",
        session_date=date(2024, 1, 5),
        expiry=date(2024, 1, 11),
        option_type=OptionType.CALL,
        start_strike=21700,
        end_strike=21800,
        premium_reference=5000,
        ideal_factor_pct=1.2,
        minimum_factor_pct=0.9,
        minimum_oi=1000,
    )

    assert payload["thresholds"]["ideal_premium"] == 60
    assert payload["thresholds"]["minimum_premium"] == 45
    assert payload["selected"]["strike"] == 21700
    assert payload["selected"]["selection_stage"] == "minimum"


def test_daily_option_history_reports_missing_calendar_dates(tmp_path: Path) -> None:
    _fixture(tmp_path)
    service = HistoricalMarketExplorerService(tmp_path)

    payload = service.daily_option_history_payload(
        instrument="NIFTY",
        session_date=date(2024, 1, 5),
        expiry=date(2024, 1, 11),
        strike=21700,
        option_type=OptionType.CALL,
        from_date=date(2024, 1, 1),
        to_date=date(2024, 1, 5),
    )

    assert payload["available_count"] == 4
    assert payload["missing_count"] == 1
    assert payload["DHH"] == 54
    assert payload["DLL"] == 17
    assert payload["rows"][0]["date"] == "2024-01-01"
    assert payload["rows"][0]["status"] == "MISSING"


def test_missing_minutes_are_reported_without_substitution(tmp_path: Path) -> None:
    session = date(2024, 1, 5)
    _write_spot(tmp_path, session, [("09:16:00", 1, 2, 0.5, 1.5)])
    _write_options(
        tmp_path,
        session,
        [("09:16:00", "NIFTY11JAN2421700CE", 10, 11, 9, 10.5, 1000, 1)],
    )
    service = HistoricalMarketExplorerService(tmp_path)

    payload = service.contract_payload(
        instrument="NIFTY",
        session_date=session,
        expiry=date(2024, 1, 11),
        strike=21700,
        option_type=OptionType.CALL,
    )

    assert payload["minute_marks"]["orpt_0924"]["status"] == "MISSING"
    assert payload["minute_marks"]["rc_0929"]["status"] == "MISSING"
    warning_codes = {item["code"] for item in payload["data_quality"]}
    assert "missing_orpt_0924" in warning_codes
    assert "missing_rc_0929" in warning_codes
    assert "insufficient_exact_contract_lookback" in warning_codes
