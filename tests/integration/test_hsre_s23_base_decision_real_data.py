from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest

from tfis.backtest.hsre_s23_base_decision import HsreS23BaseDecisionBuilder
from tfis.backtest.nifty_hsre_data_adapter import NiftyHsreHistoricalMarketDataProvider


REAL_NIFTY_ROOT = Path(r"D:\HistoricalData\Nifty")


@pytest.mark.skipif(
    not REAL_NIFTY_ROOT.exists(),
    reason="Real HSRE NIFTY data root is not available on this machine.",
)
def test_real_january_2024_first_s23_base_decision_discovery() -> None:
    provider = NiftyHsreHistoricalMarketDataProvider(
        REAL_NIFTY_ROOT,
        max_cached_sessions=96,
    )
    builder = HsreS23BaseDecisionBuilder(provider)

    discovery = builder.discover_first_january_base_order(
        year=2024,
        evaluation_time=time(9, 16),
    )

    for attempt in discovery.attempts:
        print(
            "HSRE_M2_REAL_ATTEMPT "
            f"session={attempt['session_date']} "
            f"monthly_status={attempt['monthly_status']} "
            f"branch={attempt['branch']} "
            f"contract_selection={attempt['contract_selection_result']} "
            f"option_lookback={attempt['option_lookback_status']} "
            f"final_status={attempt['final_status']} "
            f"reason={attempt['reason']}"
        )

    assert discovery.first_attempted_session is not None
    assert discovery.first_base_order_ready_session is not None
    assert discovery.accepted_packet_hash is not None

    ready_packet = builder.build_for_session(
        session_date=date.fromisoformat(discovery.first_base_order_ready_session),
        evaluation_time=time(9, 16),
    )
    assert ready_packet.status == "READY"
    assert ready_packet.option_reference_packet is not None
    assert ready_packet.selected_symbol is not None
    assert ready_packet.selected_premium_0916 is not None
    assert ready_packet.selected_oi_0916 is not None
    print(
        "HSRE_M2_REAL_READY "
        f"session={ready_packet.session_date} "
        f"hash={builder.stable_packet_hash(ready_packet)} "
        f"monthly_status={ready_packet.monthly_status} "
        f"branch={ready_packet.resolved_strategy_unique_code} "
        f"selected={ready_packet.selected_symbol} "
        f"premium={ready_packet.selected_premium_0916} "
        f"oi={ready_packet.selected_oi_0916} "
        f"volume={ready_packet.selected_volume_0916} "
        f"prior={','.join(ready_packet.option_reference_packet.prior_sessions_used)} "
        f"OPT_PRV_2DHH={ready_packet.option_reference_packet.opt_prv_2dhh} "
        f"OPT_PRV_2DLL={ready_packet.option_reference_packet.opt_prv_2dll} "
        f"OPT_PRV_3DHH={ready_packet.option_reference_packet.opt_prv_3dhh} "
        f"OPT_PRV_3DLL={ready_packet.option_reference_packet.opt_prv_3dll} "
        f"entry={ready_packet.base_entry} "
        f"target={ready_packet.base_target} "
        f"stoploss={ready_packet.base_stoploss}"
    )
