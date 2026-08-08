from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date, time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.brokers.fyers_token import prepare_fyers_env_from_tfis
from tfis.paper.live_ingress import PaperLiveIngressConfig
from tfis.paper.lifecycle_runtime_config import (
    PaperLifecycleBrokerConfig,
    build_paper_broker_adapter_from_broker_config,
)
from tfis.rules import get_s21_leg_rule


@dataclass(frozen=True)
class EntryDistanceAudit:
    session_date: str
    strategy_leg: str
    selected_contract: str
    planned_entry: float
    order_time: str
    watch_cutoff_time: str
    historical_reference_alias: str
    historical_reference_value: float | None
    derived_entry_discount_pct: float | None
    first_bar_start: str | None
    first_bar_open: float | None
    first_bar_high: float | None
    first_bar_low: float | None
    first_bar_close: float | None
    minimum_low: float | None
    minimum_low_bar_start: str | None
    maximum_high: float | None
    maximum_high_bar_start: str | None
    entry_triggered: bool
    first_trigger_bar_start: str | None
    first_trigger_bar_low: float | None
    certified_fill_price: float | None
    min_low_minus_entry: float | None
    min_low_minus_entry_pct_of_entry: float | None
    entry_minus_min_low: float | None
    entry_minus_min_low_pct_of_entry: float | None
    bar_count_checked: int
    trigger_rule: str
    interpretation: str


