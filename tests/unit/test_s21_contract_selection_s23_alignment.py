from __future__ import annotations

from tfis.strategy_engine.s21 import (
    OptionContractEvidence,
    OptionHistoricalReferences,
    S21StrategyEngine,
    S21StrategyEvidence,
)


CODES = (
    "BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL",
    "BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT",
    "BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL",
    "BANKNIFTY_OP_SELL_MONTHLY_BEAR_PUT",
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
        for code in CODES
    }


def _base(chain, histories):
    return S21StrategyEvidence(
        session_date="2026-08-06",
        monthly_status="BULL_CF",
        monthly_status_source="TEST",
        underlying_references={
            "PRV_2DHH": 58000.0,
            "PRV_2DLL": 57000.0,
            "PRV_3DHH": 58200.0,
            "PRV_3DLL": 56800.0,
            "PRV_4DHH": 58300.0,
            "PRV_4DLL": 56700.0,
        },
        option_chain=tuple(chain),
        option_historical_references=histories,
        option_minute_bars={},
        spot_bars={},
        branch_parameters=_params(),
    )


def test_bull_put_contract_qualification_uses_chain_premium_not_opt_prv_2dll():
    symbol = "PE_58000"
    evidence = _base(
        [
            OptionContractEvidence(
                symbol=symbol,
                option_type="PUT",
                strike=58000.0,
                expiry="2026-08-25",
                oi=50000.0,
                chain_ltp=1300.0,  # qualifies Ideal against PRV_2DHH * 2% = 1160
            )
        ],
        {
            symbol: OptionHistoricalReferences(
                symbol=symbol,
                # Historical entry reference is intentionally tiny. Old S21
                # incorrectly used 100 as candidate premium and rejected PE.
                references={
                    "OPT_PRV_2DLL": 100.0,
                    "OPT_PRV_3DHH": 2000.0,
                },
                source="TEST",
            )
        },
    )
    decision = S21StrategyEngine().evaluate(evidence)
    put = next(x for x in decision.legs if x.unique_code.endswith("BULL_PUT"))
    assert put.selected_contract == symbol
    assert put.selection_phase == "IDEAL_START_TO_END"
    assert put.candidate_decisions[0].candidate_premium == 1300.0
    # Entry still correctly uses selected contract history after selection.
    assert put.entry == 92.5


def test_bull_call_and_bull_put_are_selected_independently():
    ce = "CE_56800"
    pe = "PE_58000"
    evidence = _base(
        [
            OptionContractEvidence(ce, "CALL", 56800.0, "2026-08-25", 50000.0, 1200.0),
            OptionContractEvidence(pe, "PUT", 58000.0, "2026-08-25", 50000.0, 1300.0),
        ],
        {
            ce: OptionHistoricalReferences(
                ce,
                {"OPT_PRV_3DLL": 900.0, "OPT_PRV_2DHH": 1600.0},
                "TEST",
            ),
            pe: OptionHistoricalReferences(
                pe,
                {"OPT_PRV_2DLL": 700.0, "OPT_PRV_3DHH": 1700.0},
                "TEST",
            ),
        },
    )
    decision = S21StrategyEngine().evaluate(evidence)
    call = next(x for x in decision.legs if x.unique_code.endswith("BULL_CALL"))
    put = next(x for x in decision.legs if x.unique_code.endswith("BULL_PUT"))
    assert call.selected_contract == ce
    assert put.selected_contract == pe


def test_missing_chain_premium_fails_closed_for_oi_eligible_candidate():
    symbol = "PE_58000"
    evidence = _base(
        [OptionContractEvidence(symbol, "PUT", 58000.0, "2026-08-25", 50000.0, None)],
        {},
    )
    decision = S21StrategyEngine().evaluate(evidence)
    put = next(x for x in decision.legs if x.unique_code.endswith("BULL_PUT"))
    assert put.verdict == "EVIDENCE_INCOMPLETE"
    assert any("MISSING_OPTION_CHAIN_PREMIUM" in gap for gap in put.evidence_gaps)


def test_oi_gate_still_applies_to_chain_premium_qualified_put():
    symbol = "PE_58000"
    evidence = _base(
        [OptionContractEvidence(symbol, "PUT", 58000.0, "2026-08-25", 100.0, 5000.0)],
        {},
    )
    decision = S21StrategyEngine().evaluate(evidence)
    put = next(x for x in decision.legs if x.unique_code.endswith("BULL_PUT"))
    assert put.selected_contract is None
    assert put.verdict == "NO_QUALIFYING_CONTRACT"
