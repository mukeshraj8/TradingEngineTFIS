from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tfis.adapters.legacy_policies import build_s23_synthetic_golden_packet, runtime_input_from_packet
from tfis.decision import TFISDecisionEngine
from tfis.domain import (
    PositionCycleIdentity,
    StrategyConfigurationError,
    StrategyEvaluationIdentity,
    TFISTradeResult,
    load_strategy_configuration_resolver,
)
from tfis.adapters.legacy_policies.composition import LegacyPolicyRegistryFactory
from tfis.adapters.legacy_policies import policy_selection_for_strategy
from tfis.importers import load_strategy_rule


ROOT = Path(__file__).resolve().parents[2]


def test_family_definition_version_and_instance_identities_are_distinct() -> None:
    resolver = load_strategy_configuration_resolver(ROOT)
    resolved = resolver.resolve("S23_NIFTY_ACCOUNT_A_PAPER")

    assert resolved.family.family_id == "OPTION_SELLING"
    assert resolved.definition.strategy_definition_id == "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D"
    assert resolved.version.strategy_version == "1.0.0"
    assert resolved.instance.strategy_instance_id == "S23_NIFTY_ACCOUNT_A_PAPER"


def test_explicit_strategy_version_is_mandatory_for_instance(tmp_path: Path) -> None:
    _copy_phase3a_configs(tmp_path)
    instance = tmp_path / "config" / "strategy_instances" / "S23_NIFTY_ACCOUNT_A_PAPER.yaml"
    text = instance.read_text(encoding="utf-8").replace("strategy_version: 1.0.0", "")
    instance.write_text(text, encoding="utf-8")

    with pytest.raises(StrategyConfigurationError) as exc:
        load_strategy_configuration_resolver(tmp_path)

    assert "MISSING_MANDATORY_VALUE" in {error.code for error in exc.value.errors}


def test_resolution_hash_is_deterministic_and_cached() -> None:
    resolver = load_strategy_configuration_resolver(ROOT)

    first = resolver.resolve("S23_NIFTY_ACCOUNT_A_PAPER")
    second = resolver.resolve("S23_NIFTY_ACCOUNT_A_PAPER")

    assert first is second
    assert first.effective_configuration_hash == second.effective_configuration_hash
    assert len(first.effective_configuration_hash) == 64


def test_family_defaults_version_values_and_allowed_instance_overrides_resolve() -> None:
    resolver = load_strategy_configuration_resolver(ROOT)
    resolved = resolver.resolve("S23_NIFTY_ACCOUNT_A_PAPER")

    assert resolved.resolved_parameters["version_marker"] == 1
    assert resolved.resolved_parameters["lots"] == 1
    assert resolved.provenance["parameters.version_marker"] == "version"
    assert resolved.provenance["parameters.lots"] == "instance"


def test_forbidden_instance_override_fails_closed(tmp_path: Path) -> None:
    _copy_phase3a_configs(tmp_path)
    instance = tmp_path / "config" / "strategy_instances" / "S23_NIFTY_ACCOUNT_A_PAPER.yaml"
    instance.write_text(
        instance.read_text(encoding="utf-8").replace(
            "  lots: 1\n",
            "  lots: 1\n  entry_formula: SHOULD_NOT_OVERRIDE\n",
        ),
        encoding="utf-8",
    )

    resolver = load_strategy_configuration_resolver(tmp_path)
    with pytest.raises(StrategyConfigurationError) as exc:
        resolver.resolve("S23_NIFTY_ACCOUNT_A_PAPER")

    assert "FORBIDDEN_INSTANCE_OVERRIDE" in {error.code for error in exc.value.errors}


def test_unknown_configuration_key_fails_validation(tmp_path: Path) -> None:
    _copy_phase3a_configs(tmp_path)
    family = tmp_path / "config" / "strategy_families" / "option_selling.yaml"
    family.write_text(family.read_text(encoding="utf-8") + "unexpected_key: true\n", encoding="utf-8")

    with pytest.raises(StrategyConfigurationError) as exc:
        load_strategy_configuration_resolver(tmp_path)

    assert "UNKNOWN_CONFIGURATION_KEY" in {error.code for error in exc.value.errors}


