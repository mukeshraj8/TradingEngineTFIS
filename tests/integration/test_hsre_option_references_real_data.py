from __future__ import annotations

from datetime import time
from pathlib import Path

import pytest

from tfis.backtest.hsre_option_references import NiftyHsreSelectedContractReferenceBuilder
from tfis.backtest.nifty_hsre_data_adapter import NiftyHsreHistoricalMarketDataProvider


REAL_NIFTY_ROOT = Path(r"D:\HistoricalData\Nifty")


@pytest.mark.skipif(
    not REAL_NIFTY_ROOT.exists(),
    reason="Real HSRE NIFTY data root is not available on this machine.",
)
def test_real_january_2024_selected_contract_reference_discovery() -> None:
    provider = NiftyHsreHistoricalMarketDataProvider(
        REAL_NIFTY_ROOT,
        max_cached_sessions=64,
    )
    builder = NiftyHsreSelectedContractReferenceBuilder(provider)

    rows = builder.discover_january_contract_references(
        year=2024,
        chain_time=time(9, 16),
    )

    for row in rows:
        if row.status == "READY":
            assert row.opt_prv_2dhh is not None
            assert row.opt_prv_2dll is not None
            assert row.opt_prv_3dhh is not None
            assert row.opt_prv_3dll is not None
        print(
            "HSRE_M1C_REAL_CONTRACT "
            f"session={row.session_date} "
            f"contract={row.contract.raw_symbol} "
            f"expiry={row.contract.expiry} "
            f"strike={row.contract.strike} "
            f"side={row.contract.option_type} "
            f"prior_available={','.join(row.prior_exact_contract_sessions_available) or '-'} "
            f"two_day_ready={row.two_day_ready} "
            f"three_day_ready={row.three_day_ready} "
            f"status={row.status} "
            f"OPT_PRV_2DHH={row.opt_prv_2dhh} "
            f"OPT_PRV_2DLL={row.opt_prv_2dll} "
            f"OPT_PRV_3DHH={row.opt_prv_3dhh} "
            f"OPT_PRV_3DLL={row.opt_prv_3dll}"
        )

    assert len(rows) >= 5
    assert any(row.contract.expiry == "2024-01-04" and row.contract.option_type == "CALL" for row in rows)
    assert any(row.contract.expiry == "2024-01-04" and row.contract.option_type == "PUT" for row in rows)
    assert any(row.contract.expiry == "2024-01-11" and row.contract.option_type == "CALL" for row in rows)
    assert any(row.contract.expiry == "2024-01-11" and row.contract.option_type == "PUT" for row in rows)
    assert any(row.status == "READY" for row in rows)
