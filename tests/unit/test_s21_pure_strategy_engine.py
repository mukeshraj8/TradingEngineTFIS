from __future__ import annotations

from tfis.strategy_engine.s21 import (
    MinuteBarEvidence,
    OptionContractEvidence,
    OptionHistoricalReferences,
    S21StrategyEngine,
    S21StrategyEvidence,
)


def _params():
    return {
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


def _base_evidence(history=None, bars=None):
    return S21StrategyEvidence(
        session_date="2026-08-06",
        monthly_status="BULL_CF",
        monthly_status_source="TEST",
        underlying_references={
            "PRV_2DHH": 58068.95,
            "PRV_2DLL": 57352.65,
            "PRV_3DHH": 58247.95,
            "PRV_3DLL": 57352.65,
            "PRV_4DHH": 58247.95,
            "PRV_4DLL": 57139.60,
        },
        option_chain=(
            OptionContractEvidence(
                symbol="BANKNIFTY_20260825_60000_CE",
                option_type="CALL",
                strike=60000.0,
                expiry="2026-08-25",
                oi=30000.0,
                chain_ltp=100.0,
            ),
        ),
        option_historical_references=history or {},
        option_minute_bars=bars or {},
        spot_bars={},
        branch_parameters=_params(),
    )


def test_strategy_engine_has_no_broker_dependency_and_selects_from_history():
    symbol = "BANKNIFTY_20260825_60000_CE"
    evidence = _base_evidence(
        history={
            symbol: OptionHistoricalReferences(
                symbol=symbol,
                references={
                    "OPT_PRV_2DHH": 1500.0,
                    "OPT_PRV_2DLL": 900.0,
                    "OPT_PRV_3DHH": 1600.0,
                    "OPT_PRV_3DLL": 1200.0,
                },
                source="TEST_HISTORY",
            )
        },
        bars={
            symbol: (
                MinuteBarEvidence(
                    symbol=symbol,
                    bar_start="2026-08-06T09:24:00+05:30",
                    high=1200.0,
                    low=1150.0,
                ),
            )
        },
    )
    decision = S21StrategyEngine().evaluate(evidence)
    call = next(x for x in decision.legs if x.unique_code.endswith("BULL_CALL"))
    assert call.selected_contract == symbol
    assert call.entry == 1110.0
    assert call.order_time == "09:25"


def test_current_chain_ltp_cannot_replace_missing_historical_reference():
    decision = S21StrategyEngine().evaluate(_base_evidence())
    call = next(x for x in decision.legs if x.unique_code.endswith("BULL_CALL"))
    assert call.selected_contract is None
    assert call.verdict == "EVIDENCE_INCOMPLETE"
    assert any("MISSING_OPTION_HISTORY" in x for x in call.evidence_gaps)
