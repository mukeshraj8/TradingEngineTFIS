from __future__ import annotations

from datetime import date


NIFTY_MINIMUM_OI_LOTS = 500


def effective_lot_size(instrument: str, session_date: date) -> int:
    """Return the effective lot size for an instrument on a trading date."""

    symbol = instrument.strip().upper()
    if symbol == "NIFTY":
        if session_date < date(2021, 7, 1):
            return 75
        if session_date <= date(2024, 3, 31):
            return 50
        if session_date <= date(2024, 10, 31):
            return 25
        if session_date <= date(2025, 12, 31):
            return 75
        return 65
    if symbol == "BANKNIFTY":
        if session_date <= date(2023, 6, 30):
            return 25
        if session_date <= date(2024, 10, 31):
            return 15
        if session_date <= date(2025, 6, 30):
            return 30
        if session_date <= date(2025, 12, 31):
            return 35
        return 30
    raise ValueError(f"No effective lot-size schedule configured for {instrument!r}")


def minimum_oi_units(
    instrument: str,
    session_date: date,
    *,
    minimum_lots: int = NIFTY_MINIMUM_OI_LOTS,
) -> int:
    return int(minimum_lots) * effective_lot_size(instrument, session_date)
