from __future__ import annotations

import json
from pathlib import Path

from tfis.paper.session_contract_discovery import discover_session_contract_symbols


def test_discover_session_contract_symbols_merges_order_and_summary_sources(
    tmp_path: Path,
) -> None:
    session_dir = tmp_path / "2026-07-21" / "s23-fyers-morning-supervised-decision-2026-07-21"
    typed_branch = session_dir / "A_BRANCH"
    raw_branch = session_dir / "B_BRANCH"
    summary_branch = session_dir / "C_BRANCH"
    for path in (typed_branch, raw_branch, summary_branch):
        path.mkdir(parents=True)

    (typed_branch / "paper_order_state.json").write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "strategy_code": "S23",
                "strategy_branch": "A_BRANCH",
                "symbol": "NIFTY",
                "selected_contract_symbol": "NIFTY_20260728_24300_PE",
                "selected_contract_expiry": "2026-07-28",
                "selected_contract_option_type": "PUT",
                "selected_contract_strike": 24300,
                "expiry_type": "WEEKLY",
                "rollover_policy": "T_MINUS_1",
                "forced_close_time": "12:00:00",
                "no_carry_past_expiry": True,
                "order_side": "SELL",
                "trigger_rule": "SELL_TRIGGER_WHEN_PREMIUM_AT_OR_BELOW_ENTRY",
                "entry_date": "2026-07-21",
                "order_timestamp": "2026-07-21T09:30:00+05:30",
                "planned_entry_price": 194.25,
                "target_price": 77.70,
                "stoploss_price": 242.0,
                "fsl_price": None,
                "lots": 1,
                "quantity": 65,
                "status": "PAPER_ORDER_WAITING_FOR_TRIGGER",
                "last_updated_timestamp": "2026-07-21T09:30:00+05:30",
            }
        ),
        encoding="utf-8",
    )
    (raw_branch / "paper_order_state.json").write_text(
        json.dumps({"selected_contract_symbol": "NIFTY_20260728_24350_PE"}),
        encoding="utf-8",
    )
    (summary_branch / "trade_decision_summary.json").write_text(
        json.dumps({"summary": {"selected_contract_symbol": "NIFTY_20260728_24400_PE"}}),
        encoding="utf-8",
    )

    assert discover_session_contract_symbols(session_dir) == (
        "NIFTY_20260728_24300_PE",
        "NIFTY_20260728_24350_PE",
        "NIFTY_20260728_24400_PE",
    )
