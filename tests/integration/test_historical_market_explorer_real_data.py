from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from tfis.domain.enums import OptionType
from tfis.tools.historical_market_explorer import HistoricalMarketExplorerService


REAL_DATA_ROOT = Path(r"D:\HistoricalData")


@pytest.mark.skipif(
    not (REAL_DATA_ROOT / "Nifty").exists(),
    reason="Real historical NIFTY data root is not available on this machine.",
)
def test_real_jan17_golden_contract_retrieval() -> None:
    service = HistoricalMarketExplorerService(REAL_DATA_ROOT)

    payload = service.contract_payload(
        instrument="NIFTY",
        session_date=date(2024, 1, 17),
        expiry=date(2024, 1, 18),
        strike=21650,
        option_type=OptionType.CALL,
    )

    assert payload["selection"]["symbol"] == "NIFTY18JAN2421650CE"
    assert payload["summary"]["minute_count"] > 300
    assert payload["summary"]["day_volume"] >= 0
    assert payload["summary"]["opening_oi"] >= 0
    assert payload["summary"]["closing_oi"] >= 0
    assert payload["minute_marks"]["premium_0916"]["status"] == "FOUND"
    assert payload["minute_marks"]["orpt_0924"]["status"] == "FOUND"
    assert payload["minute_marks"]["rc_0929"]["status"] == "FOUND"
    assert payload["prior_option_history"]["references"]["status"] == "READY"
    assert payload["prior_option_history"]["references"]["OPT_PRV_3DLL"] is not None
    assert payload["prior_spot_history"]["references"]["PRV_4DLL"] is not None
    assert payload["s23_workbook_validation"]["historical_lot_size"] == 50
    assert payload["s23_workbook_validation"]["minimum_oi_units"] == 25000


@pytest.mark.skipif(
    not (REAL_DATA_ROOT / "Nifty").exists(),
    reason="Real historical NIFTY data root is not available on this machine.",
)
def test_real_jan3_golden_no_trade_contract_retrieval() -> None:
    service = HistoricalMarketExplorerService(REAL_DATA_ROOT)

    payload = service.contract_payload(
        instrument="NIFTY",
        session_date=date(2024, 1, 3),
        expiry=date(2024, 1, 4),
        strike=21900,
        option_type=OptionType.PUT,
    )

    assert payload["selection"]["symbol"] == "NIFTY04JAN2421900PE"
    assert payload["summary"]["minute_count"] > 300
    assert payload["minute_marks"]["premium_0916"]["status"] == "FOUND"
    assert payload["minute_marks"]["orpt_0924"]["status"] == "FOUND"
    assert payload["minute_marks"]["rc_0929"]["status"] == "FOUND"
    assert payload["summary"]["day_volume"] >= 0
    assert payload["summary"]["maximum_oi"] >= payload["summary"]["minimum_oi"]
    assert payload["prior_option_history"]["references"]["status"] == "READY"
    assert payload["prior_option_history"]["references"]["OPT_PRV_2DHH"] is not None
    assert payload["prior_spot_history"]["references"]["PRV_3DHH"] is not None


@pytest.mark.skipif(
    not (REAL_DATA_ROOT / "Nifty").exists(),
    reason="Real historical NIFTY data root is not available on this machine.",
)
def test_real_jan17_option_chain_snapshot_retrieval() -> None:
    service = HistoricalMarketExplorerService(REAL_DATA_ROOT)

    payload = service.option_chain_payload(
        instrument="NIFTY",
        session_date=date(2024, 1, 17),
        expiry=date(2024, 1, 18),
        selected_strike=21650,
        ideal_premium=260.0,
        minimum_premium=195.0,
        minimum_oi=25000,
        start_strike=22800,
        end_strike=21600,
    )

    assert payload["rows"]
    assert any(row["strike"] == 21650 and row["selected"] for row in payload["rows"])
    assert payload["search_order"]["start_to_end"]
    assert payload["search_order"]["end_to_start"]
