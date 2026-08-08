from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
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


@dataclass(frozen=True)
class FillCertification:
    session_date: str
    strategy_leg: str
    selected_contract: str
    planned_entry: float
    order_time: str
    watch_cutoff_time: str
    result: str
    first_trigger_bar_start: str | None
    first_trigger_bar_end: str | None
    first_trigger_bar_low: float | None
    certified_fill_price: float | None
    bar_count_checked: int
    rule: str


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Certify whether S21 waiting SELL orders would actually fill, using "
            "the same bar trigger semantics as PaperOrderStateStore: bar.low <= planned_entry."
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
        help="Current supervisor default and watch cutoff, HH:MM.",
    )
    parser.add_argument(
        "--output",
        default="reports/s21_entry_fill_certification/summary.json",
    )
    args = parser.parse_args()

    cutoff = time.fromisoformat(args.watch_cutoff)
    adapter = _build_adapter(args.config)
    results: list[FillCertification] = []

    try:
        for raw_date in args.dates:
            session_date = date.fromisoformat(raw_date)
            replay_path = (
                Path(args.replay_root) / raw_date / "s21_replay.json"
            )
            replay = _load_replay(replay_path)

            for leg in replay.get("legs", []):
                if leg.get("verdict") != "NORMAL_ORDER_READY_AT_09_25":
                    continue
                symbol = leg.get("selected_contract")
                entry = leg.get("entry")
                order_time = leg.get("order_time")
                if not symbol or entry is None or order_time != "09:25":
                    continue

                bars = adapter.get_option_bars(
                    symbol,
                    session_date=session_date,
                    from_time=time(9, 25),
                    to_time=cutoff,
                    interval_minutes=1,
                )

                trigger_bar = None
                for bar in bars:
                    # Exact bar-based waiting-order trigger from PaperOrderStateStore:
                    # triggered = low is not None and low <= planned_entry_price
                    if bar.low is not None and float(bar.low) <= float(entry):
                        trigger_bar = bar
                        break

                results.append(
                    FillCertification(
                        session_date=raw_date,
                        strategy_leg=str(leg.get("unique_code")),
                        selected_contract=str(symbol),
                        planned_entry=float(entry),
                        order_time="09:25",
                        watch_cutoff_time=args.watch_cutoff,
                        result=(
                            "ENTRY_TRIGGERED"
                            if trigger_bar is not None
                            else "ENTRY_NOT_TRIGGERED_BY_CUTOFF"
                        ),
                        first_trigger_bar_start=(
                            trigger_bar.bar_start.isoformat()
                            if trigger_bar is not None
                            else None
                        ),
                        first_trigger_bar_end=(
                            trigger_bar.bar_end.isoformat()
                            if trigger_bar is not None
                            else None
                        ),
                        first_trigger_bar_low=(
                            float(trigger_bar.low)
                            if trigger_bar is not None and trigger_bar.low is not None
                            else None
                        ),
                        certified_fill_price=(
                            float(entry) if trigger_bar is not None else None
                        ),
                        bar_count_checked=len(bars),
                        rule="SELL BAR TRIGGER: low <= planned_entry; fill_price = planned_entry",
                    )
                )
    finally:
        adapter.disconnect()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps([asdict(x) for x in results], indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print()
    print("S21 ENTRY-FILL CERTIFICATION")
    print("=" * 88)
    for row in results:
        print(
            f"{row.session_date} | {row.selected_contract} | entry={row.planned_entry:.4f} "
            f"| {row.result} | trigger_start={row.first_trigger_bar_start} "
            f"| low={row.first_trigger_bar_low} | fill={row.certified_fill_price}"
        )
    print("=" * 88)
    print(f"Report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
