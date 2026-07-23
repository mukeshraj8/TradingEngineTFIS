from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, datetime, time
from pathlib import Path

from tfis.paper import (
    S23PaperOrderFinalizer,
    S23PaperOrderState,
    S23PaperOrderStateStore,
    S23PaperOrderStatus,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_finalizer_script():
    script_path = REPO_ROOT / "scripts" / "finalize_s23_pending_paper_orders.py"
    spec = importlib.util.spec_from_file_location("finalize_s23_pending_paper_orders", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_finalizer_marks_same_session_waiting_order_after_cutoff(tmp_path: Path) -> None:
    order_dir = tmp_path / "2026-06-29" / "session" / "BEAR_PUT"
    store = S23PaperOrderStateStore()
    store.save_state(order_dir, _waiting_order(entry_date=date(2026, 6, 29)))

    summary = S23PaperOrderFinalizer(order_store=store).finalize(
        tmp_path,
        session_date=date(2026, 6, 29),
        marked_at=datetime(2026, 6, 29, 15, 35),
        cutoff_time=time(15, 30),
    )

    updated = store.load_state(order_dir)
    assert summary.scanned_count == 1
    assert summary.finalized_count == 1
    assert summary.decisions[0].action == "FINALIZED"
    assert summary.decisions[0].reason_code == "paper_order_not_triggered_by_cutoff_sweeper"
    assert updated.status is S23PaperOrderStatus.PAPER_ORDER_NOT_FILLED
    assert updated.last_reason_code == "paper_order_not_triggered_by_cutoff_sweeper"
    assert "session-only" in (updated.last_message or "")
    assert "Pending S23 paper entry orders" not in (updated.last_message or "")
    events = (order_dir / "paper_order_events.jsonl").read_text(encoding="utf-8")
    assert "PAPER_ORDER_NOT_FILLED" in events


def test_finalizer_skips_same_session_order_before_cutoff(tmp_path: Path) -> None:
    order_dir = tmp_path / "2026-06-29" / "session" / "BEAR_CALL"
    store = S23PaperOrderStateStore()
    store.save_state(order_dir, _waiting_order(entry_date=date(2026, 6, 29)))

    summary = S23PaperOrderFinalizer(order_store=store).finalize(
        tmp_path,
        session_date=date(2026, 6, 29),
        marked_at=datetime(2026, 6, 29, 15, 25),
        cutoff_time=time(15, 30),
    )

    updated = store.load_state(order_dir)
    assert summary.finalized_count == 0
    assert summary.skipped_count == 1
    assert summary.decisions[0].reason_code == "paper_order_cutoff_not_reached"
    assert updated.status is S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER


def test_finalizer_skips_prior_session_unless_included(tmp_path: Path) -> None:
    order_dir = tmp_path / "2026-06-28" / "session" / "BEAR_CALL"
    store = S23PaperOrderStateStore()
    store.save_state(order_dir, _waiting_order(entry_date=date(2026, 6, 28)))

    skipped = S23PaperOrderFinalizer(order_store=store).finalize(
        tmp_path,
        session_date=date(2026, 6, 29),
        marked_at=datetime(2026, 6, 29, 15, 35),
        cutoff_time=time(15, 30),
    )
    assert skipped.finalized_count == 0
    assert skipped.decisions[0].reason_code == "paper_order_prior_session_not_included"
    assert store.load_state(order_dir).status is S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER

    repaired = S23PaperOrderFinalizer(order_store=store).finalize(
        tmp_path,
        session_date=date(2026, 6, 29),
        marked_at=datetime(2026, 6, 29, 15, 35),
        cutoff_time=time(15, 30),
        include_prior_sessions=True,
    )
    assert repaired.finalized_count == 1
    assert repaired.decisions[0].reason_code == "paper_order_expired_untriggered_previous_session_sweeper"
    assert store.load_state(order_dir).status is S23PaperOrderStatus.PAPER_ORDER_NOT_FILLED


def test_finalizer_dry_run_does_not_modify_state(tmp_path: Path) -> None:
    order_dir = tmp_path / "2026-06-29" / "session" / "BEAR_PUT"
    store = S23PaperOrderStateStore()
    store.save_state(order_dir, _waiting_order(entry_date=date(2026, 6, 29)))

    summary = S23PaperOrderFinalizer(order_store=store).finalize(
        tmp_path,
        session_date=date(2026, 6, 29),
        marked_at=datetime(2026, 6, 29, 15, 35),
        cutoff_time=time(15, 30),
        dry_run=True,
    )

    assert summary.finalized_count == 1
    assert summary.decisions[0].action == "WOULD_FINALIZE"
    assert store.load_state(order_dir).status is S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER
    assert not (order_dir / "paper_order_events.jsonl").exists()


def test_finalizer_cli_sweeps_all_targets_from_shared_config(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    module = _load_finalizer_script()
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    s23_root = tmp_path / "data" / "strategies" / "S23" / "fyers_morning_supervised_decision"
    s21_root = tmp_path / "data" / "strategies" / "S21" / "fyers_morning_supervised_decision"
    store = S23PaperOrderStateStore()
    store.save_state(
        s23_root / "2026-06-29" / "s23-session" / "BEAR_PUT",
        _waiting_order(entry_date=date(2026, 6, 29)),
    )
    store.save_state(
        s21_root / "2026-06-29" / "s21-session" / "BEAR_CALL",
        _waiting_order(entry_date=date(2026, 6, 29)),
    )
    targets_config = tmp_path / "config" / "paper_lifecycle_supervisor_targets.yaml"
    targets_config.parent.mkdir(parents=True)
    targets_config.write_text(
        "\n".join(
            [
                "targets:",
                "  - strategy_code: S23",
                "    config_path: config/paper.s23.fyers_connect_test.yaml",
                "    artifact_root: data/strategies/S23/fyers_morning_supervised_decision",
                "    process_lock_root: tmp/process_locks/s23_paper_watch",
                "    strategy_path: config/strategies/S23",
                "    reference_packet_path: config/reference_packets/s23.json",
                "    session_id_prefix: s23-fyers-morning-supervised-decision",
                "    executor: paper_morning_supervised",
                "    runner_script_path: scripts/run_s23.py",
                "    wrapper_script_path: scripts/start_s23.ps1",
                "  - strategy_code: S21",
                "    config_path: config/paper.s21.fyers_connect_test.yaml",
                "    artifact_root: data/strategies/S21/fyers_morning_supervised_decision",
                "    process_lock_root: tmp/process_locks/s21_paper_watch",
                "    strategy_path: config/strategies/S21",
                "    reference_packet_path: config/reference_packets/s21.json",
                "    session_id_prefix: s21-fyers-morning-supervised-decision",
                "    executor: paper_morning_supervised",
                "    runner_script_path: scripts/run_s21.py",
                "    wrapper_script_path: scripts/start_s21.ps1",
            ]
        ),
        encoding="utf-8",
    )

    exit_code = module.main(
        [
            "--targets-config",
            str(targets_config),
            "--session-date",
            "2026-06-29",
            "--allow-before-cutoff",
            "--dry-run",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary_count"] == 2
    assert payload["total_scanned_count"] == 2
    assert payload["total_finalized_count"] == 2
    assert {Path(item["artifact_root"]).name for item in payload["summaries"]} == {
        "fyers_morning_supervised_decision"
    }


def test_finalizer_cli_dashboard_fallback_uses_resolved_artifact_root(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    module = _load_finalizer_script()
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    captured = {}

    class FakeDashboardBuilder:
        def __init__(self, *, strategy_configs):
            captured["strategy_configs"] = strategy_configs

        def build(self, *, output_root):
            captured["output_root"] = output_root
            return type("Result", (), {"strategy_pages": {"S23": output_root / "strategies" / "S23"}})()

    monkeypatch.setattr(module, "TfisOperatorDashboardBuilder", FakeDashboardBuilder)

    exit_code = module.main(
        [
            "--artifact-root",
            "data/custom_strategy_root",
            "--session-date",
            "2026-06-29",
            "--allow-before-cutoff",
            "--rebuild-dashboard",
        ]
    )

    assert exit_code == 0
    strategy_config = captured["strategy_configs"][0]
    assert strategy_config.artifact_root == tmp_path / "data" / "custom_strategy_root"
    assert captured["output_root"] == tmp_path / "tmp" / "operator_dashboard"
    assert "Dashboard rebuilt: S23=" in capsys.readouterr().out


def _waiting_order(*, entry_date: date) -> S23PaperOrderState:
    return S23PaperOrderState(
        artifact_version=1,
        strategy_code="S23",
        strategy_branch="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        symbol="NIFTY",
        selected_contract_symbol="NIFTY_20260707_24300_PE",
        selected_contract_expiry=date(2026, 7, 7),
        selected_contract_option_type="PUT",
        selected_contract_strike=24300.0,
        expiry_type="WEEKLY",
        rollover_policy="T_MINUS_1",
        forced_close_time=time(12, 0),
        no_carry_past_expiry=True,
        order_side="SELL",
        trigger_rule="SELL_TRIGGER_WHEN_PREMIUM_AT_OR_BELOW_ENTRY",
        entry_date=entry_date,
        order_timestamp=datetime.combine(entry_date, time(9, 30)),
        planned_entry_price=212.75,
        target_price=85.10,
        stoploss_price=258.94,
        fsl_price=258.94,
        lots=1,
        quantity=65,
        status=S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER,
        last_updated_timestamp=datetime.combine(entry_date, time(12, 32)),
        last_market_price=387.30,
        last_market_bid=386.60,
        last_market_ask=387.85,
        last_reason_code="paper_order_waiting_quote_above_entry",
        last_message="Selected option premium is still above entry; the paper sell order remains waiting.",
    )
