from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from tfis.reference_data.instrument_master import (
    classify_monthly_expiries,
    normalize_symbol_master_rows,
)


IST = ZoneInfo("Asia/Kolkata")


def test_reliance_symbol_master_rows_preserve_required_metadata() -> None:
    downloaded_at = datetime(2026, 8, 2, 9, 0, tzinfo=IST)
    rows = [
        {
            "symbol": "NSE:RELIANCE-EQ",
            "segment": "NSE",
            "instrument_type": "EQUITY",
            "underlying": "RELIANCE",
            "fyToken": "RELIANCE_CASH_TOKEN",
            "tickSize": "0.05",
        },
        {
            "symbol": "NSE:RELIANCE26AUG3000CE",
            "segment": "NSEFO",
            "instrument_type": "OPTION",
            "underlying": "RELIANCE",
            "expiry": "2026-08-27",
            "strike": "3000",
            "option_type": "CE",
            "lotSize": "250",
            "tickSize": "0.05",
            "fyToken": "RELIANCE_AUG_CE_TOKEN",
        },
        {
            "symbol": "NSE:RELIANCE26AUG3000PE",
            "segment": "NSEFO",
            "instrument_type": "OPTION",
            "underlying": "RELIANCE",
            "expiry": "2026-08-27",
            "strike": "3000",
            "option_type": "PE",
            "lotSize": "250",
            "tickSize": "0.05",
            "fyToken": "RELIANCE_AUG_PE_TOKEN",
        },
    ]

    records = normalize_symbol_master_rows(
        rows,
        exchange="NSEFO",
        source_version="fixture:2026-08-02",
        downloaded_at=downloaded_at,
    )

    option_records = [record for record in records if record.option_type]
    assert len(option_records) == 2
    assert {record.option_type for record in option_records} == {"CALL", "PUT"}
    assert {record.lot_size for record in option_records} == {250}
    assert {record.tick_size for record in option_records} == {Decimal("0.05")}
    assert option_records[0].source_hash != option_records[1].source_hash


def test_reliance_lookup_and_monthly_expiry_classification() -> None:
    downloaded_at = datetime(2026, 8, 2, 9, 0, tzinfo=IST)
    records = normalize_symbol_master_rows(
        [
            {
                "symbol": "NSE:RELIANCE26AUG3000CE",
                "underlying": "RELIANCE",
                "expiry": "2026-08-27",
                "strike": "3000",
                "option_type": "CE",
                "lotSize": "250",
                "tickSize": "0.05",
            },
            {
                "symbol": "NSE:RELIANCE26SEP3000CE",
                "underlying": "RELIANCE",
                "expiry": "2026-09-24",
                "strike": "3000",
                "option_type": "CE",
                "lotSize": "250",
                "tickSize": "0.05",
            },
            {
                "symbol": "NSE:TCS26AUG3000CE",
                "underlying": "TCS",
                "expiry": "2026-08-27",
                "strike": "3000",
                "option_type": "CE",
                "lotSize": "175",
                "tickSize": "0.05",
            },
        ],
        exchange="NSEFO",
        source_version="fixture:2026-08-02",
        downloaded_at=downloaded_at,
    )

    classification = classify_monthly_expiries(records, underlying="RELIANCE", as_of=date(2026, 8, 2))

    assert classification.near_monthly_expiry == date(2026, 8, 27)
    assert classification.next_monthly_expiry == date(2026, 9, 24)
    assert classification.warnings == ()


def test_symbol_master_csv_parsing_and_inference_for_option_symbol() -> None:
    downloaded_at = datetime(2026, 8, 2, 9, 0, tzinfo=IST)
    csv_text = (
        "symbol,expiry,strike,option_type,lotSize,tickSize,fyToken\n"
        "NSE:RELIANCE26AUG3000CE,2026-08-27,3000,CE,250,0.05,TOKEN1\n"
    )

    (record,) = normalize_symbol_master_rows(
        csv_text,
        exchange="NSEFO",
        source_version="fixture:csv",
        downloaded_at=downloaded_at,
    )

    assert record.underlying == "RELIANCE"
    assert record.expiry == date(2026, 8, 27)
    assert record.option_type == "CALL"
    assert record.instrument_token == "TOKEN1"


def test_fyers_headerless_symbol_master_row_is_normalized() -> None:
    downloaded_at = datetime(2026, 8, 2, 9, 0, tzinfo=IST)
    csv_text = (
        "1011260825141595,RELIANCE 25 Aug 26 760 CE,15,500,0.05,,0915-1540|1815-1915:,"
        "2026-07-31,1787652000,NSE:RELIANCE26AUG760CE,10,11,141595,RELIANCE,2885,760.0,"
        "CE,10100000002885,None,0,0.0\n"
    )

    (record,) = normalize_symbol_master_rows(
        csv_text,
        exchange="NSEFO",
        source_version="fyers-symbol-master:NSEFO:2026-08-02",
        downloaded_at=downloaded_at,
    )

    assert record.source_symbol == "NSE:RELIANCE26AUG760CE"
    assert record.instrument_id == "1011260825141595"
    assert record.instrument_token == "141595"
    assert record.instrument_type == "OPTION"
    assert record.underlying == "RELIANCE"
    assert record.expiry == date(2026, 8, 25)
    assert record.strike == Decimal("760.0")
    assert record.option_type == "CALL"
    assert record.lot_size == 500
    assert record.tick_size == Decimal("0.05")
