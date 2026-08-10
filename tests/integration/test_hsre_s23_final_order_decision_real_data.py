from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest

from tfis.backtest.hsre_s23_final_order_decision import HsreS23FinalOrderDecisionBuilder
from tfis.backtest.nifty_hsre_data_adapter import NiftyHsreHistoricalMarketDataProvider


REAL_NIFTY_ROOT = Path(r"D:\HistoricalData\Nifty")


@pytest.mark.skipif(
    not REAL_NIFTY_ROOT.exists(),
    reason="Real HSRE NIFTY data root is not available on this machine.",
)
def test_real_jan_3_2024_s23_final_order_decision() -> None:
    provider = NiftyHsreHistoricalMarketDataProvider(
        REAL_NIFTY_ROOT,
        max_cached_sessions=128,
    )
    builder = HsreS23FinalOrderDecisionBuilder(provider)

    first = builder.build_for_session(
        session_date=date(2024, 1, 3),
        planning_time=time(9, 16),
    )
    second = builder.build_for_session(
        session_date=date(2024, 1, 3),
        planning_time=time(9, 16),
    )

    assert first.status in {
        "NORMAL_ORDER_READY",
        "RECALCULATED_ORDER_READY",
        "NO_QUALIFYING_RECALCULATED_CONTRACT",
        "INSUFFICIENT_RECALCULATED_OPTION_HISTORY",
        "RC_REJECTED",
        "EVIDENCE_INCOMPLETE",
    }
    assert builder.stable_packet_hash(first) == builder.stable_packet_hash(second)
    assert first.monthly_status == "BULL_CF"
    assert first.branch == "NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT"
    assert first.base_contract == "NIFTY04JAN2421900PE"
    assert first.base_entry == pytest.approx(85.60875)
    assert first.orpt_evidence is not None
    assert first.entry_missed_result is not None

    print(
        "HSRE_M3_REAL_READY "
        f"session={first.session_date} "
        f"hash={builder.stable_packet_hash(first)} "
        f"status={first.status} "
        f"monthly_status={first.monthly_status} "
        f"branch={first.branch} "
        f"base_contract={first.base_contract} "
        f"base_entry={first.base_entry} "
        f"orpt_option_low={first.orpt_evidence.option_low_through_cutoff} "
        f"orpt_option_high={first.orpt_evidence.option_high_through_cutoff} "
        f"orpt_spot_low={first.orpt_evidence.spot_low_through_cutoff} "
        f"orpt_spot_high={first.orpt_evidence.spot_high_through_cutoff} "
        f"entry_missed={first.entry_missed_result.entry_missed} "
        f"recalculated_contract={first.recalculated_contract} "
        f"final_contract={first.final_effective_contract} "
        f"final_entry={first.final_effective_entry} "
        f"final_target={first.final_effective_target} "
        f"final_stoploss={first.final_effective_stoploss}"
    )
