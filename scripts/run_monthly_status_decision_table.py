from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tfis.monthly_status import (
    MonthlyStatusDecisionTable,
    MonthlyStatusReferenceLevels,
    load_monthly_status_thresholds,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render a diagnostic monthly-status decision table from supplied reference levels."
    )
    parser.add_argument("--instrument-group", required=True, help="Configured instrument group")
    parser.add_argument("--pmh", required=True, type=float, help="Previous month high")
    parser.add_argument("--pml", required=True, type=float, help="Previous month low")
    parser.add_argument("--cmh", required=True, type=float, help="Current month high")
    parser.add_argument("--cml", required=True, type=float, help="Current month low")
    parser.add_argument("--pwh", required=True, type=float, help="Previous week high")
    parser.add_argument("--pwl", required=True, type=float, help="Previous week low")
    parser.add_argument("--cwh", required=True, type=float, help="Current week high")
    parser.add_argument("--cwl", required=True, type=float, help="Current week low")
    parser.add_argument("--current-price", required=True, type=float, help="Current price")
    parser.add_argument("--bullish-value", type=float, help="Optional bullish reference value")
    parser.add_argument("--bearish-value", type=float, help="Optional bearish reference value")
    parser.add_argument("--out", required=True, help="Path to write JSON output")
    parser.add_argument("--markdown-out", help="Optional path to write markdown output")
    return parser


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    return value


def _format_number(value: Any, *, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _render_markdown(report: dict[str, Any]) -> str:
    thresholds = report["thresholds"]
    input_levels = report["input_levels"]
    lines = [
        "# Monthly Status Decision Table",
        "",
        f"- Instrument group: `{report['instrument_group']}`",
        f"- Threshold a_pct: `{_format_number(thresholds['a_pct'])}`",
        f"- Threshold b_pct: `{_format_number(thresholds['b_pct'])}`",
        f"- Threshold c_pct: `{_format_number(thresholds['c_pct'])}`",
        "",
        "This is diagnostic only and does not select final monthly status.",
        "",
        "## Input Levels",
        "",
        f"- PMH: `{_format_number(input_levels['PMH'])}`",
        f"- PML: `{_format_number(input_levels['PML'])}`",
        f"- CMH: `{_format_number(input_levels['CMH'])}`",
        f"- CML: `{_format_number(input_levels['CML'])}`",
        f"- PWH: `{_format_number(input_levels['PWH'])}`",
        f"- PWL: `{_format_number(input_levels['PWL'])}`",
        f"- CWH: `{_format_number(input_levels['CWH'])}`",
        f"- CWL: `{_format_number(input_levels['CWL'])}`",
        f"- current_price: `{_format_number(input_levels['current_price'])}`",
        f"- bullish_value: `{_format_number(report['bullish_value'])}`",
        f"- bearish_value: `{_format_number(report['bearish_value'])}`",
        "",
        "## Candidate Table",
        "",
        "| Trigger | Candidate Status | Threshold | Condition Met | Confidence | Notes |",
        "| --- | --- | ---: | --- | --- | --- |",
    ]

    for candidate in report["candidates"]:
        lines.append(
            "| "
            f"{candidate['trigger_name']} | "
            f"{candidate['candidate_status']} | "
            f"{_format_number(candidate['threshold_value'])} | "
            f"{candidate['condition_met']} | "
            f"{candidate['confidence']} | "
            f"{candidate['notes']} |"
        )

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        thresholds_by_group = load_monthly_status_thresholds()
        if args.instrument_group not in thresholds_by_group:
            raise ValueError(
                f"Unknown instrument group for monthly-status decision table: {args.instrument_group}"
            )

        reference_levels = MonthlyStatusReferenceLevels(
            PMH=args.pmh,
            PML=args.pml,
            CMH=args.cmh,
            CML=args.cml,
            PWH=args.pwh,
            PWL=args.pwl,
            CWH=args.cwh,
            CWL=args.cwl,
            current_price=args.current_price,
        )
        decision_table = MonthlyStatusDecisionTable(thresholds_by_group)
        candidates = decision_table.build_candidates(
            args.instrument_group,
            reference_levels,
            bullish_value=args.bullish_value,
            bearish_value=args.bearish_value,
        )
    except (KeyError, ValueError) as exc:
        print(f"Decision table refused: {exc}")
        return 1

    report = {
        "instrument_group": args.instrument_group,
        "thresholds": _to_jsonable(thresholds_by_group[args.instrument_group]),
        "input_levels": _to_jsonable(reference_levels),
        "bullish_value": args.bullish_value,
        "bearish_value": args.bearish_value,
        "candidates": _to_jsonable(candidates),
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Decision table JSON written to {out_path}")

    if args.markdown_out:
        markdown_path = Path(args.markdown_out)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(_render_markdown(report), encoding="utf-8")
        print(f"Decision table markdown written to {markdown_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
