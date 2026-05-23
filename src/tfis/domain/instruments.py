from __future__ import annotations

from dataclasses import dataclass

from .enums import Segment


@dataclass(frozen=True, slots=True)
class InstrumentRef:
    symbol: str
    segment: Segment

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must be a non-empty string")
