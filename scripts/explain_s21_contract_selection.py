from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CandidateRow:
    session_date: str
    monthly_status: str
    unique_code: str
    option_type: str
    leg_verdict: str
    selected_contract: str | None
    selected_strike: float | None
    selection_phase: str | None
    phase: str
    symbol: str
    strike: float
    expiry: str
    candidate_premium: float | None
    premium_source: str | None
    required_premium: float | None
    premium_pass: bool
    oi: float | None
    required_oi: float | None
    oi_pass: bool
    status: str
    reasons: list[str]
    selected: bool


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _as_float(v):
    return None if v is None else float(v)


def _rows_for_day(day: str, replay: dict[str, Any]) -> list[CandidateRow]:
    monthly_status = str(replay.get("monthly_status") or "")
    rows: list[CandidateRow] = []

    for leg in replay.get("legs", []):
        unique_code = str(leg.get("unique_code") or "")
        selected_contract = leg.get("selected_contract")
        selected_strike = _as_float(leg.get("selected_strike"))
        selection_phase = leg.get("selection_phase")

        for c in leg.get("candidate_decisions", []):
            symbol = str(c.get("symbol") or "")
            rows.append(
                CandidateRow(
                    session_date=day,
                    monthly_status=monthly_status,
                    unique_code=unique_code,
                    option_type=str(c.get("option_type") or leg.get("option_type") or ""),
                    leg_verdict=str(leg.get("verdict") or ""),
                    selected_contract=str(selected_contract) if selected_contract else None,
                    selected_strike=selected_strike,
                    selection_phase=str(selection_phase) if selection_phase else None,
                    phase=str(c.get("phase") or ""),
                    symbol=symbol,
                    strike=float(c.get("strike") or 0.0),
                    expiry=str(c.get("expiry") or ""),
                    candidate_premium=_as_float(c.get("candidate_premium")),
                    premium_source=str(c.get("premium_source") or "") or None,
                    required_premium=_as_float(c.get("required_premium")),
                    premium_pass=bool(c.get("premium_pass")),
                    oi=_as_float(c.get("oi")),
                    required_oi=_as_float(c.get("required_oi")),
                    oi_pass=bool(c.get("oi_pass")),
                    status=str(c.get("status") or ""),
                    reasons=[str(x) for x in c.get("reasons", [])],
                    selected=(selected_contract == symbol),
                )
            )

    return rows


def _reason_bucket(row: CandidateRow) -> str:
    if row.selected:
        return "SELECTED"
    if not row.oi_pass and not row.premium_pass:
        return "OI_AND_PREMIUM_FAILED"
    if not row.oi_pass:
        return "OI_FAILED"
    if not row.premium_pass:
        return "PREMIUM_FAILED"
    if row.status == "QUALIFIED":
        return "QUALIFIED_NOT_SELECTED_EARLIER_PRIORITY_WON"
    return "OTHER"


