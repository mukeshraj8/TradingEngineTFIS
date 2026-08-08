from __future__ import annotations

from datetime import date
import json
from pathlib import Path

from tfis.replay.s21_archived_session import S21ArchivedStrategySessionAdapter


def _write_json(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")


def test_discovers_and_maps_archived_s21_strategy_session(tmp_path: Path):
    root = tmp_path / "data" / "strategies" / "S21" / "fyers_morning_supervised_decision"
    day = root / "2026-07-15"
    cp0916 = day / "s21-fyers-morning-supervised-decision-0916-2026-07-15"
    _write_json(cp0916 / "normalized_option_chain_snapshot.json")
    _write_json(cp0916 / "normalized_underlying_daily_bars.json")

    final = day / "s21-fyers-morning-supervised-decision-2026-07-15"
    branch = final / "BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT"
    _write_json(branch / "trade_decision_explainer.json")
    _write_json(branch / "paper_order_state.json")
    (branch / "selected_contract_market_events.jsonl").write_text(
        "{}\n", encoding="utf-8"
    )

    adapter = S21ArchivedStrategySessionAdapter(root)

    assert adapter.discover_dates() == (date(2026, 7, 15),)
    session = adapter.load(date(2026, 7, 15))

    assert session.replay_market_evidence_ready is True
    assert session.has_original_decision_evidence is True
    assert session.has_persisted_selected_contract_events is True
    assert session.checkpoint_0916.option_chain_snapshot is not None
    assert session.branches[0].branch == "BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT"


def test_index_records_missing_optional_checkpoints_without_inventing_data(tmp_path: Path):
    root = tmp_path / "sessions"
    day = root / "2026-07-16"
    cp0916 = day / "session-0916-2026-07-16"
    _write_json(cp0916 / "normalized_option_chain_snapshot.json")
    _write_json(cp0916 / "normalized_underlying_daily_bars.json")

    adapter = S21ArchivedStrategySessionAdapter(root)
    session = adapter.load(date(2026, 7, 16))
    payload = session.to_index_payload()

    assert payload["checkpoints"]["0916"]["market_evidence_ready"] is True
    assert payload["checkpoints"]["0925"]["directory"] is None
    assert payload["checkpoints"]["0930"]["directory"] is None
