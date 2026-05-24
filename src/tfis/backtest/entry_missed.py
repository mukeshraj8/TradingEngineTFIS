from __future__ import annotations

from dataclasses import dataclass

from tfis.domain.enums import OptionType

from .recalculation import IntradaySnapshot


@dataclass(frozen=True, slots=True)
class EntryMissedInput:
    option_type: OptionType
    entry_price: float
    orpt_snapshot: IntradaySnapshot


@dataclass(frozen=True, slots=True)
class EntryMissedResult:
    entry_missed: bool
    rule_name: str
    compared_value: float
    threshold_entry_price: float
    notes: tuple[str, ...]


class S23EntryMissedDetector:
    """Diagnostic ORPT-time missed-entry check for S23 option-selling branches.

    Excel rule captured for both call-sell and put-sell entry:

    - if ORPT-time option low < entry price -> entry missed
    - otherwise -> entry not missed

    This detector is intentionally limited to the ORPT check only. It does not:

    - infer recalculation results
    - scan intraday bars automatically
    - alter backtest behavior
    """

    RULE_NAME = "S23_OPTIONS_SELL_ORPT_OPTION_LOW_CHECK_V1"

    def detect(self, detection_input: EntryMissedInput) -> EntryMissedResult:
        option_low = detection_input.orpt_snapshot.option_low
        if option_low is None:
            raise ValueError(
                "ORPT option_low is required for S23 entry-missed detection."
            )

        entry_missed = float(option_low) < float(detection_input.entry_price)
        return EntryMissedResult(
            entry_missed=entry_missed,
            rule_name=self.RULE_NAME,
            compared_value=float(option_low),
            threshold_entry_price=float(detection_input.entry_price),
            notes=(
                (
                    f"Evaluated ORPT snapshot at "
                    f"{detection_input.orpt_snapshot.timestamp.isoformat()}."
                ),
                (
                    f"Applied Excel ORPT low check for {detection_input.option_type.value} "
                    "sell entry: option_low < entry_price."
                ),
            ),
        )
