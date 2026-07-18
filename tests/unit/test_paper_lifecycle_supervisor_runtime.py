from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, datetime, time
from pathlib import Path

import pytest

from tfis.brokers import FyersBrokerAdapter
from tfis.domain import ExpiryType, MonthlyStatus, OptionType, RolloverPolicy, Segment, StrategyExpiryPolicy, StrategyRule
from tfis.paper import (
    build_paper_expiry_governance,
    build_paper_position_manager,
    PaperLifecycleBrokerRuntime,
    PaperLifecycleRuntimeConfig,
    PaperLifecycleSupervisor,
    PaperLifecycleSupervisorTargetDiscovery,
    PaperOrderStateStore,
    S23PaperPositionManager,
    S23PaperTradeLedgerStore,
    S23PaperTradeDecisionSummary,
    build_paper_broker_adapter,
    load_paper_broker_runtime,
    load_paper_lifecycle_supervisor_target_specs,
    prepare_paper_broker_runtime_environment,
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
    assert specs[0].executor == "s23_morning_supervised"


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
        ("order", "stale-branch"),
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
    assert by_code["S23"].executor == "s23_morning_supervised"
    assert by_code["S21"].strategy_path is not None
    assert by_code["S21"].reference_packet_path is not None
    assert by_code["S21"].session_id_prefix == "s21-fyers-morning-supervised-decision"
    assert by_code["S21"].executor == "s23_morning_supervised"


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
    assert config.costs.slippage_exit_points == 1.5


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
                "    executor: s23_morning_supervised",
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
