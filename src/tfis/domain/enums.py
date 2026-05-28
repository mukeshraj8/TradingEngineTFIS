from __future__ import annotations

from enum import Enum


class Segment(str, Enum):
    FUTURES = "FUTURES"
    OPTIONS_BUY = "OPTIONS_BUY"
    OPTIONS_SELL = "OPTIONS_SELL"
    EQUITY = "EQUITY"


class MonthlyStatus(str, Enum):
    BULL = "BULL"
    BULL_CF = "BULL_CF"
    BEAR = "BEAR"
    BEAR_CF = "BEAR_CF"
    UNKNOWN = "UNKNOWN"


class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class ExpiryType(str, Enum):
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class RolloverPolicy(str, Enum):
    T_MINUS_1 = "T_MINUS_1"
    T_MINUS_2 = "T_MINUS_2"


class RoundingMode(str, Enum):
    ROUND_UP = "ROUND_UP"
    ROUND_DOWN = "ROUND_DOWN"
    NEAREST = "NEAREST"
