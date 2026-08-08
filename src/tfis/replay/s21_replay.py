from __future__ import annotations

import json
from pathlib import Path

from tfis.replay.s21_evidence import load_s21_replay_evidence
from tfis.strategy_engine.s21 import S21StrategyEngine, decision_to_dict


def run_s21_replay(
    *,
    evidence_path: str | Path,
    output_dir: str | Path,
):
    """Pure deterministic replay.

    It reads a sealed evidence file and calls the same pure strategy engine.
    It has no broker/auth/network imports and cannot fetch missing data.
    """
    evidence = load_s21_replay_evidence(evidence_path)
    decision = S21StrategyEngine().evaluate(evidence)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = decision_to_dict(decision)
    (output_dir / "s21_replay.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "s21_replay.md").write_text(
        _render_markdown(payload),
        encoding="utf-8",
    )
    return decision


def _render_markdown(payload: dict) -> str:
    lines = [
        f"# S21 Replay — {payload['session_date']}",
        "",
        f"- Monthly Status: **{payload['monthly_status']}**",
        f"- Evidence complete: **{payload['evidence_complete']}**",
        f"- Eligible legs: `{', '.join(payload['eligible_legs'])}`",
        "",
    ]
    if payload["evidence_gaps"]:
        lines += ["## Evidence gaps"] + [
            f"- `{gap}`" for gap in payload["evidence_gaps"]
        ] + [""]

    for leg in payload["legs"]:
        lines += [
            f"## {leg['unique_code']}",
            f"- Strike range: `{leg['start_strike']} -> {leg['end_strike']}`",
            f"- Ideal / Minimum: `{leg['ideal_premium']} / {leg['minimum_premium']}`",
            f"- OI requirement: `{leg['minimum_oi_units']}`",
            f"- Selected: `{leg['selected_contract']}`",
            f"- Entry / Target / SL: `{leg['entry']} / {leg['target']} / {leg['stoploss']}`",
            f"- ORPT: **{leg['orpt_status']}**",
            f"- RC: **{leg['rc_status']}**",
            f"- Order time: `{leg['order_time']}`",
            f"- Verdict: **{leg['verdict']}**",
            "",
            "### Candidate audit",
            "",
            "| Phase | Strike | Symbol | OI | Chain Premium | Required | Status | Reasons |",
            "|---|---:|---|---:|---:|---:|---|---|",
        ]
        for row in leg["candidate_decisions"]:
            reasons = ", ".join(row["reasons"]) if row["reasons"] else "-"
            lines.append(
                f"| {row['phase']} | {row['strike']} | `{row['symbol']}` | "
                f"{row['oi']} | {row['candidate_premium']} | "
                f"{row['required_premium']} | {row['status']} | {reasons} |"
            )
        lines.append("")
    return "\n".join(lines)