def _write_markdown(rows: list[CandidateRow], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# S21 Contract Selection Explanation", ""]

    days = sorted({r.session_date for r in rows})
    for day in days:
        day_rows = [r for r in rows if r.session_date == day]
        if not day_rows:
            continue

        lines += [f"## {day}", ""]
        monthly = day_rows[0].monthly_status
        lines.append(f"Monthly Status: **{monthly}**")
        lines.append("")

        codes = []
        for r in day_rows:
            if r.unique_code not in codes:
                codes.append(r.unique_code)

        for code in codes:
            leg_rows = [r for r in day_rows if r.unique_code == code]
            first = leg_rows[0]
            lines += [
                f"### {code}",
                "",
                f"- Verdict: **{first.leg_verdict}**",
                f"- Selected contract: `{first.selected_contract}`",
                f"- Selected strike: `{first.selected_strike}`",
                f"- Selection phase: `{first.selection_phase}`",
                "",
                "| # | Phase | Strike | Symbol | Premium | Required | Prem OK | OI | Req OI | OI OK | Result | Reason |",
                "|---:|---|---:|---|---:|---:|---|---:|---:|---|---|---|",
            ]
            for idx, r in enumerate(leg_rows, 1):
                reason = _reason_bucket(r)
                if r.reasons:
                    reason += ": " + ", ".join(r.reasons)
                lines.append(
                    f"| {idx} | {r.phase} | {r.strike:.0f} | `{r.symbol}` | "
                    f"{'' if r.candidate_premium is None else r.candidate_premium} | "
                    f"{'' if r.required_premium is None else r.required_premium} | "
                    f"{'YES' if r.premium_pass else 'NO'} | "
                    f"{'' if r.oi is None else r.oi} | "
                    f"{'' if r.required_oi is None else r.required_oi} | "
                    f"{'YES' if r.oi_pass else 'NO'} | "
                    f"{'SELECTED' if r.selected else r.status} | {reason} |"
                )

            # concise diagnosis
            selected = next((r for r in leg_rows if r.selected), None)
            if selected:
                lines += [
                    "",
                    f"**Why finalized:** `{selected.symbol}` was the first qualifying candidate "
                    f"in authoritative phase `{selected.phase}` that passed both premium and OI.",
                    "",
                ]
            else:
                oi_failed = sum(1 for r in leg_rows if not r.oi_pass)
                prem_failed = sum(1 for r in leg_rows if not r.premium_pass)
                both_failed = sum(1 for r in leg_rows if not r.oi_pass and not r.premium_pass)
                qualified = sum(1 for r in leg_rows if r.oi_pass and r.premium_pass)
                lines += [
                    "",
                    f"**Why no contract:** qualified={qualified}, "
                    f"premium_failed={prem_failed}, oi_failed={oi_failed}, both_failed={both_failed}.",
                    "",
                ]

    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Explain every S21 candidate selection/rejection.")
    ap.add_argument("--dates", nargs="+", required=True)
    ap.add_argument("--replay-root", default="reports/s21_pure_replay")
    ap.add_argument("--output-root", default="reports/s21_decision_explanation")
    args = ap.parse_args()

    replay_root = Path(args.replay_root)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    all_rows: list[CandidateRow] = []
    for day in args.dates:
        replay_path = replay_root / day / "s21_replay.json"
        replay = _load_json(replay_path)
        all_rows.extend(_rows_for_day(day, replay))

    json_path = output_root / "candidate_decisions.json"
    json_path.write_text(
        json.dumps([asdict(r) for r in all_rows], indent=2, sort_keys=True),
        encoding="utf-8",
    )

    csv_path = output_root / "candidate_decisions.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        fields = [
            "session_date","monthly_status","unique_code","option_type","leg_verdict",
            "selected_contract","selected_strike","selection_phase","phase","symbol",
            "strike","expiry","candidate_premium","premium_source","required_premium",
            "premium_pass","oi","required_oi","oi_pass","status","reasons","selected",
            "reason_bucket",
        ]
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in all_rows:
            d = asdict(r)
            d["reasons"] = "; ".join(r.reasons)
            d["reason_bucket"] = _reason_bucket(r)
            w.writerow(d)

    md_path = output_root / "candidate_decisions.md"
    _write_markdown(all_rows, md_path)

    print("S21 DECISION EXPLANATION")
    print("=" * 100)
    for day in args.dates:
        print(day)
        day_rows = [r for r in all_rows if r.session_date == day]
        for code in sorted({r.unique_code for r in day_rows}):
            leg_rows = [r for r in day_rows if r.unique_code == code]
            selected = next((r for r in leg_rows if r.selected), None)
            qualified = sum(1 for r in leg_rows if r.oi_pass and r.premium_pass)
            premium_failed = sum(1 for r in leg_rows if not r.premium_pass)
            oi_failed = sum(1 for r in leg_rows if not r.oi_pass)
            print(
                f"  {code}: selected={selected.symbol if selected else None}; "
                f"qualified={qualified}; premium_failed={premium_failed}; oi_failed={oi_failed}; "
                f"verdict={leg_rows[0].leg_verdict if leg_rows else 'NO_ROWS'}"
            )
    print("=" * 100)
    print(f"Markdown: {md_path}")
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
