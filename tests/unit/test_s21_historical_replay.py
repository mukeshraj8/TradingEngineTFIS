from __future__ import annotations

from datetime import date, time

from tfis.domain.enums import MonthlyStatus
from tfis.replay.s21_replay import S21ReplayEngine


class FakeEvidence:
    def __init__(self, refs, bars=None):
        self.refs = refs
        self.bars = bars or {}

    def daily_references(self, *, symbol, session_date):
        return self.refs.get(symbol)

    def minute_bars(self, *, symbol, session_date, from_time, to_time):
        return list(self.bars.get(symbol, []))


PARAMS = {
    code: {
        "strike_buffer_pct": 5.0,
        "strike_step": 100.0,
        "ideal_premium_pct": 2.0,
        "minimum_premium_pct": 1.5,
        "entry_discount_pct": 7.5,
        "target_pct": 60.0,
        "sl_entry_pct": 60.0,
        "sl_reference_pct": 7.0 if code.endswith(("BULL_CALL", "BEAR_PUT")) else 10.0,
        "minimum_lots": 500.0,
        "lot_size": 35.0,
    }
    for code in (
        "BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL",
        "BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT",
        "BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL",
        "BANKNIFTY_OP_SELL_MONTHLY_BEAR_PUT",
    )
}


def test_bull_family_replays_two_independent_legs():
    engine = S21ReplayEngine(
        session_date=date(2026, 8, 6),
        monthly_status=MonthlyStatus.BULL_CF,
        underlying_references={
            "PRV_2DHH": 58000.0,
            "PRV_2DLL": 57000.0,
            "PRV_3DHH": 58200.0,
            "PRV_3DLL": 56800.0,
        },
        option_chain_contracts=[],
        branch_parameters=PARAMS,
        option_evidence=FakeEvidence({}),
        spot_orpt_bar=None,
        spot_rc_bar=None,
    )
    assert engine.eligible_legs() == (
        "BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL",
        "BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT",
    )


def test_bull_call_uses_historical_option_reference_not_chain_ltp():
    symbol = "BANKNIFTY_20260825_59000_CE"
    refs = {
        symbol: {
            "OPT_PRV_2DHH": 1600.0,
            "OPT_PRV_2DLL": 900.0,
            "OPT_PRV_3DHH": 1700.0,
            "OPT_PRV_3DLL": 1200.0,
        }
    }
    bars = {
        symbol: [
            {
                "bar_start": "2026-08-06T09:24:00+05:30",
                "bar_end": "2026-08-06T09:24:59+05:30",
                "high": 1300.0,
                "low": 1200.0,
            }
        ]
    }
    engine = S21ReplayEngine(
        session_date=date(2026, 8, 6),
        monthly_status=MonthlyStatus.BULL,
        underlying_references={
            "PRV_2DHH": 58000.0,
            "PRV_2DLL": 57000.0,
            "PRV_3DHH": 58200.0,
            "PRV_3DLL": 56800.0,
        },
        option_chain_contracts=[
            {
                "symbol": symbol,
                "expiry": "2026-08-25",
                "strike": 59000.0,
                "option_type": "CALL",
                "oi": 20000.0,
                "ltp": 100.0,  # intentionally far below ideal; must not decide qualification
            }
        ],
        branch_parameters=PARAMS,
        option_evidence=FakeEvidence(refs, bars),
        spot_orpt_bar={},
        spot_rc_bar={},
    )
    leg = engine.replay_leg("BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL")
    assert leg.selected_contract == symbol
    assert leg.selection_phase == "IDEAL_PREMIUM_START_TO_END"
    assert leg.entry == 1110.0


def test_missing_history_fails_closed_instead_of_using_current_ltp():
    symbol = "BANKNIFTY_20260825_59000_CE"
    engine = S21ReplayEngine(
        session_date=date(2026, 8, 6),
        monthly_status=MonthlyStatus.BULL,
        underlying_references={
            "PRV_2DHH": 58000.0,
            "PRV_2DLL": 57000.0,
            "PRV_3DHH": 58200.0,
            "PRV_3DLL": 56800.0,
        },
        option_chain_contracts=[
            {
                "symbol": symbol,
                "expiry": "2026-08-25",
                "strike": 59000.0,
                "option_type": "CALL",
                "oi": 20000.0,
                "ltp": 5000.0,
            }
        ],
        branch_parameters=PARAMS,
        option_evidence=FakeEvidence({}),
        spot_orpt_bar=None,
        spot_rc_bar=None,
    )
    leg = engine.replay_leg("BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL")
    assert leg.selected_contract is None
    assert leg.replay_verdict == "NO_QUALIFYING_CONTRACT"