def _load_replay(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing replay result: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _build_adapter(config_path: str):
    prepare_fyers_env_from_tfis(tfis_root=REPO_ROOT, skip_refresh=False)
    config = PaperLiveIngressConfig.from_yaml(config_path)
    adapter = build_paper_broker_adapter_from_broker_config(
        PaperLifecycleBrokerConfig(
            provider=config.broker.provider,
            timezone=config.broker.timezone,
            payload_fixture_path=config.broker.payload_fixture_path,
            capture_stream_events=config.broker.capture_stream_events,
            option_chain_strike_count=config.broker.option_chain_strike_count,
        )
    )
    adapter.connect()
    return adapter


def _safe_float(value):
    return None if value is None else float(value)



def _safe_symbol_dir(symbol: str) -> str:
    base = re.sub(r'[^A-Za-z0-9._-]+', '_', symbol).strip("._")
    digest = hashlib.sha1(symbol.encode("utf-8")).hexdigest()[:10]
    return f"{base[:100]}__{digest}"


class _CachedBar:
    def __init__(self, payload: dict):
        from datetime import datetime
        self.bar_start = datetime.fromisoformat(str(payload["bar_start"]))
        self.bar_end = self.bar_start + __import__("datetime").timedelta(minutes=1)
        self.open = payload.get("open")
        self.high = payload.get("high")
        self.low = payload.get("low")
        self.close = payload.get("close")


def _load_cached_minute_bars(
    *,
    option_evidence_root: Path,
    session_date: date,
    symbol: str,
    from_time: time,
    to_time: time,
):
    path = (
        option_evidence_root
        / session_date.isoformat()
        / _safe_symbol_dir(symbol)
        / "minute_bars.json"
    )
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if payload.get("symbol") != symbol or payload.get("session_date") != session_date.isoformat():
        return None

    requested_from = payload.get("requested_from")
    requested_to = payload.get("requested_to")
    if requested_from and requested_to:
        try:
            if time.fromisoformat(str(requested_from)) > from_time:
                return None
            if time.fromisoformat(str(requested_to)) < to_time:
                return None
        except ValueError:
            return None
    else:
        # Older 09:24-09:30 caches are intentionally not treated as complete
        # fill-certification data.
        return None

    rows = []
    for row in payload.get("bars", []):
        if not isinstance(row, dict) or not row.get("bar_start"):
            continue
        bar = _CachedBar(row)
        t = bar.bar_start.timetz().replace(tzinfo=None)
        if from_time <= t < to_time:
            rows.append(bar)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit how close each corrected S21 09:25 waiting SELL entry came to filling. "
            "Uses PaperOrderStateStore bar semantics: bar.low <= planned_entry."
        )
    )
    parser.add_argument(
        "--dates",
        nargs="+",
        required=True,
        help="ISO dates, e.g. 2026-08-04 2026-08-05",
    )
    parser.add_argument(
        "--replay-root",
        default="reports/s21_pure_replay",
    )
    parser.add_argument(
        "--config",
        default="config/paper.s21.fyers_connect_test.yaml",
    )
    parser.add_argument(
        "--watch-cutoff",
        default="15:30",
    )
    parser.add_argument(
        "--option-evidence-root",
        default="reports/s21_replay_option_evidence",
        help="Use cached selected-contract minute bars from this root before broker access.",
    )
    parser.add_argument(
        "--offline-only",
        action="store_true",
        help="Fail instead of calling FYERS when the required full-session minute cache is absent.",
    )
    parser.add_argument(
        "--output",
        default="reports/s21_entry_distance_certification/summary.json",
    )
    parser.add_argument(
        "--markdown-output",
        default="reports/s21_entry_distance_certification/summary.md",
    )
    args = parser.parse_args()

    cutoff = time.fromisoformat(args.watch_cutoff)
    adapter = None
    results: list[EntryDistanceAudit] = []

    try:
        for raw_date in args.dates:
            session_date = date.fromisoformat(raw_date)
            replay = _load_replay(
                Path(args.replay_root) / raw_date / "s21_replay.json"
            )

            for leg in replay.get("legs", []):
                if leg.get("verdict") != "NORMAL_ORDER_READY_AT_09_25":
                    continue

                symbol = leg.get("selected_contract")
                entry = leg.get("entry")
                order_time = leg.get("order_time")
                unique_code = str(leg.get("unique_code") or "")
                if not symbol or entry is None or order_time != "09:25":
                    continue

                entry = float(entry)
                rule = get_s21_leg_rule(unique_code)
                ref_alias = rule.entry_reference_alias
                refs = leg.get("selected_option_references") or {}
                ref_value = _safe_float(refs.get(ref_alias))
                derived_discount = (
                    (1.0 - entry / ref_value) * 100.0
                    if ref_value not in (None, 0.0)
                    else None
                )

                bars = _load_cached_minute_bars(
                    option_evidence_root=REPO_ROOT / args.option_evidence_root,
                    session_date=session_date,
                    symbol=str(symbol),
                    from_time=time(9, 25),
                    to_time=cutoff,
                )
                if bars is None:
                    if args.offline_only:
                        raise RuntimeError(
                            f"Missing cached full-session minute evidence for {raw_date} {symbol}"
                        )
                    if adapter is None:
                        adapter = _build_adapter(args.config)
                    bars = adapter.get_option_bars(
                        symbol,
                        session_date=session_date,
                        from_time=time(9, 25),
                        to_time=cutoff,
                        interval_minutes=1,
                    )

                first_bar = bars[0] if bars else None

                min_bar = None
                max_bar = None
                trigger_bar = None
                for bar in bars:
                    if bar.low is not None:
                        if min_bar is None or float(bar.low) < float(min_bar.low):
                            min_bar = bar
                        if trigger_bar is None and float(bar.low) <= entry:
                            trigger_bar = bar
                    if bar.high is not None:
                        if max_bar is None or float(bar.high) > float(max_bar.high):
                            max_bar = bar

                min_low = _safe_float(min_bar.low) if min_bar is not None else None
                max_high = _safe_float(max_bar.high) if max_bar is not None else None
                min_low_minus_entry = (
                    min_low - entry if min_low is not None else None
                )
                entry_minus_min_low = (
                    entry - min_low if min_low is not None else None
                )

                if min_low is None:
                    interpretation = "NO_INTRADAY_BARS"
                elif trigger_bar is not None:
                    interpretation = "ENTRY_WAS_REACHED"
                else:
                    gap_pct = ((min_low - entry) / entry) * 100.0
                    if gap_pct <= 1.0:
                        interpretation = "VERY_CLOSE_BUT_NOT_REACHED"
                    elif gap_pct <= 5.0:
                        interpretation = "MODERATELY_ABOVE_ENTRY"
                    else:
                        interpretation = "ENTRY_FAR_BELOW_OBSERVED_MARKET"

                results.append(
                    EntryDistanceAudit(
                        session_date=raw_date,
                        strategy_leg=unique_code,
                        selected_contract=str(symbol),
                        planned_entry=entry,
                        order_time="09:25",
                        watch_cutoff_time=args.watch_cutoff,
                        historical_reference_alias=ref_alias,
                        historical_reference_value=ref_value,
                        derived_entry_discount_pct=derived_discount,
                        first_bar_start=(
                            first_bar.bar_start.isoformat()
                            if first_bar is not None
                            else None
                        ),
                        first_bar_open=_safe_float(first_bar.open) if first_bar else None,
                        first_bar_high=_safe_float(first_bar.high) if first_bar else None,
                        first_bar_low=_safe_float(first_bar.low) if first_bar else None,
                        first_bar_close=_safe_float(first_bar.close) if first_bar else None,
                        minimum_low=min_low,
                        minimum_low_bar_start=(
                            min_bar.bar_start.isoformat()
                            if min_bar is not None
                            else None
                        ),
                        maximum_high=max_high,
                        maximum_high_bar_start=(
                            max_bar.bar_start.isoformat()
                            if max_bar is not None
                            else None
                        ),
                        entry_triggered=trigger_bar is not None,
                        first_trigger_bar_start=(
                            trigger_bar.bar_start.isoformat()
                            if trigger_bar is not None
                            else None
                        ),
                        first_trigger_bar_low=(
                            _safe_float(trigger_bar.low)
                            if trigger_bar is not None
                            else None
                        ),
                        certified_fill_price=(
                            entry if trigger_bar is not None else None
                        ),
                        min_low_minus_entry=min_low_minus_entry,
                        min_low_minus_entry_pct_of_entry=(
                            (min_low_minus_entry / entry) * 100.0
                            if min_low_minus_entry is not None and entry != 0
                            else None
                        ),
                        entry_minus_min_low=entry_minus_min_low,
                        entry_minus_min_low_pct_of_entry=(
                            (entry_minus_min_low / entry) * 100.0
                            if entry_minus_min_low is not None and entry != 0
                            else None
                        ),
                        bar_count_checked=len(bars),
                        trigger_rule="SELL BAR TRIGGER: low <= planned_entry",
                        interpretation=interpretation,
                    )
                )
    finally:
        if adapter is not None:
            adapter.disconnect()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps([asdict(row) for row in results], indent=2, sort_keys=True),
        encoding="utf-8",
    )

    md = Path(args.markdown_output)
    md.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# S21 Entry Distance Certification",
        "",
        "| Date | Contract | Entry | 09:25 Low | Min Low | Min Time | Min-Entry | Gap % | Triggered | Interpretation |",
        "|---|---|---:|---:|---:|---|---:|---:|---|---|",
    ]
    for row in results:
        lines.append(
            f"| {row.session_date} | `{row.selected_contract}` | "
            f"{row.planned_entry:.4f} | "
            f"{row.first_bar_low if row.first_bar_low is not None else 'n/a'} | "
            f"{row.minimum_low if row.minimum_low is not None else 'n/a'} | "
            f"{row.minimum_low_bar_start or 'n/a'} | "
            f"{row.min_low_minus_entry if row.min_low_minus_entry is not None else 'n/a'} | "
            f"{row.min_low_minus_entry_pct_of_entry if row.min_low_minus_entry_pct_of_entry is not None else 'n/a'} | "
            f"{'YES' if row.entry_triggered else 'NO'} | {row.interpretation} |"
        )
    lines += [
        "",
        "## Formula trace",
        "",
    ]
    for row in results:
        lines += [
            f"### {row.session_date} — {row.selected_contract}",
            f"- Historical entry reference: `{row.historical_reference_alias} = {row.historical_reference_value}`",
            f"- Planned entry: `{row.planned_entry}`",
            f"- Derived discount from reference: `{row.derived_entry_discount_pct}%`",
            f"- Minimum observed low after 09:25: `{row.minimum_low}` at `{row.minimum_low_bar_start}`",
            f"- Trigger rule: `{row.trigger_rule}`",
            f"- Result: **{'ENTRY_TRIGGERED' if row.entry_triggered else 'ENTRY_NOT_TRIGGERED'}**",
            "",
        ]
    md.write_text("\n".join(lines), encoding="utf-8")

    print()
    print("S21 ENTRY DISTANCE CERTIFICATION")
    print("=" * 120)
    for row in results:
        print(
            f"{row.session_date} | {row.selected_contract} | "
            f"entry={row.planned_entry:.4f} | "
            f"09:25_low={row.first_bar_low} | "
            f"min_low={row.minimum_low} @ {row.minimum_low_bar_start} | "
            f"min-entry={row.min_low_minus_entry} | "
            f"gap%={row.min_low_minus_entry_pct_of_entry} | "
            f"triggered={row.entry_triggered} | "
            f"{row.interpretation}"
        )
    print("=" * 120)
    print(f"JSON: {out}")
    print(f"Markdown: {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
