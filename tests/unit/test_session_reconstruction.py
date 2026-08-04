from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from tfis.fyers_read_only.models import CompletedCandleSet, FyersCandle, FyersQuote
from tfis.runtime.multi_strategy.session_reconstruction import (
    MARKET_OPEN,
    StrategyTimingPolicy,
    classify_candle_completeness,
    classify_market_session_state,
    reconstruct_option_selling_entry,
    selected_contract_is_authoritative,
)


IST = ZoneInfo("Asia/Calcutta")


def test_market_session_state_uses_current_time_without_marking_pre_open_as_live() -> None:
    assert classify_market_session_state(datetime(2026, 8, 4, 9, 14, 59, tzinfo=IST)) == "PRE_OPEN"
    assert classify_market_session_state(datetime(2026, 8, 4, 9, 15, 0, tzinfo=IST)) == "LIVE"
    assert classify_market_session_state(datetime(2026, 8, 4, 15, 31, 0, tzinfo=IST)) == "POST_CLOSE"


def test_selected_contract_authority_requires_real_exchange_symbol() -> None:
    assert selected_contract_is_authoritative("NSE:RELIANCE26AUG1260CE") is True
    assert selected_contract_is_authoritative("NIFTY_PHASE5C_PUT_FIXTURE") is False
    assert selected_contract_is_authoritative("BANKNIFTY24JAN47000CE") is False


def test_reconstruction_keeps_normal_entry_valid_when_low_never_breaches_entry() -> None:
    now = datetime(2026, 8, 4, 10, 0, tzinfo=IST)
    result = reconstruct_option_selling_entry(
        strategy_instance_id="S22_RELIANCE_INTERNAL_PAPER_A",
        timing_policy=StrategyTimingPolicy(market_open=MARKET_OPEN, orpt_time=time(9, 24, 59), rc_time=time(9, 29, 59)),
        now=now,
        invalid_runtime_classification="INVALID_RUNTIME_CLASSIFICATION",
        selected_contract_authoritative=True,
        base_entry=Decimal("57.50"),
        revised_entry=Decimal("57.00"),
        underlying_bars=_bars("NSE:RELIANCE-EQ", [("09:15", "1300", "1305", "1298", "1302"), ("09:16", "1302", "1304", "1301", "1303")]),
        option_bars=_bars("NSE:RELIANCE26AUG1260CE", [("09:24", "80", "84", "78", "81"), ("09:25", "81", "83", "79", "80")]),
        current_quote=_quote("NSE:RELIANCE26AUG1260CE", "80"),
    )
    assert result.orpt_result == "ORPT_ENTRY_NOT_MISSED"
    assert result.rc_result == "RC_NOT_REQUIRED"
    assert result.current_entry_state == "NORMAL_ENTRY_STILL_VALID"


def test_reconstruction_uses_rc_when_normal_entry_was_missed() -> None:
    now = datetime(2026, 8, 4, 10, 0, tzinfo=IST)
    result = reconstruct_option_selling_entry(
        strategy_instance_id="S22_RELIANCE_INTERNAL_PAPER_A",
        timing_policy=StrategyTimingPolicy(market_open=MARKET_OPEN, orpt_time=time(9, 24, 59), rc_time=time(9, 29, 59)),
        now=now,
        invalid_runtime_classification="INVALID_RUNTIME_CLASSIFICATION",
        selected_contract_authoritative=True,
        base_entry=Decimal("57.50"),
        revised_entry=Decimal("57.00"),
        underlying_bars=_bars("NSE:RELIANCE-EQ", [("09:15", "1300", "1305", "1298", "1302"), ("09:16", "1302", "1304", "1301", "1303")]),
        option_bars=_bars(
                "NSE:RELIANCE26AUG1260CE",
                [
                    ("09:24", "60", "61", "56", "58"),
                    ("09:30", "58", "59", "57.10", "58"),
                    ("09:31", "58", "60", "57.20", "59"),
                ],
        ),
        current_quote=_quote("NSE:RELIANCE26AUG1260CE", "58"),
    )
    assert result.orpt_result == "ORPT_ENTRY_MISSED_WAITING_FOR_RC"
    assert result.rc_result == "RC_ENTRY_STILL_VALID"
    assert result.current_entry_state == "RC_ENTRY_STILL_VALID"


