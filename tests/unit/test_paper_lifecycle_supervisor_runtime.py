from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import replace
from datetime import date, datetime, time
from pathlib import Path

import pytest

from tfis.brokers import BrokerAdapterError, FyersBrokerAdapter
from tfis.domain import ExpiryType, MonthlyStatus, OptionType, RolloverPolicy, Segment, StrategyExpiryPolicy, StrategyRule
from tfis.normalized_events import EventEnvelope, PaperEventType, SelectedContractQuoteEvent
from tfis.paper import (
    build_paper_expiry_governance,
    build_paper_live_state_store_from_yaml,
    build_paper_position_manager,
    PaperLifecycleBrokerConfig,
    PaperLifecycleBrokerRuntime,
    PaperLifecycleRuntimeConfig,
    PaperLifecycleSupervisor,
    PaperLifecycleSupervisorTargetDiscovery,
    PaperOrderStateStore,
    PaperPositionStateStatus,
    PaperPositionStateStore,
    S23PaperPositionManager,
    S23PaperTradeLedgerEventType,
    S23PaperTradeLedgerStore,
    S23PaperTradeDecisionSummary,
    build_paper_broker_adapter,
    build_paper_broker_adapter_from_broker_config,
    ensure_paper_broker_runtime_healthy,
    inspect_paper_live_state_store_from_yaml,
    load_paper_broker_runtime,
    paper_broker_credentials_available,
    load_paper_runtime_guardrail_statuses,
    load_paper_runtime_fresh_entry_handoff_statuses,
    load_paper_runtime_broker_health_statuses,
    load_paper_runtime_heartbeat_statuses,
    load_paper_runtime_lifecycle_audit_statuses,
    load_paper_runtime_order_routing_statuses,
    load_paper_runtime_reconciliation_statuses,
    load_paper_runtime_waiting_order_statuses,
    load_paper_lifecycle_supervisor_target_specs,
    prepare_paper_broker_runtime_environment,
    validate_paper_lifecycle_runtime_guardrails,
)
from tfis.paper.fresh_entry_promotion import promote_blocked_fresh_entries as shared_promote_blocked_fresh_entries


def test_load_paper_lifecycle_supervisor_target_specs(tmp_path: Path) -> None:
    config_path = tmp_path / "targets.yaml"
    config_path.write_text(
        "\n".join(
            (
                "targets:",
                "  - strategy_code: S23",
                "    config_path: config/paper.s23.fyers_connect_test.yaml",
                "    artifact_root: data/strategies/S23/fyers_morning_supervised_decision",
                "    process_lock_root: tmp/process_locks/s23_paper_watch",
                "    strategy_path: config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
                "    reference_packet_path: config/reference_packets/s23_bear_put_live_decision_reference.json",
                "    session_id_prefix: s23-fyers-morning-supervised-decision",
                "    executor: s23_morning_supervised",
                "    runner_script_path: scripts/run_s23_fyers_0916_supervised_decision.py",
                "    wrapper_script_path: scripts/start_s23_fyers_morning_supervised_decision.ps1",
            )
        ),
        encoding="utf-8",
    )

    specs = load_paper_lifecycle_supervisor_target_specs(config_path, repo_root=tmp_path)

    assert len(specs) == 1
    assert specs[0].strategy_code == "S23"
    assert specs[0].config_path == (tmp_path / "config/paper.s23.fyers_connect_test.yaml").resolve()
    assert specs[0].artifact_root == (tmp_path / "data/strategies/S23/fyers_morning_supervised_decision").resolve()
    assert specs[0].process_lock_root == (tmp_path / "tmp/process_locks/s23_paper_watch").resolve()
    assert specs[0].strategy_path == (
        tmp_path / "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D"
    ).resolve()
    assert specs[0].reference_packet_path == (
        tmp_path / "config/reference_packets/s23_bear_put_live_decision_reference.json"
    ).resolve()
    assert specs[0].session_id_prefix == "s23-fyers-morning-supervised-decision"
    assert specs[0].executor == "paper_morning_supervised"
    assert specs[0].runner_script_path == (
        tmp_path / "scripts/run_s23_fyers_0916_supervised_decision.py"
    ).resolve()
    assert specs[0].wrapper_script_path == (
        tmp_path / "scripts/start_s23_fyers_morning_supervised_decision.ps1"
    ).resolve()


def test_target_discovery_finds_active_positions_and_waiting_orders(tmp_path: Path) -> None:
    artifact_root = tmp_path / "data" / "strategies" / "S23" / "fyers_morning_supervised_decision"
    open_dir = artifact_root / "2026-07-16" / "open-branch"
    wait_dir = artifact_root / "2026-07-17" / "wait-branch"
    stale_dir = artifact_root / "2026-07-15" / "stale-branch"
    open_dir.mkdir(parents=True, exist_ok=True)
    wait_dir.mkdir(parents=True, exist_ok=True)
    stale_dir.mkdir(parents=True, exist_ok=True)

    manager = S23PaperPositionManager(
        ledger_store=S23PaperTradeLedgerStore(global_ledger_root=tmp_path / "global-ledger"),
    )
    manager.open_from_live_decision(
        open_dir,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(session_date=date(2026, 7, 16)),
        opened_at=datetime(2026, 7, 16, 9, 31),
    )

    order_store = PaperOrderStateStore()
    order_store.create_waiting_order_from_live_decision(
        wait_dir,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(session_date=date(2026, 7, 17)),
        created_at=datetime(2026, 7, 17, 9, 30),
    )
    order_store.create_waiting_order_from_live_decision(
        stale_dir,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(session_date=date(2026, 7, 15)),
        created_at=datetime(2026, 7, 15, 9, 30),
    )

    config_path = tmp_path / "config" / "paper.s23.fyers_connect_test.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("broker:\n  timezone: Asia/Kolkata\n", encoding="utf-8")
    spec = load_paper_lifecycle_supervisor_target_specs(
        _targets_yaml(tmp_path, config_path=config_path, artifact_root=artifact_root),
        repo_root=tmp_path,
    )[0]

    targets = PaperLifecycleSupervisorTargetDiscovery().discover_targets(
        spec,
        effective_session_date=date(2026, 7, 17),
    )

    assert {(item.mode, item.directory.name) for item in targets} == {
        ("state", "open-branch"),
        ("order", "wait-branch"),
    }


def test_repo_supervisor_targets_yaml_carries_relaunch_metadata() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    specs = load_paper_lifecycle_supervisor_target_specs(
        repo_root / "config" / "paper_lifecycle_supervisor_targets.yaml",
        repo_root=repo_root,
    )

    by_code = {spec.strategy_code: spec for spec in specs}
    assert by_code["S23"].strategy_path is not None
    assert by_code["S23"].reference_packet_path is not None
    assert by_code["S23"].session_id_prefix == "s23-fyers-morning-supervised-decision"
    assert by_code["S23"].executor == "paper_morning_supervised"
    assert by_code["S23"].runner_script_path is not None
    assert by_code["S23"].wrapper_script_path is not None
    assert by_code["S21"].strategy_path is not None
    assert by_code["S21"].reference_packet_path is not None
    assert by_code["S21"].session_id_prefix == "s21-fyers-morning-supervised-decision"
    assert by_code["S21"].executor == "paper_morning_supervised"
    assert by_code["S21"].runner_script_path is not None
    assert by_code["S21"].wrapper_script_path is not None


def test_paper_lifecycle_runtime_config_loads_relative_payload_fixture(tmp_path: Path) -> None:
    fixture_path = tmp_path / "fixtures" / "sample_payload.json"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text("{}", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            (
                "broker:",
                "  provider: fyers",
                "  timezone: Asia/Kolkata",
                "  payload_fixture_path: fixtures/sample_payload.json",
                "  option_chain_strike_count: 120",
                "paper:",
                "  paper_mode_enabled: true",
                "  no_live_orders_allowed: true",
                "  kill_switch_enabled: true",
                "  session_kill_switch_active: false",
                "costs:",
                "  slippage_exit_points: 1.5",
            )
        ),
        encoding="utf-8",
    )

    config = PaperLifecycleRuntimeConfig.from_yaml(config_path)

    assert config.broker.provider == "fyers"
    assert config.broker.timezone == "Asia/Kolkata"
    assert config.broker.payload_fixture_path == str(fixture_path.resolve())
    assert config.broker.option_chain_strike_count == 120
    assert config.paper.paper_mode_enabled is True
    assert config.paper.no_live_orders_allowed is True
    assert config.paper.kill_switch_enabled is True
    assert config.paper.session_kill_switch_active is False
    assert config.costs.slippage_exit_points == 1.5


