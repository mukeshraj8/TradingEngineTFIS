from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


DEFAULT_THRESHOLDS_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "monthly_status_thresholds.yaml"
)
REQUIRED_GROUPS = (
    "nifty",
    "banknifty",
    "stock",
    "currency",
    "gold",
    "silver",
    "crude_oil",
    "natural_gas",
)


@dataclass(frozen=True, slots=True)
class MonthlyStatusThresholds:
    instrument_group: str
    a_pct: float
    b_pct: float
    c_pct: float

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_group, str) or not self.instrument_group.strip():
            raise ValueError("instrument_group must be a non-empty string")
        for field_name in ("a_pct", "b_pct", "c_pct"):
            value = float(getattr(self, field_name))
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative")


def load_monthly_status_thresholds(
    path: Path | None = None,
) -> dict[str, MonthlyStatusThresholds]:
    thresholds_path = path or DEFAULT_THRESHOLDS_PATH
    with thresholds_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Monthly status thresholds must contain a mapping: {thresholds_path}")

    groups = data.get("instrument_groups")
    if not isinstance(groups, dict):
        raise ValueError(
            f"Monthly status thresholds missing instrument_groups mapping: {thresholds_path}"
        )

    missing_groups = [group for group in REQUIRED_GROUPS if group not in groups]
    if missing_groups:
        raise ValueError(
            "Monthly status thresholds missing required groups: "
            + ", ".join(missing_groups)
        )

    thresholds: dict[str, MonthlyStatusThresholds] = {}
    for group_name, raw_values in groups.items():
        if not isinstance(raw_values, dict):
            raise ValueError(
                f"Monthly status threshold group must be a mapping: {group_name}"
            )
        for field_name in ("a_pct", "b_pct", "c_pct", "source_notes"):
            if field_name not in raw_values:
                raise ValueError(
                    f"Monthly status threshold group {group_name} missing {field_name}"
                )
        thresholds[str(group_name)] = MonthlyStatusThresholds(
            instrument_group=str(group_name),
            a_pct=float(raw_values["a_pct"]),
            b_pct=float(raw_values["b_pct"]),
            c_pct=float(raw_values["c_pct"]),
        )

    return thresholds
