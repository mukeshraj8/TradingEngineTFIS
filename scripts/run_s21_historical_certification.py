from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from statistics import mean, median
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"

BUILD_EVIDENCE = REPO_ROOT / "scripts" / "build_s21_replay_evidence.py"
COLLECT_EVIDENCE = REPO_ROOT / "scripts" / "collect_s21_replay_option_evidence.py"
RUN_REPLAY = REPO_ROOT / "scripts" / "run_s21_historical_replay.py"
ENTRY_DISTANCE = REPO_ROOT / "scripts" / "certify_s21_entry_distance.py"

DEFAULT_CERT_ROOT = REPO_ROOT / "reports" / "s21_certification_input"
DEFAULT_EVIDENCE_ROOT = REPO_ROOT / "reports" / "s21_replay_evidence"
DEFAULT_OPTION_ROOT = REPO_ROOT / "reports" / "s21_replay_option_evidence"
DEFAULT_REPLAY_ROOT = REPO_ROOT / "reports" / "s21_pure_replay"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "s21_historical_certification"


@dataclass
class LegSummary:
    unique_code: str
    verdict: str
    selected_contract: str | None
    entry: float | None
    orpt_status: str
    rc_status: str
    order_time: str | None
    minimum_low: float | None = None
    minimum_low_time: str | None = None
    gap_points: float | None = None
    gap_pct: float | None = None
    entry_triggered: bool | None = None


@dataclass
class DaySummary:
    session_date: str
    status: str
    monthly_status: str | None
    evidence_complete: bool | None
    bull_call: LegSummary | None
    bull_put: LegSummary | None
    bear_call: LegSummary | None
    bear_put: LegSummary | None
    both_active_legs_selected: bool
    any_entry_triggered: bool
    rc_required: bool
    no_contract: bool
    error: str | None = None


