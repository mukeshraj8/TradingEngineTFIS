from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path

from tfis.domain import ExpiryType, MonthlyStatus, OptionType, RolloverPolicy, Segment, StrategyExpiryPolicy, StrategyRule
from tfis.paper import (
    PaperLifecycleSupervisorTargetDiscovery,
    PaperOrderStateStore,
    S23PaperPositionManager,
    S23PaperTradeDecisionSummary,
    load_paper_lifecycle_supervisor_target_specs,
)


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
            )
        ),
        encoding="utf-8",
    )

    specs = load_paper_lifecycle_supervisor_target_specs(config_path, repo_root=tmp_path)

    assert len(specs) == 1
    assert specs[0].strategy_code == "S23"
    assert specs[0].config_path == (tmp_path / "config/paper.s23.fyers_connect_test.yaml").resolve()


def test_target_discovery_finds_active_positions_and_waiting_orders(tmp_path: Path) -> None:
    artifact_root = tmp_path / "data" / "strategies" / "S23" / "fyers_morning_supervised_decision"
    open_dir = artifact_root / "2026-07-16" / "open-branch"
    wait_dir = artifact_root / "2026-07-17" / "wait-branch"
    stale_dir = artifact_root / "2026-07-15" / "stale-branch"
    open_dir.mkdir(parents=True, exist_ok=True)
    wait_dir.mkdir(parents=True, exist_ok=True)
    stale_dir.mkdir(parents=True, exist_ok=True)

    manager = S23PaperPositionManager()
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
