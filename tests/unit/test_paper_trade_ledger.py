from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

import pytest

from tfis.paper.trade_ledger import (
    PaperTradeLedgerEventType,
    PaperTradeLedgerRow,
    PaperTradeLedgerStore,
)


def test_trade_ledger_append_preserves_concurrent_rows(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    store = PaperTradeLedgerStore(
        global_ledger_root=tmp_path / "global",
        lock_timeout_seconds=5,
        lock_retry_delay_seconds=0,
    )
    row_count = 40

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(
            executor.map(
                lambda index: store.append(session_dir, _ledger_row(index)),
                range(row_count),
            )
        )

    session_rows = _read_jsonl(session_dir / "paper_trade_ledger.jsonl")
    global_rows = _read_jsonl(store.global_ledger_path)

    assert len(session_rows) == row_count
    assert len(global_rows) == row_count
    assert {row["trade_id"] for row in session_rows} == {
        f"trade-{index}" for index in range(row_count)
    }
    assert not list(session_dir.glob("*.tmp"))
    assert not list(session_dir.glob("*.lock"))


def test_trade_ledger_append_times_out_when_lock_is_held(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    lock_path = session_dir / ".paper_trade_ledger.jsonl.lock"
    lock_path.write_text("held by another writer\n", encoding="utf-8")
    store = PaperTradeLedgerStore(
        global_ledger_root=tmp_path / "global",
        lock_timeout_seconds=0,
        stale_lock_seconds=3600,
    )

    with pytest.raises(TimeoutError, match="paper trade ledger lock"):
        store.append(session_dir, _ledger_row(1))

    assert not (session_dir / "paper_trade_ledger.jsonl").exists()


def test_trade_ledger_append_removes_stale_lock(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    lock_path = session_dir / ".paper_trade_ledger.jsonl.lock"
    lock_path.write_text("stale writer\n", encoding="utf-8")
    store = PaperTradeLedgerStore(
        global_ledger_root=tmp_path / "global",
        lock_timeout_seconds=1,
        lock_retry_delay_seconds=0,
        stale_lock_seconds=0.001,
    )

    store.append(session_dir, _ledger_row(1))

    rows = _read_jsonl(session_dir / "paper_trade_ledger.jsonl")
    assert [row["trade_id"] for row in rows] == ["trade-1"]
    assert not lock_path.exists()


def _ledger_row(index: int) -> PaperTradeLedgerRow:
    timestamp = datetime(2026, 7, 27, 9, 30, index % 60)
    return PaperTradeLedgerRow(
        artifact_version=1,
        event_timestamp=timestamp,
        event_type=PaperTradeLedgerEventType.HOLD,
        trade_id=f"trade-{index}",
        strategy_id="S23:S23_TEST",
        strategy_code="S23",
        strategy_branch="S23_TEST",
        symbol="NIFTY",
        option_type="CALL",
        selected_contract_symbol=f"NIFTY_20260804_24000_CE_{index}",
        expiry_date=date(2026, 8, 4),
        side="SELL",
        lots=1,
        quantity=65,
        entry_date=date(2026, 7, 27),
        entry_timestamp=datetime(2026, 7, 27, 9, 30),
        entry_price=210.4,
        target_price=85.1,
        stoploss_price=258.94,
        fsl_price=None,
        trp_price=None,
        session_date=date(2026, 7, 27),
        lifecycle_status="PAPER_POSITION_OPEN",
        manager_status="PAPER_POSITION_HELD",
        reason_code="held",
        message="held",
        current_price=210.4 + index,
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