def run_cmd(cmd: list[str], allow_fail: bool = False) -> subprocess.CompletedProcess:
    print("\n>", " ".join(map(str, cmd)), flush=True)
    p = subprocess.run(cmd, cwd=str(REPO_ROOT), text=True, capture_output=True)
    if p.stdout:
        print(p.stdout, end="")
    if p.stderr:
        print(p.stderr, end="", file=sys.stderr)
    if p.returncode and not allow_fail:
        raise RuntimeError(f"Command failed ({p.returncode})")
    return p


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def weekdays(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def build_evidence(session_date: date, cert_root: Path, evidence_path: Path, option_dir: Path | None = None):
    cmd = [str(PYTHON), str(BUILD_EVIDENCE),
           "--certification-root", str(cert_root),
           "--session-date", session_date.isoformat(),
           "--output", str(evidence_path)]
    if option_dir is not None:
        cmd += ["--option-evidence-dir", str(option_dir)]
    return run_cmd(cmd, allow_fail=True)


def collect_daily(session_date: date, manifest: Path, option_dir: Path):
    if not manifest.exists() or not manifest.read_text(encoding="utf-8").strip():
        return
    run_cmd([str(PYTHON), str(COLLECT_EVIDENCE),
             "--symbols-file", str(manifest),
             "--session-date", session_date.isoformat(),
             "--output-root", str(option_dir),
             "--mode", "daily"], allow_fail=True)


def run_replay(evidence_path: Path, replay_dir: Path):
    return run_cmd([str(PYTHON), str(RUN_REPLAY),
                    "--evidence", str(evidence_path),
                    "--output-dir", str(replay_dir)], allow_fail=True)


def replay_json(replay_dir: Path) -> Path:
    p = replay_dir / "s21_replay.json"
    if p.exists():
        return p
    found = list(replay_dir.glob("*.json"))
    if not found:
        raise FileNotFoundError(f"No replay JSON found in {replay_dir}")
    return found[0]


def collect_selected_minute(session_date: date, replay: dict[str, Any], option_dir: Path) -> tuple[bool, bool]:
    """Ensure selected contracts have full-session minute evidence.

    Returns:
        (collection_attempted, replay_needs_rebuild)

    We need full-session 09:24-15:30 evidence for two distinct purposes:
    1. ORPT/RC completion when replay currently reports MISSING_ORPT_BAR.
    2. Entry-trigger/distance certification for NORMAL_ORDER_READY_AT_09_25.

    The collector itself is cache-aware, so it is safe to pass already-cached
    selected contracts: valid full-session caches become CACHE_HIT and do not
    touch FYERS.
    """
    symbols: list[str] = []
    replay_needs_rebuild = False

    for leg in replay.get("legs", []):
        symbol = leg.get("selected_contract")
        if not symbol:
            continue

        verdict = str(leg.get("verdict") or "")
        gaps = [str(x) for x in leg.get("evidence_gaps", [])]

        if verdict == "NORMAL_ORDER_READY_AT_09_25":
            symbols.append(str(symbol))
            continue

        if verdict == "EVIDENCE_INCOMPLETE" and gaps and all(
            "MISSING_ORPT_BAR" in g for g in gaps
        ):
            symbols.append(str(symbol))
            replay_needs_rebuild = True

    symbols = sorted(set(symbols))
    if not symbols:
        return False, False

    f = option_dir / "selected_contracts_full_session.txt"
    f.write_text("\n".join(symbols) + "\n", encoding="utf-8")
    proc = run_cmd([
        str(PYTHON), str(COLLECT_EVIDENCE),
        "--symbols-file", str(f),
        "--session-date", session_date.isoformat(),
        "--output-root", str(option_dir),
        "--mode", "minute",
        "--minute-from", "09:24",
        "--minute-to", "15:30",
    ], allow_fail=True)

    # If collection itself failed, downstream offline distance certification
    # will truthfully classify the day PARTIAL_MARKET_EVIDENCE.
    return True, replay_needs_rebuild and proc.returncode == 0


def run_distance(session_date: date):
    return run_cmd([
        str(PYTHON), str(ENTRY_DISTANCE),
        "--dates", session_date.isoformat(),
        "--option-evidence-root", "reports/s21_replay_option_evidence",
        "--offline-only",
    ], allow_fail=True)


def distance_lookup(session_date: date) -> dict[str, dict[str, Any]]:
    p = REPO_ROOT / "reports" / "s21_entry_distance_certification" / "summary.json"
    if not p.exists():
        return {}
    payload = json.loads(p.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload.get("rows", [])
    return {
        str(r.get("selected_contract")): r
        for r in rows
        if str(r.get("session_date")) == session_date.isoformat()
    }


def leg_summary(leg: dict[str, Any] | None, distances: dict[str, dict[str, Any]]) -> LegSummary | None:
    if not leg:
        return None
    contract = leg.get("selected_contract")
    d = distances.get(str(contract), {}) if contract else {}
    return LegSummary(
        unique_code=str(leg.get("unique_code") or ""),
        verdict=str(leg.get("verdict") or ""),
        selected_contract=str(contract) if contract else None,
        entry=float(leg["entry"]) if leg.get("entry") is not None else None,
        orpt_status=str(leg.get("orpt_status") or ""),
        rc_status=str(leg.get("rc_status") or ""),
        order_time=str(leg.get("order_time")) if leg.get("order_time") else None,
        minimum_low=float(d["minimum_low"]) if d.get("minimum_low") is not None else None,
        minimum_low_time=str(d.get("minimum_low_bar_start")) if d.get("minimum_low_bar_start") else None,
        gap_points=float(d["min_low_minus_entry"]) if d.get("min_low_minus_entry") is not None else None,
        gap_pct=float(d["min_low_minus_entry_pct_of_entry"]) if d.get("min_low_minus_entry_pct_of_entry") is not None else None,
        entry_triggered=bool(d["entry_triggered"]) if d.get("entry_triggered") is not None else None,
    )


def active_codes(monthly_status: str | None):
    if monthly_status in {"BULL", "BULL_CF"}:
        return ("BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL", "BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT")
    if monthly_status in {"BEAR", "BEAR_CF"}:
        return ("BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL", "BANKNIFTY_OP_SELL_MONTHLY_BEAR_PUT")
    return ("", "")


def certify_day(session_date: date, args) -> DaySummary:
    ds = session_date.isoformat()
    evidence_dir = args.evidence_root / ds
    option_dir = args.option_root / ds
    replay_dir = args.replay_root / ds
    evidence_path = evidence_dir / "s21_replay_evidence.json"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    option_dir.mkdir(parents=True, exist_ok=True)
    replay_dir.mkdir(parents=True, exist_ok=True)

    try:
        p = build_evidence(session_date, args.certification_root, evidence_path)

        # build_s21_replay_evidence intentionally exits non-zero when it has
        # successfully written a base evidence file but still needs option
        # history. Therefore returncode alone is NOT a build-failure signal.
        # The durable artifact is authoritative here.
        if not evidence_path.exists():
            message = (p.stderr or p.stdout)[-1000:]
            if "Missing archived evidence" in message:
                return DaySummary(
                    ds, "NO_ARCHIVED_EVIDENCE", None, None,
                    None, None, None, None,
                    False, False, False, False,
                    error=message,
                )
            return DaySummary(
                ds, "EVIDENCE_BUILD_FAILED", None, None,
                None, None, None, None,
                False, False, False, False,
                error=message,
            )

        manifest = evidence_path.with_suffix(".missing_option_history.txt")

        # Reuse already-collected per-date option evidence BEFORE making any
        # broker calls. This makes reruns cheap and deterministic.
        merged_cache_complete = False
        if option_dir.exists() and any(option_dir.iterdir()):
            merged = build_evidence(
                session_date,
                args.certification_root,
                evidence_path,
                option_dir,
            )
            if not evidence_path.exists():
                return DaySummary(
                    ds, "DAILY_MERGE_FAILED", None, None,
                    None, None, None, None,
                    False, False, False, False,
                    error=(merged.stderr or merged.stdout)[-1000:],
                )
            if merged.returncode == 0:
                merged_cache_complete = True
                # The builder can leave an older missing-history manifest
                # beside a newly complete evidence file. It is stale now.
                if manifest.exists():
                    manifest.unlink()

        # If the merged/base evidence still reports missing histories, collect
        # only those symbols, then rebuild with the option-evidence directory.
        if (
            not merged_cache_complete
            and manifest.exists()
            and manifest.read_text(encoding="utf-8").strip()
        ):
            collect_daily(session_date, manifest, option_dir)
            merged = build_evidence(
                session_date,
                args.certification_root,
                evidence_path,
                option_dir,
            )
            if not evidence_path.exists():
                return DaySummary(
                    ds, "DAILY_MERGE_FAILED", None, None,
                    None, None, None, None,
                    False, False, False, False,
                    error=(merged.stderr or merged.stdout)[-1000:],
                )

        p = run_replay(evidence_path, replay_dir)
        try:
            replay_path = replay_json(replay_dir)
        except FileNotFoundError:
            return DaySummary(
                ds, "REPLAY_FAILED", None, None,
                None, None, None, None,
                False, False, False, False,
                error=(p.stderr or p.stdout)[-1000:],
            )

        # Pure replay may return non-zero deliberately when it emitted a valid
        # intermediate report with evidence gaps (for example MISSING_ORPT_BAR).
        # Inspect the artifact instead of treating the exit code as fatal.
        replay = load_json(replay_path)

        # Always ensure full-session selected-contract minute evidence exists
        # for normal orders as well as ORPT-incomplete orders. Previously this
        # only ran for MISSING_ORPT_BAR, which left already-normal Aug-04 with
        # only the legacy 09:24-09:30 cache and made offline fill certification
        # impossible.
        _minute_attempted, replay_needs_rebuild = collect_selected_minute(
            session_date,
            replay,
            option_dir,
        )
        if replay_needs_rebuild:
            p = build_evidence(
                session_date,
                args.certification_root,
                evidence_path,
                option_dir,
            )
            if not p.returncode:
                run_replay(evidence_path, replay_dir)
                replay = load_json(replay_json(replay_dir))

        normal_orders_exist = any(
            l.get("verdict") == "NORMAL_ORDER_READY_AT_09_25"
            for l in replay.get("legs", [])
        )
        distance_ok = True
        if normal_orders_exist:
            distance_proc = run_distance(session_date)
            distance_ok = distance_proc.returncode == 0
        distances = distance_lookup(session_date) if distance_ok else {}

        by_code = {str(x.get("unique_code")): x for x in replay.get("legs", [])}
        bull_call = leg_summary(by_code.get("BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL"), distances)
        bull_put = leg_summary(by_code.get("BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT"), distances)
        bear_call = leg_summary(by_code.get("BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL"), distances)
        bear_put = leg_summary(by_code.get("BANKNIFTY_OP_SELL_MONTHLY_BEAR_PUT"), distances)

        monthly = str(replay.get("monthly_status") or "")
        a, b = active_codes(monthly)
        active = [by_code.get(a), by_code.get(b)]
        both_selected = bool(a and b and all(x and x.get("selected_contract") for x in active))

        legs = [bull_call, bull_put, bear_call, bear_put]
        any_triggered = any(x and x.entry_triggered is True for x in legs)
        rc_required = any(
            x and (
                x.orpt_status == "RECALCULATION_REQUIRED"
                or x.verdict == "RECALCULATION_REQUIRED"
                or x.rc_status not in {"", "NOT_REQUIRED", "NOT_EVALUATED"}
            )
            for x in legs
        )
        no_contract = any(x and x.verdict == "NO_QUALIFYING_CONTRACT" for x in legs)

        return DaySummary(
            ds,
            (
                "CERTIFIED"
                if replay.get("evidence_complete") is True and distance_ok
                else (
                    "PARTIAL_MARKET_EVIDENCE"
                    if replay.get("evidence_complete") is True and not distance_ok
                    else "PARTIAL"
                )
            ),
            monthly or None,
            bool(replay.get("evidence_complete")),
            bull_call, bull_put, bear_call, bear_put,
            both_selected, any_triggered, rc_required, no_contract,
        )
    except Exception as exc:
        return DaySummary(ds, "ERROR", None, None, None, None, None, None, False, False, False, False,
                          error=f"{type(exc).__name__}: {exc}")


def iter_legs(days):
    for d in days:
        for l in (d.bull_call, d.bull_put, d.bear_call, d.bear_put):
            if l:
                yield d, l


def aggregate(days):
    certified = [d for d in days if d.status == "CERTIFIED"]
    selected = [(d, l) for d, l in iter_legs(certified) if l.selected_contract]
    triggered = [(d, l) for d, l in iter_legs(certified) if l.entry_triggered is True]
    gaps = [l.gap_pct for _, l in selected if l.gap_pct is not None and l.entry_triggered is not None]
    by_leg = {}
    for _, l in selected:
        x = by_leg.setdefault(l.unique_code, {"selected": 0, "triggered": 0})
        x["selected"] += 1
        if l.entry_triggered:
            x["triggered"] += 1

    return {
        "days_requested": len(days),
        "days_certified": len(certified),
        "days_no_archived_evidence": sum(1 for d in days if d.status == "NO_ARCHIVED_EVIDENCE"),
        "days_partial_or_failed": sum(
            1 for d in days
            if d.status not in {"CERTIFIED", "NO_ARCHIVED_EVIDENCE"}
        ),
        "bull_days": sum(1 for d in certified if d.monthly_status in {"BULL", "BULL_CF"}),
        "bear_days": sum(1 for d in certified if d.monthly_status in {"BEAR", "BEAR_CF"}),
        "days_both_active_legs_selected": sum(1 for d in certified if d.both_active_legs_selected),
        "days_any_entry_triggered": sum(1 for d in certified if d.any_entry_triggered),
        "days_rc_required": sum(1 for d in certified if d.rc_required),
        "days_with_no_contract_leg": sum(1 for d in certified if d.no_contract),
        "selected_legs": len(selected),
        "triggered_legs": len(triggered),
        "entry_trigger_rate_pct": (100.0 * len(triggered) / len(selected)) if selected else 0.0,
        "average_gap_pct_for_normal_orders": mean(gaps) if gaps else None,
        "median_gap_pct_for_normal_orders": median(gaps) if gaps else None,
        "by_strategy_leg": by_leg,
    }


def write_reports(days, output_root: Path):
    output_root.mkdir(parents=True, exist_ok=True)
    summary = aggregate(days)
    (output_root / "summary.json").write_text(
        json.dumps({"summary": summary, "days": [asdict(d) for d in days]}, indent=2, sort_keys=True),
        encoding="utf-8"
    )

    fields = ["session_date","status","monthly_status","leg","verdict","selected_contract","entry",
              "orpt_status","rc_status","order_time","minimum_low","minimum_low_time","gap_points","gap_pct","entry_triggered"]
    with (output_root / "daily_legs.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for d, l in iter_legs(days):
            w.writerow({
                "session_date": d.session_date, "status": d.status, "monthly_status": d.monthly_status,
                "leg": l.unique_code, "verdict": l.verdict, "selected_contract": l.selected_contract,
                "entry": l.entry, "orpt_status": l.orpt_status, "rc_status": l.rc_status, "order_time": l.order_time,
                "minimum_low": l.minimum_low, "minimum_low_time": l.minimum_low_time, "gap_points": l.gap_points,
                "gap_pct": l.gap_pct, "entry_triggered": l.entry_triggered,
            })

    md = ["# S21 Historical Certification", "", "## Aggregate", ""]
    for k, v in summary.items():
        if k != "by_strategy_leg":
            md.append(f"- **{k}**: {v}")
    md += ["", "## By strategy leg", ""]
    for code, stats in summary["by_strategy_leg"].items():
        md.append(f"- **{code}**: selected={stats['selected']}, triggered={stats['triggered']}")
    (output_root / "summary.md").write_text("\n".join(md), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-date", required=True)
    ap.add_argument("--end-date", required=True)
    ap.add_argument("--certification-root", type=Path, default=DEFAULT_CERT_ROOT)
    ap.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    ap.add_argument("--option-root", type=Path, default=DEFAULT_OPTION_ROOT)
    ap.add_argument("--replay-root", type=Path, default=DEFAULT_REPLAY_ROOT)
    ap.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    ap.add_argument("--max-days", type=int, default=0)
    args = ap.parse_args()

    dates = list(weekdays(date.fromisoformat(args.start_date), date.fromisoformat(args.end_date)))
    if args.max_days > 0:
        dates = dates[:args.max_days]

    results = []
    for i, d in enumerate(dates, 1):
        print(f"\n{'='*100}\n[{i}/{len(dates)}] CERTIFY {d.isoformat()}\n{'='*100}")
        result = certify_day(d, args)
        results.append(result)
        write_reports(results, args.output_root)
        print(f"DAY RESULT {result.session_date}: status={result.status} monthly={result.monthly_status} "
              f"triggered={result.any_entry_triggered} rc={result.rc_required} error={result.error}")

    print("\nS21 HISTORICAL CERTIFICATION COMPLETE")
    print(json.dumps(aggregate(results), indent=2))
    print(f"Reports: {args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
