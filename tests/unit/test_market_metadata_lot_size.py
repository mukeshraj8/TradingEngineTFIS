from __future__ import annotations

from datetime import date

import pytest

from tfis.market_metadata import effective_lot_size, minimum_oi_units


@pytest.mark.parametrize(
    ("session_date", "expected"),
    [
        (date(2021, 6, 30), 75),
        (date(2021, 7, 1), 50),
        (date(2024, 3, 31), 50),
        (date(2024, 4, 1), 25),
        (date(2024, 10, 31), 25),
        (date(2024, 11, 1), 75),
        (date(2025, 12, 31), 75),
        (date(2026, 1, 1), 65),
    ],
)
def test_nifty_effective_lot_size_boundaries(session_date: date, expected: int) -> None:
    assert effective_lot_size("NIFTY", session_date) == expected


@pytest.mark.parametrize(
    ("session_date", "expected"),
    [
        (date(2024, 1, 3), 25000),
        (date(2024, 4, 1), 12500),
        (date(2024, 11, 1), 37500),
        (date(2026, 1, 1), 32500),
    ],
)
def test_nifty_minimum_oi_units(session_date: date, expected: int) -> None:
    assert minimum_oi_units("NIFTY", session_date) == expected


@pytest.mark.parametrize(
    ("session_date", "expected"),
    [
        (date(2023, 6, 30), 25),
        (date(2023, 7, 1), 15),
        (date(2024, 10, 31), 15),
        (date(2024, 11, 1), 30),
        (date(2025, 6, 30), 30),
        (date(2025, 7, 1), 35),
        (date(2025, 12, 31), 35),
        (date(2026, 1, 1), 30),
    ],
)
def test_banknifty_effective_lot_size_boundaries(session_date: date, expected: int) -> None:
    assert effective_lot_size("BANKNIFTY", session_date) == expected


@pytest.mark.parametrize(
    ("session_date", "expected"),
    [
        (date(2024, 1, 18), 6000),
        (date(2024, 11, 1), 12000),
        (date(2025, 7, 1), 14000),
        (date(2026, 1, 1), 12000),
    ],
)
def test_banknifty_minimum_oi_units(session_date: date, expected: int) -> None:
    assert minimum_oi_units("BANKNIFTY", session_date, minimum_lots=400) == expected