def test_s21_and_s23_resolve_distinct_compositions_by_definition_and_version() -> None:
    resolver = load_strategy_configuration_resolver(ROOT)
    s21 = resolver.resolve("S21_BANKNIFTY_ACCOUNT_A_PAPER")
    s23 = resolver.resolve("S23_NIFTY_ACCOUNT_A_PAPER")

    assert s21.resolved_policy_keys.entry_policy == "legacy.s21.option_selling.entry"
    assert s23.resolved_policy_keys.entry_policy == "legacy.s23.option_selling.entry"
    assert s21.instance.account_ref == s23.instance.account_ref
    assert s21.instance.strategy_instance_id != s23.instance.strategy_instance_id
    assert s21.effective_configuration_hash != s23.effective_configuration_hash


def test_evaluation_identity_is_deterministic_without_filesystem_or_process_dependency() -> None:
    timestamp = datetime(2026, 7, 29, 9, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
    first = StrategyEvaluationIdentity.deterministic(
        strategy_instance_id="S23_NIFTY_ACCOUNT_A_PAPER",
        strategy_definition_id="S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
        strategy_version="1.0.0",
        trading_date=date(2026, 7, 29),
        evaluation_timestamp=timestamp,
        evaluation_sequence=1,
        trigger_type="OFFLINE_TEST",
        configuration_hash="abc",
    )
    second = StrategyEvaluationIdentity.deterministic(
        strategy_instance_id="S23_NIFTY_ACCOUNT_A_PAPER",
        strategy_definition_id="S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
        strategy_version="1.0.0",
        trading_date=date(2026, 7, 29),
        evaluation_timestamp=timestamp,
        evaluation_sequence=1,
        trigger_type="OFFLINE_TEST",
        configuration_hash="abc",
    )

    assert first == second
    assert first.evaluation_id.startswith("eval-")


def test_position_cycle_identity_is_isolated_by_strategy_instance() -> None:
    common = {
        "trading_date": date(2026, 7, 29),
        "cycle_sequence": 1,
        "entry_evaluation_id": "eval-same",
        "product_instrument_identity": "NSE:NIFTY:OPT",
    }
    first = PositionCycleIdentity.deterministic(strategy_instance_id="INSTANCE_A", **common)
    second = PositionCycleIdentity.deterministic(strategy_instance_id="INSTANCE_B", **common)

    assert first.position_cycle_id != second.position_cycle_id
    assert first.state_isolation_key[0] == "INSTANCE_A"
    assert first.state_isolation_key != second.state_isolation_key


def test_generic_decision_retains_authoritative_strategy_identity() -> None:
    packet = build_s23_synthetic_golden_packet()
    runtime_input = runtime_input_from_packet(packet)
    rule = load_strategy_rule(
        ROOT / "config" / "strategies" / "options_sell" / "nifty" / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
    )
    registry = LegacyPolicyRegistryFactory().build(rule)
    composition = policy_selection_for_strategy(rule.strategy_code)

    decision = TFISDecisionEngine(registry.compose(composition.policy_selection)).evaluate(runtime_input)

    assert decision.trade_result is TFISTradeResult.TRADE
    assert decision.strategy_family_id == "OPTION_SELLING"
    assert decision.strategy_definition_id == packet.identity.strategy_unique_code
    assert decision.strategy_instance_id == packet.identity.strategy_instance_id
    assert decision.resolved_configuration_hash == packet.identity.configuration_hash


def test_strategy_identity_is_included_in_packet_runtime_input() -> None:
    packet = build_s23_synthetic_golden_packet()
    runtime_input = runtime_input_from_packet(packet)

    assert runtime_input.strategy_family_id == "OPTION_SELLING"
    assert runtime_input.strategy_definition_id == packet.identity.strategy_unique_code
    assert runtime_input.strategy_instance_id == packet.identity.strategy_instance_id
    assert runtime_input.resolved_configuration_hash == packet.identity.configuration_hash


def _copy_phase3a_configs(tmp_path: Path) -> None:
    for relative in (
        "config/strategy_families/option_selling.yaml",
        "config/strategy_families/futures.yaml",
        "config/strategy_families/option_buying.yaml",
        "config/strategy_families/equity.yaml",
        "config/strategy_definitions/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D/strategy.yaml",
        "config/strategy_definitions/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D/versions/1.0.0.yaml",
        "config/strategy_definitions/S21_BANKNIFTY_OP_SELL_MONTHLY/strategy.yaml",
        "config/strategy_definitions/S21_BANKNIFTY_OP_SELL_MONTHLY/versions/1.0.0.yaml",
        "config/strategy_instances/S23_NIFTY_ACCOUNT_A_PAPER.yaml",
        "config/strategy_instances/S21_BANKNIFTY_ACCOUNT_A_PAPER.yaml",
        "config/strategy_policy_composition.yaml",
    ):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
