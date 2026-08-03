from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from tfis.adapters.phase5e import s22_reliance as s22
from tfis.contract_selection import (
    ActualOptionChainQualityCode,
    build_actual_option_chain_traversal,
)


def _contract(
    *,
    symbol: str,
    underlying: str,
    expiry: str,
    option_type: str,
    strike: str,
    ltp: str = "100.0",
    oi: str = "100000",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "underlying": underlying,
        "expiry": expiry,
        "option_type": option_type,
        "strike": strike,
        "ltp": ltp,
        "oi": oi,
        "lot_size": 400,
        "tick_size": "0.05",
        "oi_unit": "SOURCE_UNSPECIFIED",
    }


def test_descending_traversal_uses_non_uniform_actual_ladder_without_synthetic_strikes() -> None:
    traversal = build_actual_option_chain_traversal(
        (
            _contract(symbol="NSE:INFY26AUG1140CE", underlying="INFY-EQ", expiry="2026-08-25", option_type="CALL", strike="1140"),
            _contract(symbol="NSE:INFY26AUG1120CE", underlying="INFY-EQ", expiry="2026-08-25", option_type="CALL", strike="1120"),
            _contract(symbol="NSE:INFY26AUG1115CE", underlying="INFY-EQ", expiry="2026-08-25", option_type="CALL", strike="1115"),
            _contract(symbol="NSE:INFY26AUG1100CE", underlying="INFY-EQ", expiry="2026-08-25", option_type="CALL", strike="1100"),
            _contract(symbol="NSE:INFY26AUG1080CE", underlying="INFY-EQ", expiry="2026-08-25", option_type="CALL", strike="1080"),
        ),
        expected_underlying="INFY",
        expiry=date(2026, 8, 25),
        option_type="CALL",
        traversal_direction="DESCENDING_START_TO_END",
        start_reference_strike=Decimal("1132"),
        start_round_mode="DOWN",
        end_reference_strike=Decimal("1118"),
        end_round_mode="DOWN",
        end_offset_steps=-1,
        exchange="NSE",
    )

    assert [str(item) for item in traversal.ordered_candidate_strikes] == ["1120", "1115", "1100"]
    assert "1105" not in [str(item) for item in traversal.ordered_candidate_strikes]
    assert traversal.resolved_start_strike == Decimal("1120")
    assert traversal.resolved_end_strike == Decimal("1100")
    assert ActualOptionChainQualityCode.COMPLETE_FOR_REQUIRED_RANGE in traversal.quality_codes


def test_ascending_traversal_uses_first_actual_boundary_when_start_is_not_listed() -> None:
    traversal = build_actual_option_chain_traversal(
        (
            _contract(symbol="NSE:INFY26AUG1180PE", underlying="INFY-EQ", expiry="2026-08-25", option_type="PUT", strike="1180"),
            _contract(symbol="NSE:INFY26AUG1195PE", underlying="INFY-EQ", expiry="2026-08-25", option_type="PUT", strike="1195"),
            _contract(symbol="NSE:INFY26AUG1200PE", underlying="INFY-EQ", expiry="2026-08-25", option_type="PUT", strike="1200"),
            _contract(symbol="NSE:INFY26AUG1220PE", underlying="INFY-EQ", expiry="2026-08-25", option_type="PUT", strike="1220"),
        ),
        expected_underlying="INFY",
        expiry=date(2026, 8, 25),
        option_type="PUT",
        traversal_direction="ASCENDING_START_TO_END",
        start_reference_strike=Decimal("1182"),
        start_round_mode="UP",
        end_reference_strike=Decimal("1190"),
        end_round_mode="UP",
        end_offset_steps=1,
        exchange="NSE",
    )

    assert [str(item) for item in traversal.ordered_candidate_strikes] == ["1195", "1200"]
    assert traversal.resolved_start_strike == Decimal("1195")
    assert traversal.resolved_end_strike == Decimal("1200")


