from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class UnderlyingHistoryBar:
    symbol: str
    bar_start: datetime
    bar_end: datetime
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None = None
    source_id: str | None = None
