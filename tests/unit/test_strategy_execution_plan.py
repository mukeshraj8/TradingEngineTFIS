from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tfis.importers import load_strategy_registry
from tfis.strategy import (
    assert_no_blocked_enabled_strategies,
    build_strategy_execution_plan,
)


ROOT = Path(__file__).resolve().parents[2]


def test_execution_plan_marks_enabled_supported_strategy_runnable() -> None:
    plan = build_strategy_execution_plan(
        {
            "strategies": [
                {
                    "strategy_code": "S23",
                    "enabled": True,
                    "executor": "s23_morning_supervised",
                    "registry_ids": ["S23_NIFTY_OP_SELL_WK_DIFF_2D_3D"],
                }
            ]
        },
        registry=load_strategy_registry(),
        supported_executors=("s23_morning_supervised",),
    )

    assert len(plan.items) == 1
    assert plan.items[0].status == "RUNNABLE"
    assert plan.runnable_items == plan.items
    assert plan.blocked_items == ()
    assert_no_blocked_enabled_strategies(plan)


def test_execution_plan_skips_disabled_strategy_without_blocking() -> None:
    plan = build_strategy_execution_plan(
        {
            "strategies": [
                {
                    "strategy_code": "S23",
                    "enabled": False,
                    "executor": "s23_morning_supervised",
                    "registry_ids": ["S23_NIFTY_OP_SELL_WK_DIFF_2D_3D"],
                }
            ]
        },
        registry=load_strategy_registry(),
        supported_executors=("s23_morning_supervised",),
    )

    assert plan.items[0].status == "SKIPPED_DISABLED"
    assert plan.runnable_items == ()
    assert plan.blocked_items == ()
    assert_no_blocked_enabled_strategies(plan)


def test_execution_plan_fails_closed_for_unsupported_enabled_executor() -> None:
    plan = build_strategy_execution_plan(
        {
            "strategies": [
                {
                    "strategy_code": "S21",
                    "enabled": True,
                    "executor": "s21_not_implemented",
                    "registry_ids": [],
                }
            ]
        },
        registry=load_strategy_registry(),
        supported_executors=("s23_morning_supervised",),
    )

    assert plan.items[0].status == "BLOCKED_UNSUPPORTED_EXECUTOR"
    with pytest.raises(ValueError, match="BLOCKED_UNSUPPORTED_EXECUTOR"):
        assert_no_blocked_enabled_strategies(plan)


def test_execution_plan_blocks_disallowed_registry_status() -> None:
    plan = build_strategy_execution_plan(
        {
            "strategies": [
                {
                    "strategy_code": "MONTHLY_OPTION_BUYING",
                    "enabled": True,
                    "executor": "monthly_option_buying",
                    "registry_ids": ["MONTHLY_OPTION_BUYING"],
                }
            ]
        },
        registry=load_strategy_registry(),
        supported_executors=("monthly_option_buying",),
    )

    assert plan.items[0].status == "BLOCKED_REGISTRY_STATUS"
    assert "UNKNOWN_REQUIRES_REVIEW" in plan.items[0].reason


def test_execution_plan_supports_current_single_strategy_fallback() -> None:
    plan = build_strategy_execution_plan(
        {"paper": {"strategy_code": "S23", "paper_mode_enabled": True}},
        registry=load_strategy_registry(),
        supported_executors=("s23",),
    )

    assert plan.items[0].strategy_code == "S23"
    assert plan.items[0].executor == "s23"
    assert plan.items[0].status == "RUNNABLE"


def test_paper_s23_configs_have_runnable_generic_strategy_plan() -> None:
    registry = load_strategy_registry()
    for config_name in ("paper.s23.yaml", "paper.s23.fyers_connect_test.yaml"):
        config = yaml.safe_load((ROOT / "config" / config_name).read_text(encoding="utf-8"))
        plan = build_strategy_execution_plan(
            config,
            registry=registry,
            supported_executors=("s23_morning_supervised",),
        )

        assert len(plan.items) == 1
        assert plan.items[0].strategy_code == "S23"
        assert plan.items[0].status == "RUNNABLE"
        assert len(plan.items[0].registry_ids) == 4
        assert len(plan.items[0].strategy_paths) == 4
        assert_no_blocked_enabled_strategies(plan)


def test_paper_s21_config_has_runnable_generic_strategy_plan() -> None:
    registry = load_strategy_registry()
    config = yaml.safe_load(
        (ROOT / "config" / "paper.s21.fyers_connect_test.yaml").read_text(encoding="utf-8")
    )
    plan = build_strategy_execution_plan(
        config,
        registry=registry,
        supported_executors=("s23_morning_supervised",),
    )

    assert len(plan.items) == 1
    assert plan.items[0].strategy_code == "S21"
    assert plan.items[0].executor == "s23_morning_supervised"
    assert plan.items[0].status == "RUNNABLE"
    assert len(plan.items[0].registry_ids) == 4
    assert len(plan.items[0].strategy_paths) == 4
    assert_no_blocked_enabled_strategies(plan)
