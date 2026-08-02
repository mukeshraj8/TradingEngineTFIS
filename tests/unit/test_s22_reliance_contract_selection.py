from __future__ import annotations

import copy

from tfis.adapters.phase5e import s22_reliance as s22


def _fixture() -> dict:
    return s22._load_fixture(s22.FIXTURE_PATH)


def test_s22_reliance_metadata_lot_size_conflict_blocks() -> None:
    fixture = _fixture()
    fixture = copy.deepcopy(fixture)
    fixture["option_chains"][0]["payload"]["contracts"][0]["lot_size"] = 250

    result = s22._metadata_validation(fixture)

    assert result["verdict"] == "BLOCKED_METADATA_LOT_SIZE_CONFLICT"
    assert sorted(result["lot_sizes_observed"]) == [250, 500]


def test_s22_reliance_near_expiry_bear_call_qualifies_from_real_candidates() -> None:
    fixture = _fixture()
    market_structure = s22._market_structure(fixture)
    result = s22._evaluate_branch_contracts(fixture, market_structure, s22.BRANCH_SPECS["BEAR_CALL"])

    assert result["decision"] == "SELECTED"
    assert result["selected_expiry_kind"] == "NEAR"
    assert result["qualification_phase"] == "IDEAL_PREMIUM"
    assert result["selected_contract"]["symbol"] == "NSE:RELIANCE26AUG1260CE"
    assert result["selected_contract"]["option_type"] == "CALL"
    assert DecimalString(result["selected_contract"]["oi"]) >= DecimalString(result["minimum_oi_exchange_units"])


def test_s22_reliance_near_fail_can_fall_back_to_next_expiry() -> None:
    fixture = _fixture()
    market_structure = s22._market_structure(fixture)
    result = s22._evaluate_branch_contracts(fixture, market_structure, s22.BRANCH_SPECS["BEAR_CALL"], force_near_fail=True)

    assert result["decision"] == "SELECTED"
    assert result["selected_expiry_kind"] == "NEXT"
    assert result["selected_contract"]["expiry"] == "2026-09-29"


def test_s22_reliance_wrong_contract_guards_are_recorded() -> None:
    certification = s22.build_s22_reliance_certification()
    guards = certification["s22_reliance_contract_selection"]["wrong_contract_guards"]

    assert guards["ce_cannot_satisfy_pe"] is True
    assert guards["pe_cannot_satisfy_ce"] is True
    assert guards["wrong_expiry_blocks"] is True
    assert guards["wrong_strike_blocks"] is True
    assert guards["oi_missing_differs_from_zero"] is True


def DecimalString(value: str):
    from decimal import Decimal

    return Decimal(str(value))
