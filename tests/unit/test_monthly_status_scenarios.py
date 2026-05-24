from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tfis.monthly_status import MonthlyStatusDecisionTable, MonthlyStatusReferenceLevels


ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_PATH = (
    ROOT / "tests" / "fixtures" / "monthly_status" / "monthly_status_scenarios.yaml"
)


def _load_scenarios() -> list[dict]:
    with SCENARIOS_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return list(data.get("scenarios") or [])


def test_monthly_status_scenarios_yaml_loads() -> None:
    scenarios = _load_scenarios()

    assert scenarios
    assert {scenario["name"] for scenario in scenarios} >= {
        "nifty_clear_bull_candidate",
        "nifty_clear_bear_candidate",
        "stock_threshold_example",
        "unresolved_cf_example",
    }


@pytest.mark.parametrize("scenario", _load_scenarios(), ids=lambda item: item["name"])
def test_monthly_status_scenarios_match_expected_candidates(scenario: dict) -> None:
    reference_levels = MonthlyStatusReferenceLevels(**scenario["reference_levels"])
    candidates = MonthlyStatusDecisionTable().build_candidates(
        scenario["instrument_group"],
        reference_levels,
        bullish_value=scenario.get("bullish_value"),
        bearish_value=scenario.get("bearish_value"),
    )
    candidate_map = {candidate.trigger_name: candidate for candidate in candidates}

    for trigger_name, expected_condition in scenario["expected_candidates"].items():
        assert candidate_map[trigger_name].condition_met is expected_condition

    for trigger_name, expected_threshold in (scenario.get("expected_thresholds") or {}).items():
        assert candidate_map[trigger_name].threshold_value == pytest.approx(expected_threshold)

    assert scenario["expected_final_status"] is None
    assert isinstance(candidates, list)
    assert not hasattr(candidates, "final_status")


def test_monthly_status_scenarios_do_not_use_final_status_engine() -> None:
    scenario = next(
        item for item in _load_scenarios() if item["name"] == "unresolved_cf_example"
    )
    reference_levels = MonthlyStatusReferenceLevels(**scenario["reference_levels"])

    candidates = MonthlyStatusDecisionTable().build_candidates(
        scenario["instrument_group"],
        reference_levels,
    )
    candidate_map = {candidate.trigger_name: candidate for candidate in candidates}

    assert scenario["expected_final_status"] is None
    assert candidate_map["BULL_CF_B_THRESHOLD"].condition_met is None
    assert candidate_map["BEAR_CF_B_THRESHOLD"].condition_met is None