def test_build_paper_broker_adapter_from_broker_config_preserves_fixture_and_strike_count(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "fixtures" / "sample_payload.json"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text("{}", encoding="utf-8")

    adapter = build_paper_broker_adapter_from_broker_config(
        PaperLifecycleBrokerConfig(
            provider="fyers",
            timezone="Asia/Kolkata",
            payload_fixture_path=str(fixture_path),
            option_chain_strike_count=120,
        )
    )

    assert isinstance(adapter, FyersBrokerAdapter)
    assert adapter._payloads == {}
    assert adapter._option_chain_strike_count == 80

    live_adapter = build_paper_broker_adapter_from_broker_config(
        PaperLifecycleBrokerConfig(
            provider="fyers",
            timezone="Asia/Kolkata",
            payload_fixture_path=None,
            option_chain_strike_count=120,
        )
    )

    assert isinstance(live_adapter, FyersBrokerAdapter)
    assert live_adapter._option_chain_strike_count == 120


def test_paper_broker_credentials_available_reports_fixture_mode_as_ready(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "fixtures" / "sample_payload.json"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text("{}", encoding="utf-8")

    credentials_ready, message = paper_broker_credentials_available(
        PaperLifecycleBrokerConfig(
            provider="fyers",
            timezone="Asia/Kolkata",
            payload_fixture_path=str(fixture_path),
        )
    )

    assert credentials_ready is True
    assert message is None


def test_paper_broker_credentials_available_reports_missing_live_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FYERS_APP_ID", raising=False)
    monkeypatch.delenv("FYERS_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FYERS_CLIENT_ID", raising=False)

    credentials_ready, message = paper_broker_credentials_available(
        PaperLifecycleBrokerConfig(
            provider="fyers",
            timezone="Asia/Kolkata",
            payload_fixture_path=None,
        )
    )

    assert credentials_ready is False
    assert message is not None
    assert "FYERS_APP_ID" in message


def test_paper_lifecycle_runtime_guardrails_fail_for_unsafe_runtime_flags(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            (
                "source_mode: broker_fyers_live_fill_mode",
                "paper:",
                "  paper_mode_enabled: false",
                "  no_live_orders_allowed: false",
                "  kill_switch_enabled: false",
                "  session_kill_switch_active: true",
            )
        ),
        encoding="utf-8",
    )

    config = PaperLifecycleRuntimeConfig.from_yaml(config_path)
    failures = validate_paper_lifecycle_runtime_guardrails(config)

    assert any("source_mode must stay on a broker-backed paper-ingress path" in item for item in failures)
    assert "paper.paper_mode_enabled must be true" in failures
    assert "paper.no_live_orders_allowed must be true" in failures
    assert "paper.kill_switch_enabled must be true" in failures
    assert "paper.session_kill_switch_active must be false before runtime start" in failures


def test_load_paper_runtime_guardrail_statuses_reports_per_strategy_results(tmp_path: Path) -> None:
    pass_config = tmp_path / "config" / "paper.s23.yaml"
    fail_config = tmp_path / "config" / "paper.s21.yaml"
    pass_config.parent.mkdir(parents=True, exist_ok=True)
    pass_config.write_text(
        "\n".join(
            (
                "source_mode: broker_fyers_live_paper_ingress",
                "broker:",
                "  provider: fyers",
                "  timezone: Asia/Kolkata",
                "paper:",
                "  paper_mode_enabled: true",
                "  no_live_orders_allowed: true",
                "  kill_switch_enabled: true",
                "  session_kill_switch_active: false",
            )
        ),
        encoding="utf-8",
    )
    fail_config.write_text(
        "\n".join(
            (
                "source_mode: broker_fyers_live_fill_mode",
                "broker:",
                "  provider: fyers",
                "  timezone: Asia/Kolkata",
                "paper:",
                "  paper_mode_enabled: true",
                "  no_live_orders_allowed: false",
                "  kill_switch_enabled: true",
                "  session_kill_switch_active: false",
            )
        ),
        encoding="utf-8",
    )
    targets_path = tmp_path / "targets.yaml"
    targets_path.write_text(
        "\n".join(
            (
                "targets:",
                "  - strategy_code: S23",
                "    config_path: config/paper.s23.yaml",
                "    artifact_root: data/strategies/S23/root",
                "    process_lock_root: tmp/process_locks/s23",
                "    strategy_path: config/strategies/options_sell/s23",
                "    reference_packet_path: config/reference_packets/s23.json",
                "    session_id_prefix: s23-session",
                "    executor: paper_morning_supervised",
                "    runner_script_path: scripts/run_s23.py",
                "    wrapper_script_path: scripts/start_s23.ps1",
                "  - strategy_code: S21",
                "    config_path: config/paper.s21.yaml",
                "    artifact_root: data/strategies/S21/root",
                "    process_lock_root: tmp/process_locks/s21",
                "    strategy_path: config/strategies/options_sell/s21",
                "    reference_packet_path: config/reference_packets/s21.json",
                "    session_id_prefix: s21-session",
                "    executor: paper_morning_supervised",
                "    runner_script_path: scripts/run_s21.py",
                "    wrapper_script_path: scripts/start_s21.ps1",
            )
        ),
        encoding="utf-8",
    )

    statuses = load_paper_runtime_guardrail_statuses(targets_path, repo_root=tmp_path)

    by_code = {item.strategy_code: item for item in statuses}
    assert by_code["S23"].status == "PASS"
    assert by_code["S23"].source_mode == "broker_fyers_live_paper_ingress"
    assert by_code["S21"].status == "FAIL"
    assert "no_live_orders_allowed" in by_code["S21"].message


def test_load_paper_runtime_heartbeat_statuses_reports_owner_and_state_directory(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config" / "paper.s23.yaml"
    artifact_root = tmp_path / "data" / "strategies" / "S23" / "fyers_morning_supervised_decision"
    state_dir = artifact_root / "2026-07-21" / "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL"
    state_dir.mkdir(parents=True, exist_ok=True)
    live_state_root = tmp_path / "paper-live-state"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "\n".join(
            (
                "source_mode: broker_fyers_live_paper_ingress",
                "broker:",
                "  provider: fyers",
                "  timezone: Asia/Kolkata",
                "paper:",
                "  paper_mode_enabled: true",
                "  no_live_orders_allowed: true",
                "  kill_switch_enabled: true",
                "  session_kill_switch_active: false",
                "live_state:",
                "  enabled: true",
                "  provider: filesystem",
                f"  root: {live_state_root.as_posix()}",
            )
        ),
        encoding="utf-8",
    )
    targets_path = _targets_yaml(tmp_path, config_path=config_path, artifact_root=artifact_root)
    live_state_store = build_paper_live_state_store_from_yaml(config_path, strict=True)
    live_state_store.set_watch_heartbeat(
        session_date=date(2026, 7, 21),
        trade_id="S23-test-heartbeat",
        payload={
            "trade_id": "S23-test-heartbeat",
            "owner_id": "tfis-paper-lifecycle-supervisor:s23:1234",
            "timestamp": "2026-07-21T09:32:00+05:30",
            "status": "PAPER_ORDER_WAITING_FOR_TRIGGER",
            "selected_contract_symbol": "NIFTY_20260728_23950_CE",
            "state_directory": str(state_dir),
            "strategy_code": "S23",
            "supervisor_pid": 1234,
        },
    )

    statuses = load_paper_runtime_heartbeat_statuses(
        targets_path,
        repo_root=tmp_path,
        stale_after_seconds=10_000_000,
    )

    assert len(statuses) == 1
    assert statuses[0].status == "OK"
    assert statuses[0].latest_trade_id == "S23-test-heartbeat"
    assert statuses[0].latest_owner_id == "tfis-paper-lifecycle-supervisor:s23:1234"
    assert statuses[0].latest_state_directory == str(state_dir)
    assert statuses[0].latest_selected_contract_symbol == "NIFTY_20260728_23950_CE"


def test_load_paper_runtime_heartbeat_statuses_reports_market_data_unavailable_as_degraded(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config" / "paper.s23.yaml"
    artifact_root = tmp_path / "data" / "strategies" / "S23" / "fyers_morning_supervised_decision"
    live_state_root = tmp_path / "paper-live-state"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "\n".join(
            (
                "source_mode: broker_fyers_live_paper_ingress",
                "broker:",
                "  provider: fyers",
                "  timezone: Asia/Kolkata",
                "paper:",
                "  paper_mode_enabled: true",
                "  no_live_orders_allowed: true",
                "  kill_switch_enabled: true",
                "  session_kill_switch_active: false",
                "live_state:",
                "  enabled: true",
                "  provider: filesystem",
                f"  root: {live_state_root.as_posix()}",
            )
        ),
        encoding="utf-8",
    )
    targets_path = _targets_yaml(tmp_path, config_path=config_path, artifact_root=artifact_root)
    live_state_store = build_paper_live_state_store_from_yaml(config_path, strict=True)
    live_state_store.set_watch_heartbeat(
        session_date=date(2026, 7, 22),
        trade_id="S23-test-heartbeat",
        payload={
            "trade_id": "S23-test-heartbeat",
            "owner_id": "tfis-paper-lifecycle-supervisor:s23:1234",
            "timestamp": datetime.now().astimezone().isoformat(),
            "status": "MARKET_DATA_UNAVAILABLE",
            "reason_code": "selected_contract_event_fetch_failed",
            "selected_contract_symbol": "NIFTY_20260728_23950_CE",
            "state_directory": str(artifact_root / "2026-07-22" / "session" / "BRANCH"),
            "strategy_code": "S23",
            "supervisor_pid": 1234,
        },
    )

    statuses = load_paper_runtime_heartbeat_statuses(
        targets_path,
        repo_root=tmp_path,
        stale_after_seconds=10_000_000,
    )

    assert statuses[0].status == "DEGRADED"
    assert statuses[0].latest_runtime_status == "MARKET_DATA_UNAVAILABLE"
    assert statuses[0].latest_reason_code == "selected_contract_event_fetch_failed"
    assert "MARKET_DATA_UNAVAILABLE" in statuses[0].message


def test_load_paper_runtime_lifecycle_audit_statuses_reports_present_audit(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config" / "paper.s23.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("broker:\n  provider: fyers\n  timezone: Asia/Kolkata\n", encoding="utf-8")
    artifact_root = tmp_path / "data" / "strategies" / "S23" / "root"
    order_dir = artifact_root / "2026-07-22" / "branch-waiting"
    order_dir.mkdir(parents=True, exist_ok=True)
    PaperOrderStateStore().create_waiting_order_from_live_decision(
        order_dir,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(session_date=date(2026, 7, 22)),
        created_at=datetime(2026, 7, 22, 9, 30),
    )
    (order_dir / "paper_lifecycle_supervisor_events.jsonl").write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "event_timestamp": datetime.now().astimezone().isoformat(),
                "event_type": "LIFECYCLE_STEP",
                "status": "PAPER_ORDER_WAITING_FOR_TRIGGER",
                "reason_code": "paper_order_waiting_quote_above_entry",
                "strategy_code": "S23",
                "trade_id": "trade-1",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    statuses = load_paper_runtime_lifecycle_audit_statuses(
        _targets_yaml(tmp_path, config_path=config_path, artifact_root=artifact_root),
        repo_root=tmp_path,
        stale_after_seconds=10_000_000,
    )

    assert len(statuses) == 1
    assert statuses[0].status == "PASS"
    assert statuses[0].managed_state_count == 1
    assert statuses[0].audit_state_count == 1
    assert statuses[0].missing_audit_count == 0
    assert statuses[0].latest_event_type == "LIFECYCLE_STEP"
    assert statuses[0].latest_reason_code == "paper_order_waiting_quote_above_entry"


def test_load_paper_runtime_lifecycle_audit_statuses_flags_legacy_missing_audit(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config" / "paper.s23.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("broker:\n  provider: fyers\n  timezone: Asia/Kolkata\n", encoding="utf-8")
    artifact_root = tmp_path / "data" / "strategies" / "S23" / "root"
    order_dir = artifact_root / "2026-07-22" / "branch-waiting"
    order_dir.mkdir(parents=True, exist_ok=True)
    PaperOrderStateStore().create_waiting_order_from_live_decision(
        order_dir,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(session_date=date(2026, 7, 22)),
        created_at=datetime(2026, 7, 22, 9, 30),
    )

    statuses = load_paper_runtime_lifecycle_audit_statuses(
        _targets_yaml(tmp_path, config_path=config_path, artifact_root=artifact_root),
        repo_root=tmp_path,
    )

    assert statuses[0].status == "ATTENTION"
    assert statuses[0].managed_state_count == 1
    assert statuses[0].audit_state_count == 0
    assert statuses[0].missing_audit_count == 1
    assert "missing=1" in statuses[0].message


def test_load_paper_runtime_lifecycle_audit_statuses_ignores_terminal_order_without_audit(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config" / "paper.s23.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("broker:\n  provider: fyers\n  timezone: Asia/Kolkata\n", encoding="utf-8")
    artifact_root = tmp_path / "data" / "strategies" / "S23" / "root"
    order_dir = artifact_root / "2026-07-22" / "branch-not-filled"
    order_dir.mkdir(parents=True, exist_ok=True)
    order_store = PaperOrderStateStore()
    order_store.create_waiting_order_from_live_decision(
        order_dir,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(session_date=date(2026, 7, 22)),
        created_at=datetime(2026, 7, 22, 9, 30),
    )
    order_store.mark_not_filled(
        order_dir,
        marked_at=datetime(2026, 7, 22, 15, 30),
        reason_code="paper_order_cutoff_not_filled",
        message="Order was not filled by cutoff.",
    )

    statuses = load_paper_runtime_lifecycle_audit_statuses(
        _targets_yaml(tmp_path, config_path=config_path, artifact_root=artifact_root),
        repo_root=tmp_path,
    )

    assert statuses[0].status == "PASS"
    assert statuses[0].managed_state_count == 1
    assert statuses[0].audit_state_count == 0
    assert statuses[0].missing_audit_count == 0
    assert statuses[0].actionable_state_count == 0


def test_load_paper_runtime_lifecycle_audit_statuses_fails_invalid_audit(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config" / "paper.s23.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("broker:\n  provider: fyers\n  timezone: Asia/Kolkata\n", encoding="utf-8")
    artifact_root = tmp_path / "data" / "strategies" / "S23" / "root"
    order_dir = artifact_root / "2026-07-22" / "branch-waiting"
    order_dir.mkdir(parents=True, exist_ok=True)
    PaperOrderStateStore().create_waiting_order_from_live_decision(
        order_dir,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(session_date=date(2026, 7, 22)),
        created_at=datetime(2026, 7, 22, 9, 30),
    )
    (order_dir / "paper_lifecycle_supervisor_events.jsonl").write_text("{not-json}\n", encoding="utf-8")

    statuses = load_paper_runtime_lifecycle_audit_statuses(
        _targets_yaml(tmp_path, config_path=config_path, artifact_root=artifact_root),
        repo_root=tmp_path,
    )

    assert statuses[0].status == "FAIL"
    assert statuses[0].invalid_audit_count == 1
    assert "invalid" in statuses[0].message


def test_load_paper_runtime_waiting_order_statuses_passes_current_session_waiting_order(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config" / "paper.s23.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("broker:\n  provider: fyers\n  timezone: Asia/Kolkata\n", encoding="utf-8")
    artifact_root = tmp_path / "data" / "strategies" / "S23" / "root"
    order_dir = artifact_root / "2026-07-22" / "branch-waiting"
    order_dir.mkdir(parents=True, exist_ok=True)
    PaperOrderStateStore().create_waiting_order_from_live_decision(
        order_dir,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(session_date=date(2026, 7, 22)),
        created_at=datetime(2026, 7, 22, 9, 30),
    )

    statuses = load_paper_runtime_waiting_order_statuses(
        _targets_yaml(tmp_path, config_path=config_path, artifact_root=artifact_root),
        repo_root=tmp_path,
        session_date=date(2026, 7, 22),
    )

    assert len(statuses) == 1
    assert statuses[0].status == "PASS"
    assert statuses[0].waiting_order_count == 1
    assert statuses[0].current_session_waiting_order_count == 1
    assert statuses[0].stale_waiting_order_count == 0


def test_load_paper_runtime_waiting_order_statuses_fails_prior_session_waiting_order(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config" / "paper.s23.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("broker:\n  provider: fyers\n  timezone: Asia/Kolkata\n", encoding="utf-8")
    artifact_root = tmp_path / "data" / "strategies" / "S23" / "root"
    order_dir = artifact_root / "2026-07-21" / "branch-waiting"
    order_dir.mkdir(parents=True, exist_ok=True)
    PaperOrderStateStore().create_waiting_order_from_live_decision(
        order_dir,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(session_date=date(2026, 7, 21)),
        created_at=datetime(2026, 7, 21, 9, 30),
    )

    statuses = load_paper_runtime_waiting_order_statuses(
        _targets_yaml(tmp_path, config_path=config_path, artifact_root=artifact_root),
        repo_root=tmp_path,
        session_date=date(2026, 7, 22),
    )

    assert statuses[0].status == "FAIL"
    assert statuses[0].waiting_order_count == 1
    assert statuses[0].current_session_waiting_order_count == 0
    assert statuses[0].stale_waiting_order_count == 1
    assert statuses[0].latest_stale_order_directory == str(order_dir.resolve())
    assert "finalizer or operator review" in statuses[0].message


def test_load_paper_runtime_order_routing_statuses_reports_per_strategy_results(tmp_path: Path) -> None:
    pass_config = tmp_path / "config" / "paper.s23.yaml"
    fail_config = tmp_path / "config" / "paper.s21.yaml"
    pass_config.parent.mkdir(parents=True, exist_ok=True)
    pass_config.write_text(
        "\n".join(
            (
                "source_mode: broker_fyers_live_paper_ingress",
                "broker:",
                "  provider: fyers",
                "  timezone: Asia/Kolkata",
                "paper:",
                "  paper_mode_enabled: true",
                "  no_live_orders_allowed: true",
                "  kill_switch_enabled: true",
                "  session_kill_switch_active: false",
            )
        ),
        encoding="utf-8",
    )
    fail_config.write_text(
        "\n".join(
            (
                "source_mode: broker_fyers_live_paper_ingress",
                "broker:",
                "  provider: fyers",
                "  timezone: Asia/Kolkata",
                "paper:",
                "  paper_mode_enabled: true",
                "  no_live_orders_allowed: false",
                "  kill_switch_enabled: true",
                "  session_kill_switch_active: false",
            )
        ),
        encoding="utf-8",
    )
    targets_path = tmp_path / "targets.yaml"
    targets_path.write_text(
        "\n".join(
            (
                "targets:",
                "  - strategy_code: S23",
                "    config_path: config/paper.s23.yaml",
                "    artifact_root: data/strategies/S23/root",
                "    process_lock_root: tmp/process_locks/s23",
                "    strategy_path: config/strategies/options_sell/s23",
                "    reference_packet_path: config/reference_packets/s23.json",
                "    session_id_prefix: s23-session",
                "    executor: paper_morning_supervised",
                "    runner_script_path: scripts/run_s23.py",
                "    wrapper_script_path: scripts/start_s23.ps1",
                "  - strategy_code: S21",
                "    config_path: config/paper.s21.yaml",
                "    artifact_root: data/strategies/S21/root",
                "    process_lock_root: tmp/process_locks/s21",
                "    strategy_path: config/strategies/options_sell/s21",
                "    reference_packet_path: config/reference_packets/s21.json",
                "    session_id_prefix: s21-session",
                "    executor: paper_morning_supervised",
                "    runner_script_path: scripts/run_s21.py",
                "    wrapper_script_path: scripts/start_s21.ps1",
            )
        ),
        encoding="utf-8",
    )

    statuses = load_paper_runtime_order_routing_statuses(targets_path, repo_root=tmp_path)

    by_code = {item.strategy_code: item for item in statuses}
    assert by_code["S23"].status == "PASS"
    assert by_code["S23"].place_order_blocked is True
    assert by_code["S23"].modify_order_blocked is True
    assert by_code["S23"].cancel_order_blocked is True
    assert by_code["S21"].status == "FAIL"
    assert "no_live_orders_allowed" in by_code["S21"].message


def test_load_paper_runtime_reconciliation_statuses_reports_per_strategy_results(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config" / "paper.s23.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "\n".join(
            (
                "source_mode: broker_fyers_live_paper_ingress",
                "broker:",
                "  provider: fyers",
                "  timezone: Asia/Kolkata",
                "paper:",
                "  paper_mode_enabled: true",
                "  no_live_orders_allowed: true",
                "  kill_switch_enabled: true",
                "  session_kill_switch_active: false",
            )
        ),
        encoding="utf-8",
    )
    targets_path = tmp_path / "targets.yaml"
    targets_path.write_text(
        "\n".join(
            (
                "targets:",
                "  - strategy_code: S23",
                "    config_path: config/paper.s23.yaml",
                "    artifact_root: data/strategies/S23/root",
                "    process_lock_root: tmp/process_locks/s23",
                "    strategy_path: config/strategies/options_sell/s23",
                "    reference_packet_path: config/reference_packets/s23.json",
                "    session_id_prefix: s23-session",
                "    executor: paper_morning_supervised",
                "    runner_script_path: scripts/run_s23.py",
                "    wrapper_script_path: scripts/start_s23.ps1",
                "  - strategy_code: S21",
                "    config_path: config/paper.s23.yaml",
                "    artifact_root: data/strategies/S21/root",
                "    process_lock_root: tmp/process_locks/s21",
                "    strategy_path: config/strategies/options_sell/s21",
                "    reference_packet_path: config/reference_packets/s21.json",
                "    session_id_prefix: s21-session",
                "    executor: paper_morning_supervised",
                "    runner_script_path: scripts/run_s21.py",
                "    wrapper_script_path: scripts/start_s21.ps1",
            )
        ),
        encoding="utf-8",
    )

    open_dir = tmp_path / "data" / "strategies" / "S23" / "root" / "2026-07-21" / "branch-open"
    conflict_dir = tmp_path / "data" / "strategies" / "S21" / "root" / "2026-07-21" / "branch-conflict"
    open_dir.mkdir(parents=True, exist_ok=True)
    conflict_dir.mkdir(parents=True, exist_ok=True)

    state_store = PaperPositionStateStore()
    ledger_store_s23 = S23PaperTradeLedgerStore(
        global_ledger_root=tmp_path / "tmp" / "paper_trade_ledger",
        global_ledger_filename="s23_paper_trade_ledger.jsonl",
    )
    ledger_store_s21 = S23PaperTradeLedgerStore(
        global_ledger_root=tmp_path / "tmp" / "paper_trade_ledger",
        global_ledger_filename="s21_paper_trade_ledger.jsonl",
    )

    open_state = state_store.create_open_position_state(
        strategy_code="S23",
        unique_code="S23_BRANCH",
        symbol="NIFTY",
        option_type=OptionType.PUT,
        selected_contract_symbol="NIFTY_20260723_24150_PE",
        expiry_date=date(2026, 7, 23),
        expiry_type=ExpiryType.WEEKLY,
        rollover_policy=RolloverPolicy.T_MINUS_1,
        forced_close_time=time(12, 0),
        no_carry_past_expiry=True,
        entry_date=date(2026, 7, 21),
        entry_timestamp=datetime(2026, 7, 21, 9, 30),
        entry_price=194.25,
        lots=1,
        quantity=65,
        side="SELL",
        target_price=77.70,
        stoploss_price=242.0,
        fsl_price=None,
        trp_price=None,
        carry_forward_allowed=True,
        last_updated_timestamp=datetime(2026, 7, 21, 9, 30),
    )
    state_store.save_state(open_dir, open_state)
    ledger_store_s23.append(
        open_dir,
        ledger_store_s23.build_row(
            state=open_state,
            event_timestamp=datetime(2026, 7, 21, 9, 30),
            event_type=S23PaperTradeLedgerEventType.OPEN,
            session_date=date(2026, 7, 21),
            manager_status="PAPER_POSITION_OPENED",
            reason_code="opened",
            message="opened",
            current_price=194.25,
            state_directory=open_dir,
        ),
    )

    conflict_state = replace(
        open_state,
        strategy_code="S21",
        unique_code="S21_BRANCH",
        symbol="BANKNIFTY",
        selected_contract_symbol="BANKNIFTY_20260729_58000_PE",
        lifecycle_status=PaperPositionStateStatus.PAPER_POSITION_CLOSED,
        last_updated_timestamp=datetime(2026, 7, 21, 12, 58),
    )
    state_store.save_state(conflict_dir, conflict_state)
    session_ledger_path = conflict_dir / "paper_trade_ledger.jsonl"
    session_ledger_path.write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "event_timestamp": "2026-07-21T09:30:00",
                "event_type": "OPEN",
                "trade_id": ledger_store_s21.trade_id_for_state(conflict_state),
                "strategy_id": "S21:S21_BRANCH",
                "strategy_code": "S21",
                "strategy_branch": "S21_BRANCH",
                "symbol": "BANKNIFTY",
                "option_type": "PUT",
                "selected_contract_symbol": "BANKNIFTY_20260729_58000_PE",
                "expiry_date": "2026-07-29",
                "side": "SELL",
                "lots": 1,
                "quantity": 65,
                "entry_date": "2026-07-21",
                "entry_timestamp": "2026-07-21T09:30:00",
                "entry_price": 194.25,
                "target_price": 77.70,
                "stoploss_price": 242.0,
                "fsl_price": None,
                "trp_price": None,
                "session_date": "2026-07-21",
                "lifecycle_status": "PAPER_POSITION_OPEN",
                "manager_status": "PAPER_POSITION_OPENED",
                "reason_code": "opened",
                "message": "opened",
                "current_price": 444.0,
                "state_directory": str(conflict_dir),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    statuses = load_paper_runtime_reconciliation_statuses(targets_path, repo_root=tmp_path)

    by_code = {item.strategy_code: item for item in statuses}
    assert by_code["S23"].status == "PASS"
    assert by_code["S23"].persisted_state_count == 1
    assert by_code["S21"].status == "FAIL"
    assert "terminal position state" in by_code["S21"].message


def test_load_paper_runtime_reconciliation_statuses_checks_order_event_authority(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config" / "paper.s23.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("broker:\n  provider: fyers\n  timezone: Asia/Kolkata\n", encoding="utf-8")
    artifact_root = tmp_path / "data" / "strategies" / "S23" / "root"
    order_dir = artifact_root / "2026-07-21" / "branch-waiting"
    order_dir.mkdir(parents=True, exist_ok=True)

    PaperOrderStateStore().create_waiting_order_from_live_decision(
        order_dir,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(session_date=date(2026, 7, 21)),
        created_at=datetime(2026, 7, 21, 9, 30),
    )

    statuses = load_paper_runtime_reconciliation_statuses(
        _targets_yaml(tmp_path, config_path=config_path, artifact_root=artifact_root),
        repo_root=tmp_path,
    )

    assert len(statuses) == 1
    assert statuses[0].status == "PASS"
    assert statuses[0].persisted_state_count == 0
    assert statuses[0].checked_trade_count == 0
    assert statuses[0].persisted_order_state_count == 1
    assert statuses[0].checked_order_event_count == 1
    assert statuses[0].conflict_count == 0


def test_load_paper_runtime_reconciliation_statuses_fails_order_event_conflict(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config" / "paper.s23.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("broker:\n  provider: fyers\n  timezone: Asia/Kolkata\n", encoding="utf-8")
    artifact_root = tmp_path / "data" / "strategies" / "S23" / "root"
    order_dir = artifact_root / "2026-07-21" / "branch-conflict"
    order_dir.mkdir(parents=True, exist_ok=True)

    PaperOrderStateStore().create_waiting_order_from_live_decision(
        order_dir,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(session_date=date(2026, 7, 21)),
        created_at=datetime(2026, 7, 21, 9, 30),
    )
    events_path = order_dir / "paper_order_events.jsonl"
    events_path.write_text(
        events_path.read_text(encoding="utf-8")
        + json.dumps(
            {
                "artifact_version": 1,
                "timestamp": "2026-07-21T15:35:00",
                "session_date": "2026-07-21",
                "status": "PAPER_ORDER_NOT_FILLED",
                "selected_contract_symbol": "NIFTY_20260723_24150_PE",
                "planned_entry_price": 194.25,
                "reason_code": "test_conflict",
                "message": "latest event disagrees with persisted order state",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    statuses = load_paper_runtime_reconciliation_statuses(
        _targets_yaml(tmp_path, config_path=config_path, artifact_root=artifact_root),
        repo_root=tmp_path,
    )

    assert len(statuses) == 1
    assert statuses[0].status == "FAIL"
    assert statuses[0].persisted_order_state_count == 1
    assert statuses[0].checked_order_event_count == 1
    assert "order state PAPER_ORDER_WAITING_FOR_TRIGGER conflicts" in statuses[0].message


def test_load_paper_runtime_fresh_entry_handoff_statuses_reports_marker_resolved_close(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config" / "paper.s23.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("broker:\n  provider: fyers\n  timezone: Asia/Kolkata\n", encoding="utf-8")
    artifact_root = tmp_path / "data" / "strategies" / "S23" / "root"
    state_dir = artifact_root / "2026-07-21" / "branch-a"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "fresh_decision_launch.json").write_text(
        json.dumps(
            {
                "launched_at": "2026-07-21T10:05:00+05:30",
                "strategy_code": "S23",
                "trade_id": "trade-1",
                "pid": 1234,
            }
        ),
        encoding="utf-8",
    )
    (state_dir / "paper_trade_ledger.jsonl").write_text(
        json.dumps(
            {
                "event_timestamp": "2026-07-21T10:00:00+05:30",
                "event_type": "CLOSE",
                "trade_id": "trade-1",
                "strategy_code": "S23",
                "strategy_branch": "BRANCH_A",
                "lifecycle_status": "PAPER_FRESH_ENTRY_REQUIRED",
                "manager_status": "PAPER_POSITION_FRESH_ENTRY_REQUIRED",
                "fresh_entry_required": True,
                "state_directory": str(state_dir),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    targets_path = _targets_yaml(tmp_path, config_path=config_path, artifact_root=artifact_root)

    statuses = load_paper_runtime_fresh_entry_handoff_statuses(targets_path, repo_root=tmp_path)

    assert len(statuses) == 1
    status = statuses[0]
    assert status.strategy_code == "S23"
    assert status.status == "PASS"
    assert status.fresh_close_count == 1
    assert status.resolved_count == 1
    assert status.unresolved_count == 0
    assert "confirmed" in status.message


def test_load_paper_runtime_fresh_entry_handoff_statuses_reports_subsequent_waiting_order_as_resolved(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config" / "paper.s23.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("broker:\n  provider: fyers\n  timezone: Asia/Kolkata\n", encoding="utf-8")
    artifact_root = tmp_path / "data" / "strategies" / "S23" / "root"
    state_dir = artifact_root / "2026-07-21" / "branch-a"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "paper_trade_ledger.jsonl").write_text(
        "\n".join(
            (
                json.dumps(
                    {
                        "event_timestamp": "2026-07-21T10:00:00+05:30",
                        "event_type": "CLOSE",
                        "trade_id": "trade-1",
                        "strategy_code": "S23",
                        "strategy_branch": "BRANCH_A",
                        "lifecycle_status": "PAPER_FRESH_ENTRY_REQUIRED",
                        "manager_status": "PAPER_POSITION_FRESH_ENTRY_REQUIRED",
                        "fresh_entry_required": True,
                        "state_directory": str(state_dir),
                    }
                ),
                json.dumps(
                    {
                        "event_timestamp": "2026-07-21T10:02:00+05:30",
                        "event_type": "ORDER_WAITING",
                        "trade_id": "trade-2",
                        "strategy_code": "S23",
                        "strategy_branch": "BRANCH_A",
                        "lifecycle_status": "ORDER_WAITING_FOR_TRIGGER",
                        "manager_status": "PAPER_ORDER_WAITING_FOR_TRIGGER",
                        "fresh_entry_required": False,
                        "state_directory": str(state_dir),
                    }
                ),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    targets_path = _targets_yaml(tmp_path, config_path=config_path, artifact_root=artifact_root)

    statuses = load_paper_runtime_fresh_entry_handoff_statuses(targets_path, repo_root=tmp_path)

    assert statuses[0].status == "PASS"
    assert statuses[0].resolved_count == 1
    assert statuses[0].unresolved_count == 0


def test_load_paper_runtime_fresh_entry_handoff_statuses_reports_later_branch_session_artifact_as_resolved(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config" / "paper.s23.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("broker:\n  provider: fyers\n  timezone: Asia/Kolkata\n", encoding="utf-8")
    artifact_root = tmp_path / "data" / "strategies" / "S23" / "root"
    closed_state_dir = artifact_root / "2026-07-06" / "session-closed" / "BRANCH_A"
    later_branch_dir = artifact_root / "2026-07-21" / "session-later" / "BRANCH_A"
    closed_state_dir.mkdir(parents=True, exist_ok=True)
    later_branch_dir.mkdir(parents=True, exist_ok=True)
    (closed_state_dir / "paper_trade_ledger.jsonl").write_text(
        json.dumps(
            {
                "event_timestamp": "2026-07-06T09:32:19+05:30",
                "event_type": "CLOSE",
                "trade_id": "trade-1",
                "strategy_code": "S23",
                "strategy_branch": "BRANCH_A",
                "lifecycle_status": "PAPER_FRESH_ENTRY_REQUIRED",
                "manager_status": "PAPER_POSITION_FRESH_ENTRY_REQUIRED",
                "fresh_entry_required": True,
                "session_date": "2026-07-06",
                "state_directory": str(closed_state_dir),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (later_branch_dir / "trade_decision_summary.json").write_text(
        json.dumps({"summary": {"status": "READY"}}),
        encoding="utf-8",
    )
    targets_path = _targets_yaml(tmp_path, config_path=config_path, artifact_root=artifact_root)

    statuses = load_paper_runtime_fresh_entry_handoff_statuses(targets_path, repo_root=tmp_path)

    assert statuses[0].status == "PASS"
    assert statuses[0].resolved_count == 1
    assert statuses[0].unresolved_count == 0


def test_load_paper_runtime_fresh_entry_handoff_statuses_reports_unresolved_close(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config" / "paper.s23.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("broker:\n  provider: fyers\n  timezone: Asia/Kolkata\n", encoding="utf-8")
    artifact_root = tmp_path / "data" / "strategies" / "S23" / "root"
    state_dir = artifact_root / "2026-07-21" / "branch-a"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "paper_trade_ledger.jsonl").write_text(
        json.dumps(
            {
                "event_timestamp": "2026-07-21T10:00:00+05:30",
                "event_type": "CLOSE",
                "trade_id": "trade-1",
                "strategy_code": "S23",
                "strategy_branch": "BRANCH_A",
                "lifecycle_status": "PAPER_FRESH_ENTRY_REQUIRED",
                "manager_status": "PAPER_POSITION_FRESH_ENTRY_REQUIRED",
                "fresh_entry_required": True,
                "state_directory": str(state_dir),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    targets_path = _targets_yaml(tmp_path, config_path=config_path, artifact_root=artifact_root)

    statuses = load_paper_runtime_fresh_entry_handoff_statuses(targets_path, repo_root=tmp_path)

    assert statuses[0].status == "FAIL"
    assert statuses[0].fresh_close_count == 1
    assert statuses[0].resolved_count == 0
    assert statuses[0].unresolved_count == 1
    assert "trade-1@BRANCH_A" in statuses[0].message


def test_build_paper_broker_adapter_returns_fyers_adapter_for_supported_provider(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            (
                "broker:",
                "  provider: fyers",
                "  timezone: Asia/Kolkata",
            )
        ),
        encoding="utf-8",
    )

    adapter = build_paper_broker_adapter(PaperLifecycleRuntimeConfig.from_yaml(config_path))

    assert isinstance(adapter, FyersBrokerAdapter)


def test_load_paper_broker_runtime_builds_timezone_and_adapter(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            (
                "broker:",
                "  provider: fyers",
                "  timezone: Asia/Kolkata",
            )
        ),
        encoding="utf-8",
    )

    runtime = load_paper_broker_runtime(config_path)

    assert isinstance(runtime, PaperLifecycleBrokerRuntime)
    assert runtime.config.broker.provider == "fyers"
    assert runtime.timezone_name == "Asia/Kolkata"
    assert runtime.timezone.key == "Asia/Kolkata"
    assert isinstance(runtime.adapter, FyersBrokerAdapter)


def test_build_paper_position_manager_routes_supported_strategy_codes() -> None:
    s23_manager = build_paper_position_manager(strategy_code="S23")
    s21_manager = build_paper_position_manager(strategy_code="S21")

    assert isinstance(s23_manager, S23PaperPositionManager)
    assert isinstance(s21_manager, S23PaperPositionManager)


def test_build_paper_expiry_governance_routes_supported_strategy_codes() -> None:
    s23_governance = build_paper_expiry_governance(strategy_code="S23")
    s21_governance = build_paper_expiry_governance(strategy_code="S21")

    assert s23_governance.__class__.__name__ == "PaperExpiryGovernance"
    assert s21_governance.__class__.__name__ == "PaperExpiryGovernance"


def test_paper_lifecycle_supervisor_default_manager_uses_strategy_factory() -> None:
    s21_supervisor = PaperLifecycleSupervisor(strategy_code="S21")
    s23_supervisor = PaperLifecycleSupervisor(strategy_code="S23")

    assert isinstance(s21_supervisor._position_manager, S23PaperPositionManager)
    assert isinstance(s23_supervisor._position_manager, S23PaperPositionManager)


def test_build_paper_position_manager_fails_closed_for_unknown_strategy() -> None:
    with pytest.raises(RuntimeError, match="Unsupported paper position manager strategy code"):
        build_paper_position_manager(strategy_code="S99")


def test_build_paper_expiry_governance_fails_closed_for_unknown_strategy() -> None:
    with pytest.raises(ValueError, match="Unsupported paper expiry governance strategy code"):
        build_paper_expiry_governance(strategy_code="S99")


def test_build_paper_broker_adapter_fails_closed_for_unknown_provider(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            (
                "broker:",
                "  provider: unsupported",
                "  timezone: Asia/Kolkata",
            )
        ),
        encoding="utf-8",
    )

    config = PaperLifecycleRuntimeConfig.from_yaml(config_path)

    with pytest.raises(RuntimeError, match="Unsupported paper lifecycle broker provider"):
        build_paper_broker_adapter(config)


def test_prepare_paper_broker_runtime_environment_uses_fyers_auth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            (
                "broker:",
                "  provider: fyers",
                "  timezone: Asia/Kolkata",
            )
        ),
        encoding="utf-8",
    )
    config = PaperLifecycleRuntimeConfig.from_yaml(config_path)
    calls: list[tuple[object, bool]] = []

    def _fake_prepare(*, tfis_root, skip_refresh):
        calls.append((tfis_root, skip_refresh))

    monkeypatch.setattr(
        "tfis.brokers.fyers_token.prepare_fyers_env_from_tfis",
        _fake_prepare,
    )

    prepare_paper_broker_runtime_environment(
        config,
        tfis_root=tmp_path,
        skip_refresh=True,
    )

    assert calls == [(tmp_path, True)]


def test_inspect_paper_live_state_store_from_yaml_reports_enabled_redis_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            (
                "storage:",
                "  live_state:",
                "    enabled: true",
                "    provider: redis",
                "    namespace: tfis",
                "    environment: paper",
                "    strategy_id: s23",
                "  redis:",
                "    host: localhost",
                "    port: 6379",
                "    db: 1",
            )
        ),
        encoding="utf-8",
    )

    class FakeRedis:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def ping(self):
            return True

    monkeypatch.setitem(sys.modules, "redis", type("RedisModule", (), {"Redis": FakeRedis}))

    diagnostics = inspect_paper_live_state_store_from_yaml(config_path)

    assert diagnostics.status == "PASS"
    assert diagnostics.backend == "redis"


def test_build_paper_live_state_store_from_yaml_strict_raises_when_backend_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            (
                "storage:",
                "  live_state:",
                "    enabled: true",
                "    provider: redis",
                "    namespace: tfis",
                "    environment: paper",
                "    strategy_id: s23",
                "  redis:",
                "    host: localhost",
                "    port: 6379",
                "    db: 1",
            )
        ),
        encoding="utf-8",
    )

    class BrokenRedis:
        def __init__(self, **kwargs):
            raise RuntimeError("redis unavailable")

    monkeypatch.setitem(sys.modules, "redis", type("RedisModule", (), {"Redis": BrokenRedis}))

    with pytest.raises(RuntimeError, match="live-state storage is unavailable"):
        build_paper_live_state_store_from_yaml(config_path, strict=True)


def test_runtime_environment_preparation_is_deduped_per_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_tfis_paper_lifecycle_supervisor.py"
    spec = importlib.util.spec_from_file_location("run_tfis_paper_lifecycle_supervisor", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            (
                "broker:",
                "  provider: fyers",
                "  timezone: Asia/Kolkata",
            )
        ),
        encoding="utf-8",
    )
    config = PaperLifecycleRuntimeConfig.from_yaml(config_path)
    calls: list[tuple[str, bool]] = []

    def _fake_prepare(runtime_config, *, tfis_root, skip_refresh):
        calls.append((runtime_config.broker.provider, skip_refresh))

    monkeypatch.setattr(module, "prepare_paper_broker_runtime_environment", _fake_prepare)
    runtime = module._TargetRuntime(
        spec=load_paper_lifecycle_supervisor_target_specs(
            _targets_yaml(
                tmp_path,
                config_path=config_path,
                artifact_root=tmp_path / "data" / "strategies" / "S23",
            ),
            repo_root=tmp_path,
        )[0],
        config=config,
        timezone_name="Asia/Kolkata",
        timezone=module.ZoneInfo("Asia/Kolkata"),
        adapter=object(),
        live_state_store=object(),
        supervisor=object(),
    )

    module._prepare_runtime_environments(
        (runtime, runtime),
        tfis_root=str(tmp_path),
        skip_refresh=False,
    )

    assert calls == [("fyers", False)]


def test_supervisor_script_supports_operator_control_root_and_signatures() -> None:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_tfis_paper_lifecycle_supervisor.py"
    spec = importlib.util.spec_from_file_location("run_tfis_paper_lifecycle_supervisor", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    parser = module.build_parser()
    args = parser.parse_args([])

    assert args.control_root == "tmp/operator_controls"
    signature = module._control_signature(
        type(
            "ControlState",
            (),
            {
                "global_pause_active": False,
                "paused_strategies": frozenset({"S23", "S21"}),
            },
        )()
    )
    assert signature == (False, ("S21", "S23"))


def test_supervisor_script_appends_lifecycle_audit_event(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_tfis_paper_lifecycle_supervisor.py"
    spec = importlib.util.spec_from_file_location("run_tfis_paper_lifecycle_supervisor", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    state_dir = tmp_path / "state"
    result_path = module._append_supervisor_audit_event(
        state_dir,
        event_timestamp=datetime(2026, 7, 22, 10, 15),
        strategy_code="S23",
        trade_id="trade-1",
        event_type="LIFECYCLE_STEP",
        status="PAPER_POSITION_HELD",
        reason_code="no_exit_threshold_hit",
        message="position held",
        selected_contract_symbol="NIFTY_20260723_24150_PE",
        provider="fyers",
    )

    rows = [json.loads(line) for line in result_path.read_text(encoding="utf-8").splitlines()]
    assert result_path == state_dir / "paper_lifecycle_supervisor_events.jsonl"
    assert rows == [
        {
            "artifact_version": 1,
            "event_timestamp": "2026-07-22T10:15:00",
            "event_type": "LIFECYCLE_STEP",
            "message": "position held",
            "provider": "fyers",
            "reason_code": "no_exit_threshold_hit",
            "selected_contract_symbol": "NIFTY_20260723_24150_PE",
            "state_directory": str(state_dir),
            "status": "PAPER_POSITION_HELD",
            "strategy_code": "S23",
            "supervisor_pid": module.os.getpid(),
            "trade_id": "trade-1",
        }
    ]


def test_connect_paper_broker_runtime_returns_health() -> None:
    class HealthyAdapter:
        def __init__(self) -> None:
            self.connected = False

        def connect(self) -> None:
            self.connected = True

        def health(self):
            from tfis.brokers import BrokerConnectionState, BrokerHealthEvent

            return BrokerHealthEvent(
                broker_name="fyers",
                as_of=datetime(2026, 7, 19, 9, 15),
                connection_state=BrokerConnectionState.CONNECTED,
                source_id="test:health",
                is_connected=self.connected,
            )

    from tfis.paper import connect_paper_broker_runtime

    health = connect_paper_broker_runtime(
        strategy_code="S23",
        provider="fyers",
        adapter=HealthyAdapter(),
    )

    assert health.connection_state.value == "CONNECTED"
    assert health.is_connected is True


def test_load_paper_runtime_broker_health_statuses_reports_connected_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tfis.paper.runtime_broker_health_status as broker_health_module

    class _Health:
        def __init__(self) -> None:
            self.connection_state = type("State", (), {"value": "CONNECTED"})()
            self.is_connected = True
            self.reconnect_attempts = 0
            self.warnings = ()
            self.diagnostics = ()

    class _Adapter:
        def disconnect(self) -> None:
            return None

    target_spec = type(
        "TargetSpec",
        (),
        {
            "strategy_code": "S23",
            "config_path": tmp_path / "config.yaml",
        },
    )()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            (
                "source_mode: broker_fyers_live_paper_ingress",
                "broker:",
                "  provider: fyers",
                "  timezone: Asia/Kolkata",
                "paper:",
                "  paper_mode_enabled: true",
                "  no_live_orders_allowed: true",
                "  kill_switch_enabled: true",
                "  session_kill_switch_active: false",
            )
        ),
        encoding="utf-8",
    )
    runtime = type(
        "Runtime",
        (),
        {
            "config": PaperLifecycleRuntimeConfig.from_yaml(config_path),
            "adapter": _Adapter(),
        },
    )()

    monkeypatch.setattr(
        broker_health_module,
        "load_paper_lifecycle_supervisor_target_specs",
        lambda _path, repo_root: (target_spec,),
    )
    monkeypatch.setattr(
        broker_health_module,
        "load_paper_broker_runtime",
        lambda _path: runtime,
    )
    monkeypatch.setattr(
        broker_health_module,
        "prepare_paper_broker_runtime_environment",
        lambda config, tfis_root, skip_refresh: None,
    )
    monkeypatch.setattr(
        broker_health_module,
        "connect_paper_broker_runtime",
        lambda **kwargs: _Health(),
    )

    statuses = load_paper_runtime_broker_health_statuses(
        tmp_path / "targets.yaml",
        repo_root=tmp_path,
        tfis_root=tmp_path,
    )

    assert len(statuses) == 1
    status = statuses[0]
    assert status.strategy_code == "S23"
    assert status.status == "PASS"
    assert status.provider == "fyers"
    assert status.connection_state == "CONNECTED"
    assert status.is_connected is True


def test_connect_paper_broker_runtime_reconnects_when_initial_health_is_degraded() -> None:
    from tfis.brokers import BrokerConnectionState, BrokerHealthEvent
    from tfis.paper import connect_paper_broker_runtime

    class DegradedThenHealthyAdapter:
        def __init__(self) -> None:
            self.connected = False
            self.reconnect_calls = 0

        def connect(self) -> None:
            self.connected = True

        def health(self):
            return BrokerHealthEvent(
                broker_name="fyers",
                as_of=datetime(2026, 7, 20, 9, 15),
                connection_state=BrokerConnectionState.DEGRADED,
                source_id="test:health",
                is_connected=False,
                diagnostics=("stream stalled",),
            )

        def reconnect(self):
            self.reconnect_calls += 1
            return BrokerHealthEvent(
                broker_name="fyers",
                as_of=datetime(2026, 7, 20, 9, 16),
                connection_state=BrokerConnectionState.CONNECTED,
                source_id="test:reconnect",
                is_connected=True,
                reconnect_attempts=self.reconnect_calls,
            )

    adapter = DegradedThenHealthyAdapter()

    health = connect_paper_broker_runtime(
        strategy_code="S23",
        provider="fyers",
        adapter=adapter,
    )

    assert health.connection_state.value == "CONNECTED"
    assert health.is_connected is True
    assert adapter.reconnect_calls == 1


def test_ensure_paper_broker_runtime_healthy_reconnects_once_when_degraded() -> None:
    from tfis.brokers import BrokerConnectionState, BrokerHealthEvent

    class DegradedThenHealthyAdapter:
        def __init__(self) -> None:
            self.reconnect_calls = 0

        def health(self):
            return BrokerHealthEvent(
                broker_name="fyers",
                as_of=datetime(2026, 7, 20, 9, 15),
                connection_state=BrokerConnectionState.DEGRADED,
                source_id="test:health",
                is_connected=False,
                diagnostics=("stream stalled",),
            )

        def reconnect(self):
            self.reconnect_calls += 1
            return BrokerHealthEvent(
                broker_name="fyers",
                as_of=datetime(2026, 7, 20, 9, 16),
                connection_state=BrokerConnectionState.CONNECTED,
                source_id="test:reconnect",
                is_connected=True,
                reconnect_attempts=self.reconnect_calls,
            )

    adapter = DegradedThenHealthyAdapter()

    health = ensure_paper_broker_runtime_healthy(
        strategy_code="S23",
        provider="fyers",
        adapter=adapter,
    )

    assert health.connection_state.value == "CONNECTED"
    assert health.is_connected is True
    assert adapter.reconnect_calls == 1


def test_ensure_paper_broker_runtime_healthy_fails_closed_when_reconnect_stays_unhealthy() -> None:
    from tfis.brokers import BrokerConnectionState, BrokerHealthEvent

    class AlwaysUnhealthyAdapter:
        def health(self):
            return BrokerHealthEvent(
                broker_name="fyers",
                as_of=datetime(2026, 7, 20, 9, 15),
                connection_state=BrokerConnectionState.DEGRADED,
                source_id="test:health",
                is_connected=False,
                warnings=("selected_contract_stream_unavailable",),
            )

        def reconnect(self):
            return BrokerHealthEvent(
                broker_name="fyers",
                as_of=datetime(2026, 7, 20, 9, 16),
                connection_state=BrokerConnectionState.ERROR,
                source_id="test:reconnect",
                is_connected=False,
                reconnect_attempts=1,
                diagnostics=("socket unavailable",),
            )

    with pytest.raises(RuntimeError, match="broker runtime is unhealthy for fyers after reconnect"):
        ensure_paper_broker_runtime_healthy(
            strategy_code="S23",
            provider="fyers",
            adapter=AlwaysUnhealthyAdapter(),
        )


def test_runtime_adapter_connection_failures_are_contextualized(
    tmp_path: Path,
) -> None:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_tfis_paper_lifecycle_supervisor.py"
    spec = importlib.util.spec_from_file_location("run_tfis_paper_lifecycle_supervisor", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            (
                "broker:",
                "  provider: fyers",
                "  timezone: Asia/Kolkata",
            )
        ),
        encoding="utf-8",
    )
    config = PaperLifecycleRuntimeConfig.from_yaml(config_path)

    class BrokenAdapter:
        def connect(self):
            raise RuntimeError("socket unavailable")

    runtime = module._TargetRuntime(
        spec=load_paper_lifecycle_supervisor_target_specs(
            _targets_yaml(
                tmp_path,
                config_path=config_path,
                artifact_root=tmp_path / "data" / "strategies" / "S23",
            ),
            repo_root=tmp_path,
        )[0],
        config=config,
        timezone_name="Asia/Kolkata",
        timezone=module.ZoneInfo("Asia/Kolkata"),
        adapter=BrokenAdapter(),
        live_state_store=object(),
        supervisor=object(),
    )

    with pytest.raises(RuntimeError, match="S23 broker connect failed for fyers"):
        module._connect_runtime_adapters((runtime,))


def test_runtime_health_check_logs_degraded_and_recovered_state(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_tfis_paper_lifecycle_supervisor.py"
    spec = importlib.util.spec_from_file_location("run_tfis_paper_lifecycle_supervisor", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            (
                "broker:",
                "  provider: fyers",
                "  timezone: Asia/Kolkata",
            )
        ),
        encoding="utf-8",
    )

    from tfis.brokers import BrokerConnectionState, BrokerHealthEvent

    class DegradedThenHealthyAdapter:
        def __init__(self) -> None:
            self.reconnect_calls = 0

        def health(self):
            return BrokerHealthEvent(
                broker_name="fyers",
                as_of=datetime(2026, 7, 20, 10, 0),
                connection_state=BrokerConnectionState.DEGRADED,
                source_id="test:health",
                is_connected=False,
                warnings=("selected_contract_stream_unavailable",),
            )

        def reconnect(self):
            self.reconnect_calls += 1
            return BrokerHealthEvent(
                broker_name="fyers",
                as_of=datetime(2026, 7, 20, 10, 1),
                connection_state=BrokerConnectionState.CONNECTED,
                source_id="test:reconnect",
                is_connected=True,
                reconnect_attempts=self.reconnect_calls,
            )

    runtime = module._TargetRuntime(
        spec=load_paper_lifecycle_supervisor_target_specs(
            _targets_yaml(
                tmp_path,
                config_path=config_path,
                artifact_root=tmp_path / "data" / "strategies" / "S23",
            ),
            repo_root=tmp_path,
        )[0],
        config=PaperLifecycleRuntimeConfig.from_yaml(config_path),
        timezone_name="Asia/Kolkata",
        timezone=module.ZoneInfo("Asia/Kolkata"),
        adapter=DegradedThenHealthyAdapter(),
        live_state_store=object(),
        supervisor=object(),
    )

    health = module._ensure_runtime_adapter_health(
        runtime=runtime,
        evaluated_at=datetime(2026, 7, 20, 10, 2),
    )

    output = capsys.readouterr().out
    assert "WARNING broker_runtime_degraded" in output
    assert "INFO broker_runtime_recovered" in output
    assert health.connection_state.value == "CONNECTED"


def test_process_target_records_market_data_unavailable_without_state_transition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_tfis_paper_lifecycle_supervisor.py"
    spec = importlib.util.spec_from_file_location("run_tfis_paper_lifecycle_supervisor", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            (
                "broker:",
                "  provider: fyers",
                "  timezone: Asia/Kolkata",
            )
        ),
        encoding="utf-8",
    )
    target_spec = load_paper_lifecycle_supervisor_target_specs(
        _targets_yaml(
            tmp_path,
            config_path=config_path,
            artifact_root=tmp_path / "data" / "strategies" / "S23",
        ),
        repo_root=tmp_path,
    )[0]
    order_dir = target_spec.artifact_root / "2026-07-22" / "session" / "BRANCH"
    order_state, _state_path, _events_path = PaperOrderStateStore().create_waiting_order_from_live_decision(
        order_dir,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(session_date=date(2026, 7, 22)),
        created_at=datetime(2026, 7, 22, 9, 30),
    )

    class FakeLiveStateStore:
        def __init__(self) -> None:
            self.heartbeats: list[dict[str, object]] = []

        def acquire_trade_lock(self, **_kwargs) -> bool:
            return True

        def release_trade_lock(self, **_kwargs) -> None:
            return None

        def set_watch_heartbeat(self, **kwargs) -> None:
            self.heartbeats.append(kwargs)

    class SupervisorMustNotRun:
        def expire_waiting_order_from_previous_session(self, *_args, **_kwargs):
            return None

        def supervise(self, *_args, **_kwargs):
            raise AssertionError("supervisor must not transition state without selected-contract data")

    live_state_store = FakeLiveStateStore()
    runtime = module._TargetRuntime(
        spec=target_spec,
        config=PaperLifecycleRuntimeConfig.from_yaml(config_path),
        timezone_name="Asia/Kolkata",
        timezone=module.ZoneInfo("Asia/Kolkata"),
        adapter=object(),
        live_state_store=live_state_store,
        supervisor=SupervisorMustNotRun(),
    )
    target = type(
        "Target",
        (),
        {
            "directory": order_dir,
            "session_date": date(2026, 7, 22),
            "mode": "order",
            "order_state": order_state,
            "position_state": None,
        },
    )()

    def _raise_fetch_error(**_kwargs):
        raise BrokerAdapterError("quote unavailable")

    monkeypatch.setattr(module, "_fetch_selected_contract_events", _raise_fetch_error)

    module._process_target(
        runtime=runtime,
        target=target,
        held_trade_ids={},
        lock_ttl_seconds=30,
        watch_cutoff_time=time(15, 30),
        dashboard_rebuild_disabled=True,
        evaluated_at=datetime(2026, 7, 22, 10, 0),
        tfis_root=tmp_path,
    )

    output = capsys.readouterr().out
    assert "WARNING market_data_unavailable" in output
    assert "selected_contract_event_fetch_failed" in output
    assert live_state_store.heartbeats[0]["payload"]["status"] == "MARKET_DATA_UNAVAILABLE"
    assert live_state_store.heartbeats[0]["payload"]["reason_code"] == "selected_contract_event_fetch_failed"
    persisted = PaperOrderStateStore().load_state(order_dir)
    assert persisted.status.value == "PAPER_ORDER_WAITING_FOR_TRIGGER"
    audit_rows = [
        json.loads(line)
        for line in (order_dir / "paper_lifecycle_supervisor_events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert audit_rows[-1]["event_type"] == "MARKET_DATA_UNAVAILABLE"
    assert audit_rows[-1]["status"] == "SKIPPED"
    assert audit_rows[-1]["reason_code"] == "selected_contract_event_fetch_failed"
    assert audit_rows[-1]["trade_id"].startswith("S23-S23_NIFTY_OP_SELL_WK_DIFF_2D_3D")


def test_process_target_records_stale_selected_contract_event_without_state_transition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_tfis_paper_lifecycle_supervisor.py"
    spec = importlib.util.spec_from_file_location("run_tfis_paper_lifecycle_supervisor", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            (
                "broker:",
                "  provider: fyers",
                "  timezone: Asia/Kolkata",
            )
        ),
        encoding="utf-8",
    )
    target_spec = load_paper_lifecycle_supervisor_target_specs(
        _targets_yaml(
            tmp_path,
            config_path=config_path,
            artifact_root=tmp_path / "data" / "strategies" / "S23",
        ),
        repo_root=tmp_path,
    )[0]
    order_dir = target_spec.artifact_root / "2026-07-22" / "session" / "BRANCH"
    order_state, _state_path, _events_path = PaperOrderStateStore().create_waiting_order_from_live_decision(
        order_dir,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(session_date=date(2026, 7, 22)),
        created_at=datetime(2026, 7, 22, 9, 30),
    )

    class FakeLiveStateStore:
        def __init__(self) -> None:
            self.heartbeats: list[dict[str, object]] = []

        def acquire_trade_lock(self, **_kwargs) -> bool:
            return True

        def release_trade_lock(self, **_kwargs) -> None:
            return None

        def set_watch_heartbeat(self, **kwargs) -> None:
            self.heartbeats.append(kwargs)

    class SupervisorMustNotRun:
        def expire_waiting_order_from_previous_session(self, *_args, **_kwargs):
            return None

        def supervise(self, *_args, **_kwargs):
            raise AssertionError("supervisor must not transition state with stale selected-contract data")

    live_state_store = FakeLiveStateStore()
    runtime = module._TargetRuntime(
        spec=target_spec,
        config=PaperLifecycleRuntimeConfig.from_yaml(config_path),
        timezone_name="Asia/Kolkata",
        timezone=module.ZoneInfo("Asia/Kolkata"),
        adapter=object(),
        live_state_store=live_state_store,
        supervisor=SupervisorMustNotRun(),
    )
    target = type(
        "Target",
        (),
        {
            "directory": order_dir,
            "session_date": date(2026, 7, 22),
            "mode": "order",
            "order_state": order_state,
            "position_state": None,
        },
    )()
    stale_event = SelectedContractQuoteEvent(
        envelope=EventEnvelope(
            event_type=PaperEventType.SELECTED_CONTRACT_QUOTE,
            session_date=date(2026, 7, 22),
            effective_timestamp=datetime(2026, 7, 22, 9, 55),
            captured_at=datetime(2026, 7, 22, 9, 55),
            timezone="Asia/Kolkata",
            source_type="broker",
            source_id="stale-selected-contract-quote",
            synthetic_fixture=True,
            normalized_by="test",
        ),
        symbol=order_state.selected_contract_symbol,
        option_type=OptionType.PUT,
        strike=24150.0,
        expiry=date(2026, 7, 23),
        bid=199.0,
        ask=201.0,
        ltp=200.0,
        oi=100000.0,
    )

    monkeypatch.setattr(module, "_fetch_selected_contract_events", lambda **_kwargs: (stale_event,))

    module._process_target(
        runtime=runtime,
        target=target,
        held_trade_ids={},
        lock_ttl_seconds=30,
        watch_cutoff_time=time(15, 30),
        dashboard_rebuild_disabled=True,
        evaluated_at=datetime(2026, 7, 22, 10, 0),
        tfis_root=tmp_path,
        max_selected_contract_event_age_seconds=120.0,
    )

    output = capsys.readouterr().out
    assert "WARNING market_data_unavailable" in output
    assert "selected_contract_event_stale" in output
    assert live_state_store.heartbeats[0]["payload"]["status"] == "MARKET_DATA_UNAVAILABLE"
    assert live_state_store.heartbeats[0]["payload"]["reason_code"] == "selected_contract_event_stale"
    persisted = PaperOrderStateStore().load_state(order_dir)
    assert persisted.status.value == "PAPER_ORDER_WAITING_FOR_TRIGGER"
    assert not (order_dir / "selected_contract_market_events.jsonl").exists()
    audit_rows = [
        json.loads(line)
        for line in (order_dir / "paper_lifecycle_supervisor_events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert audit_rows[-1]["event_type"] == "MARKET_DATA_UNAVAILABLE"
    assert audit_rows[-1]["status"] == "SKIPPED"
    assert audit_rows[-1]["reason_code"] == "selected_contract_event_stale"


def test_connect_paper_broker_runtime_contextualizes_health_failures() -> None:
    class AdapterWithBrokenHealth:
        def connect(self) -> None:
            return None

        def health(self):
            raise RuntimeError("health unavailable")

    from tfis.paper import connect_paper_broker_runtime

    with pytest.raises(RuntimeError, match="S23 broker health check failed for fyers"):
        connect_paper_broker_runtime(
            strategy_code="S23",
            provider="fyers",
            adapter=AdapterWithBrokenHealth(),
        )


def test_supervisor_runtime_bootstrap_fails_closed_for_guardrail_config(
    tmp_path: Path,
) -> None:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_tfis_paper_lifecycle_supervisor.py"
    spec = importlib.util.spec_from_file_location("run_tfis_paper_lifecycle_supervisor", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            (
                "source_mode: broker_fyers_live_fill_mode",
                "broker:",
                "  provider: fyers",
                "  timezone: Asia/Kolkata",
                "paper:",
                "  paper_mode_enabled: true",
                "  no_live_orders_allowed: false",
                "  kill_switch_enabled: true",
                "  session_kill_switch_active: false",
            )
        ),
        encoding="utf-8",
    )

    target_spec = load_paper_lifecycle_supervisor_target_specs(
        _targets_yaml(
            tmp_path,
            config_path=config_path,
            artifact_root=tmp_path / "data" / "strategies" / "S23" / "fyers_morning_supervised_decision",
        ),
        repo_root=tmp_path,
    )[0]

    with pytest.raises(RuntimeError, match="runtime guardrail check failed"):
        module._build_runtimes((target_spec,))


def test_build_fresh_decision_task_spec_from_target_metadata(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_tfis_paper_lifecycle_supervisor.py"
    spec = importlib.util.spec_from_file_location("run_tfis_paper_lifecycle_supervisor", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    config_path = tmp_path / "config" / "paper.s23.fyers_connect_test.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("broker:\n  provider: fyers\n  timezone: Asia/Kolkata\n", encoding="utf-8")
    target_spec = load_paper_lifecycle_supervisor_target_specs(
        _targets_yaml(
            tmp_path,
            config_path=config_path,
            artifact_root=tmp_path / "data" / "strategies" / "S23" / "fyers_morning_supervised_decision",
        ),
        repo_root=tmp_path,
    )[0]

    task_spec = module._build_fresh_decision_task_spec(
        spec=target_spec,
        tfis_root=tmp_path,
        carry_forward_state_dir=None,
    )

    assert task_spec is not None
    assert task_spec.strategy_path == target_spec.strategy_path
    assert task_spec.reference_packet_path == target_spec.reference_packet_path
    assert task_spec.session_id_prefix == "s23-fyers-morning-supervised-decision"
    assert task_spec.runner_script_path.name == "run_s23_fyers_0916_supervised_decision.py"
    assert task_spec.wrapper_script_path.name == "start_s23_fyers_morning_supervised_decision.ps1"


def test_launch_fresh_decision_if_required_spawns_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_tfis_paper_lifecycle_supervisor.py"
    spec = importlib.util.spec_from_file_location("run_tfis_paper_lifecycle_supervisor", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    config_path = tmp_path / "config" / "paper.s23.fyers_connect_test.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("broker:\n  provider: fyers\n  timezone: Asia/Kolkata\n", encoding="utf-8")
    target_spec = load_paper_lifecycle_supervisor_target_specs(
        _targets_yaml(
            tmp_path,
            config_path=config_path,
            artifact_root=tmp_path / "data" / "strategies" / "S23" / "fyers_morning_supervised_decision",
        ),
        repo_root=tmp_path,
    )[0]
    runtime = module._TargetRuntime(
        spec=target_spec,
        config=PaperLifecycleRuntimeConfig.from_yaml(config_path),
        timezone_name="Asia/Kolkata",
        timezone=module.ZoneInfo("Asia/Kolkata"),
        adapter=object(),
        live_state_store=object(),
        supervisor=object(),
    )
    context = module.PaperLifecycleSupervisorContext(
        session_directory=tmp_path / "data" / "strategies" / "S23" / "session",
        session_date=date(2026, 7, 18),
        trade_id="trade-1",
        selected_contract_symbol="NIFTY_20260721_24200_CE",
        order_state=None,
        position_state=None,
    )

    launched: list[tuple[tuple[str, ...], str]] = []

    class _FakeResult:
        final_step = type("Step", (), {"status": "PAPER_POSITION_FRESH_ENTRY_REQUIRED"})()

    def _fake_popen(args, cwd):
        launched.append((tuple(args), cwd))
        class _Proc:
            pid = 1234
        return _Proc()

    monkeypatch.setattr(module.subprocess, "Popen", _fake_popen)

    module._launch_fresh_decision_if_required(
        runtime=runtime,
        context=context,
        lifecycle_result=_FakeResult(),
        tfis_root=tmp_path,
        evaluated_at=datetime(2026, 7, 18, 10, 5),
    )

    assert len(launched) == 1
    assert launched[0][0][1].endswith("run_s23_fyers_0916_supervised_decision.py")
    marker_path = context.session_directory / "fresh_decision_launch.json"
    assert marker_path.exists()
    marker_payload = json.loads(marker_path.read_text(encoding="utf-8"))
    assert marker_payload["strategy_code"] == "S23"
    assert marker_payload["trade_id"] == "trade-1"
    assert marker_payload["pid"] == 1234


def test_launch_fresh_decision_if_required_skips_non_fresh_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_tfis_paper_lifecycle_supervisor.py"
    spec = importlib.util.spec_from_file_location("run_tfis_paper_lifecycle_supervisor", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    launched: list[tuple[tuple[str, ...], str]] = []

    def _fake_popen(args, cwd):
        launched.append((tuple(args), cwd))
        class _Proc:
            pid = 1234
        return _Proc()

    monkeypatch.setattr(module.subprocess, "Popen", _fake_popen)

    module._launch_fresh_decision_if_required(
        runtime=type("Runtime", (), {"spec": type("Spec", (), {"strategy_code": "S23"})()})(),
        context=type("Context", (), {"session_directory": tmp_path})(),
        lifecycle_result=type("Result", (), {"final_step": type("Step", (), {"status": "PAPER_POSITION_STOPLOSS_HIT"})()})(),
        tfis_root=tmp_path,
        evaluated_at=datetime(2026, 7, 18, 10, 5),
    )

    assert launched == []


def test_launch_fresh_decision_if_required_is_idempotent_per_session_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_tfis_paper_lifecycle_supervisor.py"
    spec = importlib.util.spec_from_file_location("run_tfis_paper_lifecycle_supervisor", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    config_path = tmp_path / "config" / "paper.s23.fyers_connect_test.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("broker:\n  provider: fyers\n  timezone: Asia/Kolkata\n", encoding="utf-8")
    target_spec = load_paper_lifecycle_supervisor_target_specs(
        _targets_yaml(
            tmp_path,
            config_path=config_path,
            artifact_root=tmp_path / "data" / "strategies" / "S23" / "fyers_morning_supervised_decision",
        ),
        repo_root=tmp_path,
    )[0]
    runtime = module._TargetRuntime(
        spec=target_spec,
        config=PaperLifecycleRuntimeConfig.from_yaml(config_path),
        timezone_name="Asia/Kolkata",
        timezone=module.ZoneInfo("Asia/Kolkata"),
        adapter=object(),
        live_state_store=object(),
        supervisor=object(),
    )
    context = module.PaperLifecycleSupervisorContext(
        session_directory=tmp_path / "data" / "strategies" / "S23" / "session",
        session_date=date(2026, 7, 18),
        trade_id="trade-1",
        selected_contract_symbol="NIFTY_20260721_24200_CE",
        order_state=None,
        position_state=None,
    )

    launched: list[tuple[tuple[str, ...], str]] = []

    class _FakeResult:
        final_step = type("Step", (), {"status": "PAPER_POSITION_FRESH_ENTRY_REQUIRED"})()

    def _fake_popen(args, cwd):
        launched.append((tuple(args), cwd))
        class _Proc:
            pid = 1234
        return _Proc()

    monkeypatch.setattr(module.subprocess, "Popen", _fake_popen)

    module._launch_fresh_decision_if_required(
        runtime=runtime,
        context=context,
        lifecycle_result=_FakeResult(),
        tfis_root=tmp_path,
        evaluated_at=datetime(2026, 7, 18, 10, 5),
    )
    module._launch_fresh_decision_if_required(
        runtime=runtime,
        context=context,
        lifecycle_result=_FakeResult(),
        tfis_root=tmp_path,
        evaluated_at=datetime(2026, 7, 18, 10, 6),
    )

    assert len(launched) == 1


def test_launch_fresh_decision_if_required_promotes_existing_blocked_decision_before_spawning_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_tfis_paper_lifecycle_supervisor.py"
    spec = importlib.util.spec_from_file_location("run_tfis_paper_lifecycle_supervisor", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    config_path = tmp_path / "config" / "paper.s23.fyers_connect_test.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("broker:\n  provider: fyers\n  timezone: Asia/Kolkata\n", encoding="utf-8")
    artifact_root = tmp_path / "data" / "strategies" / "S23" / "fyers_morning_supervised_decision"
    target_spec = load_paper_lifecycle_supervisor_target_specs(
        _targets_yaml(
            tmp_path,
            config_path=config_path,
            artifact_root=artifact_root,
        ),
        repo_root=tmp_path,
    )[0]
    runtime = module._TargetRuntime(
        spec=target_spec,
        config=PaperLifecycleRuntimeConfig.from_yaml(config_path),
        timezone_name="Asia/Kolkata",
        timezone=module.ZoneInfo("Asia/Kolkata"),
        adapter=object(),
        live_state_store=object(),
        supervisor=object(),
    )
    blocked_session = (
        artifact_root
        / "2026-07-18"
        / "s23-fyers-morning-supervised-decision-2026-07-18"
        / "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL"
    )
    blocked_session.mkdir(parents=True, exist_ok=True)
    (blocked_session.parent / "scheduled_run_metadata.json").write_text("{}", encoding="utf-8")
    (blocked_session / "trade_decision_summary.json").write_text(
        json.dumps({"summary": _blocked_ready_summary_payload()}),
        encoding="utf-8",
    )
    context = module.PaperLifecycleSupervisorContext(
        session_directory=tmp_path / "data" / "strategies" / "S23" / "closed-session",
        session_date=date(2026, 7, 18),
        trade_id="trade-1",
        selected_contract_symbol="NIFTY_20260721_24200_CE",
        order_state=None,
        position_state=None,
    )

    launched: list[tuple[tuple[str, ...], str]] = []

    class _FakeResult:
        final_step = type("Step", (), {"status": "PAPER_POSITION_FRESH_ENTRY_REQUIRED"})()

    def _fake_popen(args, cwd):
        launched.append((tuple(args), cwd))
        class _Proc:
            pid = 1234
        return _Proc()

    monkeypatch.setattr(module.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(
        module,
        "promote_blocked_fresh_entries",
        lambda artifact_root, *, session_date, created_at, session_id_prefix: shared_promote_blocked_fresh_entries(
            artifact_root,
            session_date=session_date,
            created_at=created_at,
            session_id_prefix=session_id_prefix,
            strategy_loader=lambda _branch: _strategy_rule(),
        ),
    )

    module._launch_fresh_decision_if_required(
        runtime=runtime,
        context=context,
        lifecycle_result=_FakeResult(),
        tfis_root=tmp_path,
        evaluated_at=datetime(2026, 7, 18, 10, 5),
    )

    assert launched == []
    promoted_order_state = PaperOrderStateStore().load_state(blocked_session)
    assert promoted_order_state.status.value == "PAPER_ORDER_WAITING_FOR_TRIGGER"
    marker_payload = json.loads(
        (context.session_directory / "fresh_decision_launch.json").read_text(encoding="utf-8")
    )
    assert marker_payload["mode"] == "promoted_existing_blocked_decision"


def _targets_yaml(tmp_path: Path, *, config_path: Path, artifact_root: Path) -> Path:
    target_path = tmp_path / "targets.yaml"
    target_path.write_text(
        "\n".join(
            (
                "targets:",
                "  - strategy_code: S23",
                f"    config_path: {config_path.relative_to(tmp_path).as_posix()}",
                f"    artifact_root: {artifact_root.relative_to(tmp_path).as_posix()}",
                "    process_lock_root: tmp/process_locks/s23_paper_watch",
                "    strategy_path: config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
                "    reference_packet_path: config/reference_packets/s23_bear_put_live_decision_reference.json",
                "    session_id_prefix: s23-fyers-morning-supervised-decision",
                "    executor: paper_morning_supervised",
                "    runner_script_path: scripts/run_s23_fyers_0916_supervised_decision.py",
                "    wrapper_script_path: scripts/start_s23_fyers_morning_supervised_decision.ps1",
            )
        ),
        encoding="utf-8",
    )
    return target_path


def _strategy_rule() -> StrategyRule:
    return StrategyRule(
        strategy_code="S23",
        unique_code="S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
        symbol="NIFTY",
        segment=Segment.OPTIONS_SELL,
        expiry_policy=StrategyExpiryPolicy(
            expiry_type=ExpiryType.WEEKLY,
            rollover_policy=RolloverPolicy.T_MINUS_1,
            forced_close_time=time(12, 0),
            no_carry_past_expiry=True,
        ),
        allowed_monthly_statuses=(MonthlyStatus.BEAR,),
        option_type=OptionType.PUT,
        entry_time=time(9, 24, 59),
        recalculation_time=time(9, 29, 59),
        start_strike_formula="1",
        end_strike_formula="1",
        ideal_premium_formula="1",
        minimum_premium_formula="1",
        minimum_oi=500,
        entry_formula="1",
        target_formula="1",
        stoploss_formula="1",
        carry_forward_allowed=True,
        parameters={"sl_reference_pct": 7.0},
    )


def _ready_summary(*, session_date: date) -> S23PaperTradeDecisionSummary:
    return S23PaperTradeDecisionSummary(
        status="READY",
        session_date=session_date,
        mode="fresh_entry",
        strategy_code="S23",
        strategy_branch="S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
        monthly_status="BEAR",
        monthly_status_trigger="BEAR_CONTINUES",
        monthly_status_notes="test",
        required_market_aliases=(),
        required_option_aliases=(),
        checkpoint_labels=("0915", "ORPT", "RC"),
        market_levels={},
        runtime_values={},
        lots=1,
        quantity=65,
        selected_contract_symbol="NIFTY_20260723_24150_PE",
        selected_contract_expiry="2026-07-23",
        selected_contract_strike=24150.0,
        selected_contract_option_type="PUT",
        selected_contract_ltp=194.25,
        selected_contract_oi=1000000.0,
        contract_selection_reason="test",
        contract_selection_failure_code=None,
        contract_selection_attempted_expiries=("2026-07-23",),
        rejected_candidate_counts={},
        ranked_candidates=(),
        planned_entry_price=194.25,
        target_price=77.70,
        stoploss_price=242.0,
        fsl_price=258.94,
        source_workbook_rule="test",
        workbook_row_number=1,
        notes=(),
    )


def _blocked_ready_summary_payload() -> dict[str, object]:
    return {
        "status": "READY",
        "session_date": "2026-07-18",
        "mode": "fresh_entry",
        "strategy_code": "S23",
        "strategy_branch": "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
        "monthly_status": "BEAR",
        "monthly_status_trigger": "BEAR_CONTINUES",
        "monthly_status_notes": "test",
        "required_market_aliases": [],
        "required_option_aliases": [],
        "checkpoint_labels": ["0915", "ORPT", "RC"],
        "market_levels": {},
        "runtime_values": {},
        "lots": 1,
        "quantity": 65,
        "selected_contract_symbol": "NIFTY_20260714_24150_CE",
        "selected_contract_expiry": "2026-07-14",
        "selected_contract_strike": 24150,
        "selected_contract_option_type": "CALL",
        "selected_contract_ltp": 292.35,
        "selected_contract_oi": 139945,
        "contract_selection_reason": "Selected first strike meeting ideal premium.",
        "contract_selection_failure_code": None,
        "contract_selection_attempted_expiries": ["2026-07-14"],
        "rejected_candidate_counts": {},
        "ranked_candidates": [],
        "planned_entry_price": 194.25,
        "target_price": 77.70,
        "stoploss_price": 242.00,
        "fsl_price": None,
        "source_workbook_rule": "unit-test",
        "workbook_row_number": 1,
        "governance_event_types": [],
        "resume_event_type": None,
        "notes": [],
        "order_placement_blocked": True,
        "order_placement_block_reason": "OPEN_CARRY_FORWARD_POSITION",
    }
