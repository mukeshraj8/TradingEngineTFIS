from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def normalize_executable_price(price: Decimal | None, tick_size: Decimal) -> Decimal | None:
    if price is None:
        return None
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")
    ticks = (price / tick_size).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return (ticks * tick_size).quantize(tick_size)
