from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from tfis.domain.enums import Segment
from tfis.domain.strategy_rule import StrategyRule


@dataclass(frozen=True, slots=True)
class FormulaSafetyFinding:
    severity: str
    field_name: str
    message: str
    formula: str


_PLAIN_PRV_PATTERN = re.compile(r"\bPRV_(?:2DHH|2DLL|3DHH|3DLL|4DHH|4DLL)\b")
_OPT_PRV_PATTERN = re.compile(r"\bOPT_PRV_(?:2DHH|2DLL|3DHH|3DLL)\b")


def validate_strategy_rule_formula_safety(
    rule: StrategyRule,
    *,
    crosscheck: dict[str, Any] | None = None,
) -> list[FormulaSafetyFinding]:
    if rule.segment not in {Segment.OPTIONS_BUY, Segment.OPTIONS_SELL}:
        return []

    findings: list[FormulaSafetyFinding] = []
    for field_name in ("entry_formula", "stoploss_formula"):
        formula = str(getattr(rule, field_name))
        contains_plain_prv = bool(_PLAIN_PRV_PATTERN.search(formula))
        contains_opt_prv = bool(_OPT_PRV_PATTERN.search(formula))
        expects_opt = _expects_opt_reference(field_name, crosscheck)

        if expects_opt:
            if contains_plain_prv and not contains_opt_prv:
                findings.append(
                    FormulaSafetyFinding(
                        severity="ERROR",
                        field_name=field_name,
                        message=(
                            f"{field_name} uses plain PRV_* reference where the strategy cross-check "
                            "indicates an option-premium source"
                        ),
                        formula=formula,
                    )
                )
            elif not contains_opt_prv:
                findings.append(
                    FormulaSafetyFinding(
                        severity="WARN",
                        field_name=field_name,
                        message=(
                            f"{field_name} is expected to use OPT_* aliases based on the strategy "
                            "cross-check, but no OPT_* alias was found"
                        ),
                        formula=formula,
                    )
                )
        elif contains_plain_prv and not contains_opt_prv:
            findings.append(
                FormulaSafetyFinding(
                    severity="WARN",
                    field_name=field_name,
                    message=(
                        f"{field_name} uses plain PRV_* reference in an options strategy, but the "
                        "cross-check did not explicitly confirm whether this should be OPT_*"
                    ),
                    formula=formula,
                )
            )

    return findings


def _expects_opt_reference(
    field_name: str,
    crosscheck: dict[str, Any] | None,
) -> bool:
    if not isinstance(crosscheck, dict):
        return False

    source_cells = crosscheck.get("source_cells")
    sample_calculation = crosscheck.get("sample_calculation")
    if not isinstance(source_cells, dict) or field_name not in source_cells:
        return False
    if not isinstance(sample_calculation, dict):
        return False

    option_levels = sample_calculation.get("option_levels")
    return isinstance(option_levels, dict) and bool(option_levels)
