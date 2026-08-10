from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from tfis.backtest.hsre_s23_base_decision import (
    HsreS23BaseDecisionBuilder,
    hsre_s23_base_decision_packet_to_dict,
)
from tfis.backtest.nifty_hsre_data_adapter import NiftyHsreHistoricalMarketDataProvider


ROOT = Path(__file__).resolve().parents[2]
S23_ROOT = ROOT / "config" / "strategies" / "options_sell" / "nifty"


def _write_spot(
    root: Path,
    session: date,
    rows: list[tuple[str, float, float, float, float]],
) -> None:
    path = root / "spot" / f"{session.year}" / f"{session.month}" / f"nifty_spot{session:%d_%m_%Y}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["date,time,symbol,open,high,low,close"]
    for raw_time, open_, high, low, close in rows:
        lines.append(f"{session.isoformat()},{raw_time},NIFTY,{open_},{high},{low},{close}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_options(
    root: Path,
    session: date,
    rows: list[tuple[str, str, float, float, float, float, int, int]],
) -> None:
    path = root / "options" / f"{session.year}" / f"{session.month}" / f"nifty_options_{session:%d_%m_%Y}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["date,time,symbol,open,high,low,close,oi,volume"]
    for raw_time, symbol, open_, high, low, close, oi, volume in rows:
        lines.append(
            f"{session.isoformat()},{raw_time},{symbol},{open_},{high},{low},{close},{oi},{volume}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_base_spot_context(root: Path) -> None:
    for session in [date(2023, 12, 26), date(2023, 12, 27), date(2023, 12, 28), date(2023, 12, 29)]:
        _write_spot(
            root,
            session,
            [("09:15:00", 95.0, 100.0, 90.0, 96.0), ("15:30:00", 96.0, 96.0, 96.0, 96.0)],
        )
    _write_spot(
        root,
        date(2024, 1, 1),
        [
            ("09:15:00", 100.0, 101.0, 99.0, 100.0),
            ("09:16:00", 100.0, 103.0, 99.0, 102.0),
            ("09:17:00", 102.0, 999.0, 1.0, 103.0),
        ],
    )


def _write_prior_contract_history(root: Path, symbol: str = "NIFTY04JAN2450CE") -> None:
    rows = {
        date(2023, 12, 26): (20.0, 30.0, 10.0, 20.0),
        date(2023, 12, 27): (21.0, 31.0, 11.0, 21.0),
        date(2023, 12, 28): (22.0, 32.0, 12.0, 22.0),
        date(2023, 12, 29): (23.0, 33.0, 13.0, 23.0),
    }
    for session, (open_, high, low, close) in rows.items():
        _write_options(
            root,
            session,
            [
                ("09:15:00", symbol, open_, high - 1.0, low + 1.0, close, 100000, 1),
                ("09:16:00", symbol, open_ + 1.0, high, low, close, 100000, 2),
                ("09:16:00", "NIFTY11JAN2450CE", 1.0, 999.0, 1.0, 1.0, 100000, 1),
                ("09:16:00", "NIFTY04JAN24100CE", 1.0, 888.0, 2.0, 1.0, 100000, 1),
                ("09:16:00", "NIFTY04JAN2450PE", 1.0, 777.0, 3.0, 1.0, 100000, 1),
            ],
        )


def _write_decision_chain(
    root: Path,
    *,
    selected_ltp: float = 2.0,
    selected_oi: int = 100000,
    include_selected: bool = True,
    include_later_extreme: bool = True,
) -> None:
    rows: list[tuple[str, str, float, float, float, float, int, int]] = []
    if include_selected:
        rows.append(("09:16:00", "NIFTY04JAN2450CE", 2.0, 2.0, 2.0, selected_ltp, selected_oi, 99))
    rows.extend(
        [
            ("09:16:00", "NIFTY04JAN2400CE", 0.5, 0.5, 0.5, 0.5, 100000, 1),
            ("09:16:00", "NIFTY04JAN2450PE", 2.0, 2.0, 2.0, 2.0, 100000, 1),
            ("09:16:00", "NIFTY04JAN2450CE", 0.5, 0.5, 0.5, 0.5, 1, 1),
            ("09:16:00", "NIFTY11JAN2450CE", 0.5, 0.5, 0.5, 0.5, 100000, 1),
            ("09:16:00", "NIFTY18JAN2450CE", 999.0, 999.0, 999.0, 999.0, 100000, 1),
        ]
    )
    if include_later_extreme:
        rows.append(("09:17:00", "NIFTY04JAN2450CE", 999.0, 999.0, 1.0, 999.0, 100000, 1))
    _write_options(root, date(2024, 1, 1), rows)


def _ready_builder(root: Path) -> HsreS23BaseDecisionBuilder:
    return HsreS23BaseDecisionBuilder(
        NiftyHsreHistoricalMarketDataProvider(root, max_cached_sessions=32),
        strategy_root=S23_ROOT,
    )


def _ready_dataset(root: Path) -> None:
    _write_base_spot_context(root)
    _write_prior_contract_history(root)
    _write_decision_chain(root)


def test_builds_ready_base_decision_with_existing_branch_selector_and_evaluator(tmp_path: Path) -> None:
    _ready_dataset(tmp_path)

    packet = _ready_builder(tmp_path).build_for_session(session_date=date(2024, 1, 1))

    assert packet.status == "READY"
    assert packet.monthly_status == "BULL_CF"
    assert packet.resolved_strategy_unique_code == "NIFTY_OP_SELL_WK_DIFF_2D_3D"
    assert packet.selected_symbol == "NIFTY04JAN2450CE"
    assert packet.selected_expiry == "2024-01-04"
    assert packet.selected_strike == 50
    assert packet.selected_option_type == "CALL"
    assert packet.selected_premium_0916 == 2.0
    assert packet.selected_oi_0916 == 100000
    assert packet.selected_volume_0916 == 99
    assert packet.option_reference_packet is not None
    assert packet.option_reference_packet.prior_sessions_used == (
        "2023-12-27",
        "2023-12-28",
        "2023-12-29",
    )
    assert packet.option_reference_packet.opt_prv_2dhh == 33.0
    assert packet.option_reference_packet.opt_prv_2dll == 12.0
    assert packet.option_reference_packet.opt_prv_3dhh == 33.0
    assert packet.option_reference_packet.opt_prv_3dll == 11.0
    assert packet.base_entry == pytest.approx(10.175)
    assert packet.base_target == pytest.approx(4.07)
    assert packet.base_stoploss == pytest.approx(16.28)


def test_option_chain_handoff_reports_premium_oi_and_expiry_counts(tmp_path: Path) -> None:
    _ready_dataset(tmp_path)

    packet = _ready_builder(tmp_path).build_for_session(session_date=date(2024, 1, 1))

    assert packet.candidate_count == 5
    assert packet.expiry_rejection_count == 1
    assert packet.oi_rejection_count == 1
    assert packet.premium_rejection_count == 2
    assert packet.qualified_count == 1
    assert packet.historical_lot_size == 50
    assert packet.minimum_oi_lots == 500
    assert packet.minimum_oi_units == 25000
    assert packet.branch_attempts[0].historical_lot_size == 50
    assert packet.branch_attempts[0].minimum_oi_lots == 500
    assert packet.branch_attempts[0].minimum_oi_units == 25000
    assert packet.selected_contract_bid_ask_placeholder is True


def test_hsre_contract_selection_uses_historical_session_date_oi_threshold(tmp_path: Path) -> None:
    _write_base_spot_context(tmp_path)
    _write_prior_contract_history(tmp_path)
    _write_decision_chain(tmp_path, selected_oi=26000)

    packet = _ready_builder(tmp_path).build_for_session(session_date=date(2024, 1, 1))

    assert packet.status == "READY"
    assert packet.minimum_oi_units == 25000
    assert packet.selected_oi_0916 == 26000


def test_no_qualifying_contract_fails_closed(tmp_path: Path) -> None:
    _write_base_spot_context(tmp_path)
    _write_prior_contract_history(tmp_path)
    _write_decision_chain(tmp_path, selected_ltp=0.1, selected_oi=1)

    packet = _ready_builder(tmp_path).build_for_session(session_date=date(2024, 1, 1))

    assert packet.status == "NO_QUALIFYING_CONTRACT"
    assert packet.selected_symbol is None
    assert packet.qualified_count == 0


def test_selected_contract_insufficient_history_fails_closed(tmp_path: Path) -> None:
    _write_base_spot_context(tmp_path)
    for session in [date(2023, 12, 28), date(2023, 12, 29)]:
        _write_options(
            tmp_path,
            session,
            [("09:16:00", "NIFTY04JAN2450CE", 20.0, 30.0, 10.0, 20.0, 100000, 1)],
        )
    _write_decision_chain(tmp_path)

    packet = _ready_builder(tmp_path).build_for_session(session_date=date(2024, 1, 1))

    assert packet.status == "INSUFFICIENT_OPTION_LOOKBACK"
    assert packet.selected_symbol is None
    assert packet.branch_attempts[0].selected_symbol == "NIFTY04JAN2450CE"
    assert packet.branch_attempts[0].option_lookback_status == "INSUFFICIENT_OPTION_LOOKBACK"


def test_no_active_branch_fails_closed_with_empty_strategy_root(tmp_path: Path) -> None:
    _ready_dataset(tmp_path)
    empty_strategy_root = tmp_path / "strategies"
    empty_strategy_root.mkdir()
    builder = HsreS23BaseDecisionBuilder(
        NiftyHsreHistoricalMarketDataProvider(tmp_path),
        strategy_root=empty_strategy_root,
    )

    packet = builder.build_for_session(session_date=date(2024, 1, 1))

    assert packet.status == "NO_ACTIVE_BRANCH"
    assert packet.branch_attempts == ()


def test_no_lookahead_excludes_spot_chain_and_option_reference_extremes(tmp_path: Path) -> None:
    _ready_dataset(tmp_path)
    _write_options(
        tmp_path,
        date(2024, 1, 2),
        [("09:16:00", "NIFTY04JAN2450CE", 1.0, 5000.0, 0.01, 1.0, 100000, 1)],
    )

    packet = _ready_builder(tmp_path).build_for_session(session_date=date(2024, 1, 1))

    assert packet.status == "READY"
    assert packet.underlying_references_used["current_day_high"] == 103.0
    assert packet.selected_premium_0916 == 2.0
    assert packet.option_reference_packet is not None
    assert packet.option_reference_packet.opt_prv_3dhh == 33.0
    assert packet.option_reference_packet.opt_prv_3dll == 11.0


def test_deterministic_packet_hash_and_dict_are_stable(tmp_path: Path) -> None:
    _ready_dataset(tmp_path)
    builder = _ready_builder(tmp_path)

    first = builder.build_for_session(session_date=date(2024, 1, 1))
    second = builder.build_for_session(session_date=date(2024, 1, 1))

    assert builder.stable_packet_hash(first) == builder.stable_packet_hash(second)
    assert hsre_s23_base_decision_packet_to_dict(first) == hsre_s23_base_decision_packet_to_dict(second)
    assert first.strategy_evaluator_inputs["runtime_values"]["OPT_LEVELS"]["OPT_PRV_3DLL"] == 11.0


def test_january_discovery_stops_at_first_ready_packet(tmp_path: Path) -> None:
    _ready_dataset(tmp_path)
    builder = _ready_builder(tmp_path)

    discovery = builder.discover_first_january_base_order(year=2024)

    assert discovery.first_attempted_session == "2024-01-01"
    assert discovery.first_base_order_ready_session == "2024-01-01"
    assert discovery.accepted_packet_hash is not None
    assert discovery.attempts[0]["final_status"] == "READY"