def test_reconstruction_blocks_when_selected_contract_is_not_authoritative() -> None:
    now = datetime(2026, 8, 4, 10, 0, tzinfo=IST)
    result = reconstruct_option_selling_entry(
        strategy_instance_id="S23_NIFTY_INTERNAL_PAPER_A",
        timing_policy=StrategyTimingPolicy(market_open=MARKET_OPEN, orpt_time=time(9, 24, 59), rc_time=time(9, 29, 59)),
        now=now,
        invalid_runtime_classification="INVALID_RUNTIME_CLASSIFICATION",
        selected_contract_authoritative=False,
        base_entry=Decimal("194.25"),
        revised_entry=None,
        underlying_bars=_bars("NSE:NIFTY50-INDEX", [("09:15", "22500", "22550", "22490", "22520")]),
        option_bars=None,
        current_quote=None,
    )
    assert result.current_entry_state == "BLOCKED_INSUFFICIENT_HISTORICAL_EVIDENCE"
    assert result.block_reason == "SELECTED_CONTRACT_NOT_AUTHORITATIVE_FOR_CURRENT_SESSION"


def test_reconstruction_marks_rc_missed_when_revised_entry_is_breached() -> None:
    now = datetime(2026, 8, 4, 10, 0, tzinfo=IST)
    result = reconstruct_option_selling_entry(
        strategy_instance_id="S22_RELIANCE_INTERNAL_PAPER_A",
        timing_policy=StrategyTimingPolicy(market_open=MARKET_OPEN, orpt_time=time(9, 24, 59), rc_time=time(9, 29, 59)),
        now=now,
        invalid_runtime_classification="INVALID_RUNTIME_CLASSIFICATION",
        selected_contract_authoritative=True,
        base_entry=Decimal("57.50"),
        revised_entry=Decimal("57.00"),
        underlying_bars=_bars("NSE:RELIANCE-EQ", [("09:15", "1300", "1305", "1298", "1302")]),
        option_bars=_bars(
                "NSE:RELIANCE26AUG1260CE",
                [
                    ("09:24", "60", "61", "56", "58"),
                    ("09:30", "58", "59", "56.90", "57"),
                ],
            ),
        current_quote=_quote("NSE:RELIANCE26AUG1260CE", "56.90"),
    )
    assert result.current_entry_state == "RC_ENTRY_ALREADY_MISSED"


def test_candle_completeness_detects_missing_opening_bar() -> None:
    quality = classify_candle_completeness(
        _bars("NSE:RELIANCE-EQ", [("09:16", "1300", "1301", "1299", "1300")]),
        required_start=time(9, 15),
        required_end=datetime(2026, 8, 4, 10, 0, tzinfo=IST),
    )
    assert quality == "INSUFFICIENT_TO_DETERMINE_TRIGGER_BREACH"


def _bars(symbol: str, rows: list[tuple[str, str, str, str, str]]) -> CompletedCandleSet:
    candles = []
    for clock, opn, high, low, close in rows:
        hour, minute = [int(item) for item in clock.split(":")]
        start = datetime(2026, 8, 4, hour, minute, tzinfo=IST)
        candles.append(
            FyersCandle(
                symbol=symbol,
                bar_start=start,
                bar_end=start.replace(second=59),
                open=Decimal(opn),
                high=Decimal(high),
                low=Decimal(low),
                close=Decimal(close),
                volume=Decimal("1000"),
                source_id=f"history:{symbol}",
                complete=True,
            )
        )
    return CompletedCandleSet(symbol=symbol, candles=tuple(candles), excluded_incomplete=(), duplicate_count=0, source_hash=f"hash:{symbol}:{len(rows)}")


def _quote(symbol: str, ltp: str) -> FyersQuote:
    return FyersQuote(
        symbol=symbol,
        ltp=Decimal(ltp),
        bid=Decimal(ltp),
        ask=Decimal(ltp),
        volume=Decimal("100"),
        oi=Decimal("1000"),
        timestamp=datetime(2026, 8, 4, 10, 0, tzinfo=IST),
        source_hash=f"quote:{symbol}",
    )
