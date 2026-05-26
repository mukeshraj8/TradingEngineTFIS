from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from tfis.backtest import (
    BacktestCsvError,
    build_contract_intraday_lookup,
    load_contract_intraday_bars_csv,
    resolve_contract_intraday_bars,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "backtest" / "s23_contract_intraday.csv"


def test_contract_intraday_loader_parses_fixture_rows() -> None:
    bars = load_contract_intraday_bars_csv(FIXTURE_PATH)

    assert bars
    assert bars[0].symbol == "NIFTY_20260528_22100_CE"
    assert bars[0].timestamp == datetime(2026, 5, 18, 9, 20)
    assert bars[0].low == pytest.approx(212.0)


def test_contract_intraday_lookup_resolves_symbol_keyed_bars() -> None:
    bars = load_contract_intraday_bars_csv(FIXTURE_PATH)
    lookup = build_contract_intraday_lookup(bars)

    resolved = resolve_contract_intraday_bars(
        lookup,
        session_date=date(2026, 5, 18),
        symbol="NIFTY_20260528_22100_CE",
        after_timestamp=datetime(2026, 5, 18, 9, 20),
    )

    assert [bar.timestamp.isoformat() for bar in resolved] == [
        "2026-05-18T09:25:00",
        "2026-05-18T09:30:00",
    ]


def test_contract_intraday_loader_fails_on_missing_required_column(
) -> None:
    tmp_dir = ROOT / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    bad_csv = tmp_dir / "bad_contract_intraday.csv"
    bad_csv.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,close,volume",
                "2026-05-18T09:20:00,220,226,212,218,100",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(BacktestCsvError, match="Missing required columns"):
        load_contract_intraday_bars_csv(bad_csv)
