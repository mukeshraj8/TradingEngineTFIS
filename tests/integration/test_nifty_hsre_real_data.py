from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest

from tfis.backtest.nifty_hsre_data_adapter import (
    NiftyHsreHistoricalMarketDataProvider,
)


HISTORICAL_ROOT = Path(r"D:\HistoricalData\Nifty")


@pytest.mark.skipif(not HISTORICAL_ROOT.exists(), reason="D:\\HistoricalData\\Nifty is not available")
def test_real_jan_1_2024_nifty_hsre_data_smoke() -> None:
    provider = NiftyHsreHistoricalMarketDataProvider(HISTORICAL_ROOT)
    session = date(2024, 1, 1)

    spot_bars = provider.get_spot_session_bars(session)
    option_bars = provider.get_option_session_bars(session)
    audit = provider.audit_option_session(session, chain_time=time(9, 16))

    assert provider.get_available_expiries(session) == (date(2024, 1, 4),)
    assert audit.available_expiries == (date(2024, 1, 4),)
    assert spot_bars
    assert option_bars
    assert audit.option_row_count == len(option_bars)
    assert audit.contract_count > 0
    assert audit.ce_count > 0
    assert audit.pe_count > 0
    assert audit.strike_min is not None
    assert audit.strike_max is not None
    assert audit.oi_min is not None
    assert audit.oi_max is not None
    assert audit.negative_oi_count == 0
    assert audit.chain_contract_count > 0

    print(
        "HSRE_REAL_DATA_SMOKE "
        f"session={session.isoformat()} "
        f"spot_minute_count={len(spot_bars)} "
        f"option_row_count={audit.option_row_count} "
        f"contract_count={audit.contract_count} "
        f"CE={audit.ce_count} "
        f"PE={audit.pe_count} "
        f"strike_range={audit.strike_min}-{audit.strike_max} "
        f"oi_min={audit.oi_min} "
        f"oi_max={audit.oi_max} "
        f"negative_oi_count={audit.negative_oi_count} "
        f"zero_oi_count={audit.zero_oi_count} "
        f"chain_0916_contract_count={audit.chain_contract_count} "
        f"available_expiries={[item.isoformat() for item in audit.available_expiries]}"
    )
