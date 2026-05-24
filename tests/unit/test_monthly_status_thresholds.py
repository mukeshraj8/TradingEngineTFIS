from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tfis.monthly_status import REQUIRED_GROUPS, load_monthly_status_thresholds


ROOT = Path(__file__).resolve().parents[2]
THRESHOLDS_PATH = ROOT / "config" / "monthly_status_thresholds.yaml"


def test_monthly_status_threshold_config_loads() -> None:
    thresholds = load_monthly_status_thresholds()

    assert set(REQUIRED_GROUPS).issubset(thresholds.keys())


def test_all_required_groups_exist() -> None:
    thresholds = load_monthly_status_thresholds(THRESHOLDS_PATH)

    for group_name in REQUIRED_GROUPS:
        assert group_name in thresholds


def test_expected_values_match_reference_examples() -> None:
    thresholds = load_monthly_status_thresholds(THRESHOLDS_PATH)

    assert thresholds["nifty"].a_pct == pytest.approx(0.75)
    assert thresholds["nifty"].b_pct == pytest.approx(0.75)
    assert thresholds["nifty"].c_pct == pytest.approx(0.15)

    assert thresholds["stock"].a_pct == pytest.approx(2.50)
    assert thresholds["stock"].b_pct == pytest.approx(2.00)
    assert thresholds["stock"].c_pct == pytest.approx(1.00)

    assert thresholds["currency"].a_pct == pytest.approx(0.15)
    assert thresholds["currency"].b_pct == pytest.approx(0.05)
    assert thresholds["currency"].c_pct == pytest.approx(0.05)

    assert thresholds["crude_oil"].a_pct == pytest.approx(2.00)
    assert thresholds["crude_oil"].b_pct == pytest.approx(1.50)
    assert thresholds["crude_oil"].c_pct == pytest.approx(0.30)


def test_invalid_negative_value_fails(tmp_path: Path) -> None:
    data = yaml.safe_load(THRESHOLDS_PATH.read_text(encoding="utf-8"))
    data["instrument_groups"]["nifty"]["a_pct"] = -0.75
    invalid_path = tmp_path / "monthly_status_thresholds.yaml"
    invalid_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="a_pct must be non-negative"):
        load_monthly_status_thresholds(invalid_path)
