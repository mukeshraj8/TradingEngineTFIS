from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from tfis.backtest import (
    OptionChainContract,
    OptionChainSelector,
    OptionSelectionRequest,
    load_option_chain_csv,
)
from tfis.domain.enums import OptionType


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "backtest" / "s23_option_chain.csv"


def _contract(
    *,
    strike: int,
    ltp: float,
    bid: float,
    ask: float,
    oi: int,
    option_type: OptionType = OptionType.CALL,
    timestamp: datetime = datetime(2026, 5, 18, 15, 30),
    symbol: str = "NIFTY_TEST",
    expiry: date = date(2026, 5, 28),
) -> OptionChainContract:
    return OptionChainContract(
        timestamp=timestamp,
        symbol=symbol,
        option_type=option_type,
        strike=strike,
        expiry=expiry,
        bid=bid,
        ask=ask,
        ltp=ltp,
        oi=oi,
        volume=100,
    )


def _request(
    *,
    option_type: OptionType = OptionType.CALL,
    start_strike: int = 23047,
    end_strike: int = 21949,
    ideal_premium: float = 263.4,
    minimum_premium: float = 197.55,
    minimum_oi: int = 500,
    timestamp: datetime = datetime(2026, 5, 18, 15, 30),
    expiry_dates: tuple[date, ...] = (),
) -> OptionSelectionRequest:
    return OptionSelectionRequest(
        option_type=option_type,
        start_strike=start_strike,
        end_strike=end_strike,
        ideal_premium=ideal_premium,
        minimum_premium=minimum_premium,
        minimum_oi=minimum_oi,
        timestamp=timestamp,
        expiry_dates=expiry_dates,
    )


def test_option_chain_csv_fixture_loads() -> None:
    contracts = load_option_chain_csv(FIXTURE_PATH)

    assert len(contracts) == 20
    assert contracts[0].timestamp == datetime(2026, 5, 18, 15, 30)
    assert contracts[0].option_type in {OptionType.CALL, OptionType.PUT}


def test_selects_first_minimum_premium_in_reverse_rule_order() -> None:
    selector = OptionChainSelector()
    result = selector.select(
        _request(),
        [
            _contract(strike=22000, ltp=262.0, bid=260.0, ask=266.0, oi=800),
            _contract(strike=22100, ltp=263.0, bid=261.0, ask=265.0, oi=700),
        ],
    )

    assert result.selected is True
    assert result.selected_contract is not None
    assert result.selected_contract.strike == 22000
    assert result.selection_reason == (
        "Selected first strike meeting minimum premium in reverse rule-sheet search order."
    )


def test_rejects_low_oi_contracts() -> None:
    selector = OptionChainSelector()
    result = selector.select(
        _request(minimum_oi=500),
        [
            _contract(strike=22000, ltp=262.0, bid=260.0, ask=266.0, oi=200),
            _contract(strike=22100, ltp=263.0, bid=261.0, ask=265.0, oi=300),
        ],
    )

    assert result.selected is False
    assert result.selection_reason == "No option-chain contracts meet minimum_oi 500"


def test_rejects_contracts_below_minimum_premium() -> None:
    selector = OptionChainSelector()
    result = selector.select(
        _request(minimum_premium=250.0),
        [
            _contract(strike=22000, ltp=240.0, bid=238.0, ask=242.0, oi=800),
            _contract(strike=22100, ltp=245.0, bid=243.0, ask=247.0, oi=900),
        ],
    )

    assert result.selected is False
    assert result.selection_reason == "No option-chain contracts meet minimum_premium 250.00"


def test_falls_back_to_next_expiry_when_near_expiry_fails() -> None:
    selector = OptionChainSelector()
    result = selector.select(
        _request(
            expiry_dates=(date(2026, 5, 28), date(2026, 6, 4)),
            minimum_premium=250.0,
        ),
        [
            _contract(
                strike=22100,
                ltp=245.0,
                bid=243.0,
                ask=247.0,
                oi=900,
                symbol="NIFTY_20260528_22100_CE",
                expiry=date(2026, 5, 28),
            ),
            _contract(
                strike=22100,
                ltp=265.0,
                bid=263.0,
                ask=267.0,
                oi=900,
                symbol="NIFTY_20260604_22100_CE",
                expiry=date(2026, 6, 4),
            ),
        ],
    )

    assert result.selected is True
    assert result.selected_contract is not None
    assert result.selected_contract.symbol == "NIFTY_20260604_22100_CE"
    assert result.attempted_expiries == (date(2026, 5, 28), date(2026, 6, 4))
    assert "Near expiry 2026-05-28 failed" in result.selection_reason


def test_handles_descending_strike_ranges() -> None:
    selector = OptionChainSelector()
    result = selector.select(
        _request(start_strike=23047, end_strike=21949),
        [
            _contract(strike=21800, ltp=263.0, bid=261.0, ask=265.0, oi=900),
            _contract(strike=22100, ltp=264.0, bid=262.0, ask=266.0, oi=900),
        ],
    )

    assert result.selected is True
    assert result.selected_contract is not None
    assert result.selected_contract.strike == 22100


def test_tie_breaks_by_spread_then_oi() -> None:
    selector = OptionChainSelector()
    request = _request(ideal_premium=263.0)

    spread_winner = selector.select(
        request,
        [
            _contract(strike=22000, ltp=263.0, bid=260.0, ask=266.0, oi=1200),
            _contract(strike=22100, ltp=263.0, bid=261.0, ask=265.0, oi=700),
        ],
    )
    assert spread_winner.selected_contract is not None
    assert spread_winner.selected_contract.strike == 22100

    oi_winner = selector.select(
        request,
        [
            _contract(strike=22000, ltp=263.0, bid=261.0, ask=265.0, oi=800),
            _contract(strike=22100, ltp=263.0, bid=261.0, ask=265.0, oi=1200),
        ],
    )
    assert oi_winner.selected_contract is not None
    assert oi_winner.selected_contract.strike == 22100
