from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare old and rule-corrected HSRE S23 January 2024 reports."
    )
    parser.add_argument("--old-dir", required=True)
    parser.add_argument("--new-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    old_dir = Path(args.old_dir)
    new_dir = Path(args.new_dir)
    output = Path(args.output)
    old = _load_run(old_dir)
    new = _load_run(new_dir)
    output.write_text(_markdown(old, new, old_dir, new_dir), encoding="utf-8")
    print(f"WROTE {output}")
    return 0


def _load_run(root: Path) -> dict[str, Any]:
    return {
        "summary": json.loads((root / "summary.json").read_text(encoding="utf-8")),
        "daily": _rows(root / "daily_decisions.csv"),
        "trades": _rows(root / "trades.csv"),
        "candidates": _rows(root / "rejected_candidates_summary.csv"),
        "entry_distance": _rows(root / "entry_distance.csv"),
    }


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _markdown(old: dict[str, Any], new: dict[str, Any], old_dir: Path, new_dir: Path) -> str:
    lines = [
        "# S23 January 2024 Rule-Correction Before/After",
        "",
        f"Old artifacts: `{old_dir}`",
        f"Corrected artifacts: `{new_dir}`",
        "",
        "## Summary",
        "",
        "| Metric | Old | Corrected | Delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for label, getter in _summary_metrics():
        old_value = getter(old)
        new_value = getter(new)
        lines.append(f"| {label} | {_fmt(old_value)} | {_fmt(new_value)} | {_delta(old_value, new_value)} |")

    lines.extend(["", "## CALL / PUT Breakdown", ""])
    lines.extend(_breakdown_table(old, new))
    lines.extend(["", "## Entry Distance", ""])
    lines.extend(_entry_distance_table(old, new))
    lines.extend(["", "## Per-Day Selection Changes", ""])
    lines.extend(_selection_changes(old, new))
    lines.extend(["", "## Candidate Filter Totals", ""])
    lines.extend(_candidate_table(old, new))
    return "\n".join(lines) + "\n"


def _summary_metrics() -> list[tuple[str, Any]]:
    return [
        ("Observed sessions", lambda run: run["summary"]["date_coverage"]["observed_trading_days"]),
        ("Branch attempts", lambda run: len(run["candidates"])),
        ("Selected contracts", lambda run: sum(1 for row in run["daily"] if row.get("selected_contract"))),
        (
            "No qualifying contracts",
            lambda run: run["summary"]["non_trade_reason_counts"].get("NO_QUALIFYING_CONTRACT", 0),
        ),
        (
            "Exact-history failures",
            lambda run: run["summary"]["non_trade_reason_counts"].get("INSUFFICIENT_OPTION_HISTORY", 0),
        ),
        ("Final orders ready", lambda run: run["summary"]["funnel"]["final_orders_ready"]),
        ("CALL ready", lambda run: run["summary"]["ce_pe_breakdown"]["CALL"]["orders_ready"]),
        ("PUT ready", lambda run: run["summary"]["ce_pe_breakdown"]["PUT"]["orders_ready"]),
        ("Entry triggered", lambda run: run["summary"]["trade_metrics"]["entries_triggered"]),
        ("Trigger rate", lambda run: run["summary"]["trade_metrics"]["trigger_rate"]),
        ("Actual trades", lambda run: run["summary"]["trade_metrics"]["trades"]),
        ("Wins", lambda run: run["summary"]["trade_metrics"]["wins"]),
        ("Losses", lambda run: run["summary"]["trade_metrics"]["losses"]),
        ("Net points", lambda run: run["summary"]["trade_metrics"]["net_total_points"]),
        ("Profit factor", lambda run: run["summary"]["trade_metrics"]["profit_factor"]),
        ("Max point drawdown", lambda run: run["summary"]["trade_metrics"]["max_drawdown_points"]),
        ("ORPT misses", lambda run: run["summary"]["orpt_recalculation"]["entry_missed_at_orpt"]),
        ("Recalculations", lambda run: run["summary"]["orpt_recalculation"]["recalculation_required"]),
        ("RC cases", lambda run: run["summary"]["orpt_recalculation"]["rc_required"]),
    ]


def _breakdown_table(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    lines = [
        "| Side | Old ready | New ready | Old triggered | New triggered | Old trades | New trades | Old net | New net |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for side in ("CALL", "PUT"):
        old_side = old["summary"]["ce_pe_breakdown"][side]
        new_side = new["summary"]["ce_pe_breakdown"][side]
        lines.append(
            f"| {side} | {old_side['orders_ready']} | {new_side['orders_ready']} | "
            f"{old_side['entries_triggered']} | {new_side['entries_triggered']} | "
            f"{old_side['trades']} | {new_side['trades']} | "
            f"{_fmt(old_side['net_points'])} | {_fmt(new_side['net_points'])} |"
        )
    return lines


def _entry_distance_table(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    lines = [
        "| Scope | Old avg abs points | New avg abs points | Old touched | New touched | Old rows | New rows |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        _entry_distance_row("ALL", old["entry_distance"], new["entry_distance"]),
    ]
    for side in ("CALL", "PUT"):
        old_rows = [row for row in old["entry_distance"] if row.get("option_type") == side]
        new_rows = [row for row in new["entry_distance"] if row.get("option_type") == side]
        lines.append(_entry_distance_row(side, old_rows, new_rows))
    return lines


def _entry_distance_row(label: str, old_rows: list[dict[str, str]], new_rows: list[dict[str, str]]) -> str:
    old_avg = _avg(row.get("min_distance_abs_points") for row in old_rows)
    new_avg = _avg(row.get("min_distance_abs_points") for row in new_rows)
    old_touched = sum(1 for row in old_rows if _bool(row.get("entry_touched")))
    new_touched = sum(1 for row in new_rows if _bool(row.get("entry_touched")))
    return (
        f"| {label} | {_fmt(old_avg)} | {_fmt(new_avg)} | "
        f"{old_touched} | {new_touched} | {len(old_rows)} | {len(new_rows)} |"
    )


def _selection_changes(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    old_by_date = {row["date"]: row for row in old["daily"]}
    new_by_date = {row["date"]: row for row in new["daily"]}
    dates = sorted(set(old_by_date) | set(new_by_date))
    lines = [
        "| Date | Branch | Old contract | New contract | Old premium | New premium | Old OI threshold | New OI threshold | Old entry | New entry | Old trigger | New trigger |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for date_key in dates:
        old_row = old_by_date.get(date_key, {})
        new_row = new_by_date.get(date_key, {})
        if not _materially_changed(old_row, new_row):
            continue
        lines.append(
            f"| {date_key} | {new_row.get('branch') or old_row.get('branch') or ''} | "
            f"{old_row.get('selected_contract', '')} | {new_row.get('selected_contract', '')} | "
            f"{old_row.get('premium_0916', '')} | {new_row.get('premium_0916', '')} | "
            f"{old_row.get('minimum_oi_units', '')} | {new_row.get('minimum_oi_units', '')} | "
            f"{old_row.get('final_entry', '')} | {new_row.get('final_entry', '')} | "
            f"{old_row.get('entry_triggered', '')} | {new_row.get('entry_triggered', '')} |"
        )
    if len(lines) == 2:
        lines.append("| No material per-day selection changes |  |  |  |  |  |  |  |  |  |  |  |")
    return lines


def _candidate_table(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    old_totals = _candidate_totals(old["candidates"])
    new_totals = _candidate_totals(new["candidates"])
    lines = [
        "| Metric | Old | Corrected | Delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for key in ("candidate_count", "expiry_rejected", "oi_rejected", "premium_rejected", "qualified_count"):
        lines.append(f"| {key} | {old_totals[key]} | {new_totals[key]} | {new_totals[key] - old_totals[key]} |")
    return lines


def _candidate_totals(rows: list[dict[str, str]]) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for row in rows:
        for key in ("candidate_count", "expiry_rejected", "oi_rejected", "premium_rejected", "qualified_count"):
            totals[key] += int(float(row.get(key) or 0))
    return totals


def _materially_changed(old_row: dict[str, str], new_row: dict[str, str]) -> bool:
    keys = (
        "branch",
        "selected_contract",
        "premium_0916",
        "minimum_oi_units",
        "final_entry",
        "entry_triggered",
        "final_order_verdict",
    )
    return any((old_row.get(key) or "") != (new_row.get(key) or "") for key in keys)


def _avg(values: Any) -> float | None:
    nums = [float(value) for value in values if value not in (None, "")]
    return sum(nums) / len(nums) if nums else None


def _delta(old: Any, new: Any) -> str:
    if old is None or new is None:
        return ""
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        return _fmt(new - old)
    return ""


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _bool(value: str | None) -> bool:
    return str(value).strip().lower() == "true"


if __name__ == "__main__":
    raise SystemExit(main())