def test_duplicate_contract_identities_are_classified_without_inventing_selection() -> None:
    traversal = build_actual_option_chain_traversal(
        (
            _contract(symbol="NSE:INFY26AUG1140CE", underlying="INFY-EQ", expiry="2026-08-25", option_type="CALL", strike="1140"),
            _contract(symbol="NSE:INFY26AUG1140CE", underlying="INFY-EQ", expiry="2026-08-25", option_type="CALL", strike="1140"),
        ),
        expected_underlying="INFY",
        expiry=date(2026, 8, 25),
        option_type="CALL",
        traversal_direction="DESCENDING_START_TO_END",
        start_reference_strike=Decimal("1140"),
        start_round_mode="DOWN",
        end_reference_strike=Decimal("1140"),
        end_round_mode="DOWN",
        exchange="NSE",
    )

    assert ActualOptionChainQualityCode.DUPLICATE_CONTRACT_IDENTITIES in traversal.quality_codes
    assert traversal.ordered_candidate_strikes == (Decimal("1140"),)


def test_infy_fixture_selection_uses_real_contract_from_input_chain() -> None:
    fixture = s22._load_fixture(Path("tests/fixtures/s22_multi_stock/s22_infy_fyers_snapshot_2026-08-03_sanitized.json"))
    market_structure = s22._market_structure(fixture)
    result = s22._evaluate_branch_contracts(
        fixture,
        market_structure,
        s22.BRANCH_SPECS["BEAR_CALL"],
        underlying_symbol="INFY",
        metadata_version="fyers-symbol-master:NSEFO:2026-08-03",
    )
    available_symbols = {
        contract["symbol"]
        for chain in fixture["option_chains"]
        for contract in chain["payload"]["contracts"]
        if contract["expiry"] == result["selected_contract"]["expiry"]
        and contract["option_type"] == result["selected_contract"]["option_type"]
    }

    assert result["decision"] == "SELECTED"
    assert result["selected_contract"]["symbol"] == "NSE:INFY26AUG1140CE"
    assert result["selected_contract"]["symbol"] in available_symbols
    assert "1105" not in result["strike_candidates"]


def test_tcs_fixture_selection_uses_real_contract_from_input_chain() -> None:
    fixture = s22._load_fixture(Path("tests/fixtures/s22_multi_stock/s22_tcs_fyers_snapshot_2026-08-03_sanitized.json"))
    market_structure = s22._market_structure(fixture)
    result = s22._evaluate_branch_contracts(
        fixture,
        market_structure,
        s22.BRANCH_SPECS["BEAR_CALL"],
        underlying_symbol="TCS",
        metadata_version="fyers-symbol-master:NSEFO:2026-08-03",
    )
    available_symbols = {
        contract["symbol"]
        for chain in fixture["option_chains"]
        for contract in chain["payload"]["contracts"]
        if contract["expiry"] == result["selected_contract"]["expiry"]
        and contract["option_type"] == result["selected_contract"]["option_type"]
    }

    assert result["decision"] == "SELECTED"
    assert result["selected_contract"]["symbol"] == "NSE:TCS26AUG2380CE"
    assert result["selected_contract"]["symbol"] in available_symbols


def test_selected_contract_is_serializable_to_existing_report_shape() -> None:
    fixture = s22._load_fixture(Path("tests/fixtures/s22_multi_stock/s22_infy_fyers_snapshot_2026-08-03_sanitized.json"))
    market_structure = s22._market_structure(fixture)
    result = s22._evaluate_branch_contracts(
        fixture,
        market_structure,
        s22.BRANCH_SPECS["BEAR_PUT"],
        underlying_symbol="INFY",
        metadata_version="fyers-symbol-master:NSEFO:2026-08-03",
    )

    payload = json.dumps(result, sort_keys=True)

    assert "NSE:INFY26AUG1200PE" in payload
