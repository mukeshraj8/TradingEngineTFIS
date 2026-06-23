from __future__ import annotations

import argparse
import sys
import time as time_module
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.brokers import BrokerAdapterError, FyersBrokerAdapter
from tfis.brokers.fyers_token import prepare_fyers_env_from_tfis
from tfis.paper import (
    DeterministicExpiryCalendar,
    S23OpenPaperPositionDiscovery,
    S23PaperExpiryGovernance,
    S23PaperPositionManager,
    S23PaperPositionManagerStatus,
    S23PaperPositionStateStore,
    S23PaperTradeLedgerStore,
    build_s23_paper_live_state_store_from_yaml,
    s23_live_state_owner_id,
)
from tfis.paper.live_ingress import S23LivePaperIngressConfig
from tfis.paper.models import SelectedContractBarEvent, SelectedContractQuoteEvent


DEFAULT_CONFIG = REPO_ROOT / "config" / "paper.s23.fyers_connect_test.yaml"
TERMINAL_STATUSES = {
    S23PaperPositionManagerStatus.PAPER_POSITION_TARGET_HIT,
    S23PaperPositionManagerStatus.PAPER_POSITION_STOPLOSS_HIT,
    S23PaperPositionManagerStatus.PAPER_POSITION_FORCE_CLOSED,
    S23PaperPositionManagerStatus.PAPER_POSITION_ROLLOVER_REQUIRED,
    S23PaperPositionManagerStatus.PAPER_POSITION_REVERSE_ENTRY_REQUIRED,
    S23PaperPositionManagerStatus.PAPER_POSITION_FRESH_ENTRY_REQUIRED,
    S23PaperPositionManagerStatus.PAPER_POSITION_ALREADY_CLOSED,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Resume a persisted S23 paper position and watch selected-contract "
            "FYERS prices for target, stoploss/FSL, expiry rollover, and reverse-entry triggers."
        )
    )
    parser.add_argument("--tfis-root", default=str(REPO_ROOT))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--state-dir", help="Directory containing paper_position_state.json.")
    parser.add_argument(
        "--state-search-root",
        action="append",
        default=None,
        help=(
            "Artifact root to scan for an open paper_position_state.json when --state-dir "
            "is omitted. Repeatable."
        ),
    )
    parser.add_argument("--session-date", help="YYYY-MM-DD. Defaults to current date in broker timezone.")
    parser.add_argument("--timezone", default=None, help="Defaults to broker.timezone from config.")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--max-iterations", type=int, default=0, help="0 means run until --until.")
    parser.add_argument("--until", default="15:30", help="Local HH:MM cutoff for the watch loop.")
    parser.add_argument("--skip-refresh", action="store_true")
    parser.add_argument("--allow-reverse-on-stoploss", action="store_true", default=True)
    parser.add_argument("--once", action="store_true", help="Fetch/process one batch and exit.")
    parser.add_argument(
        "--no-open-ok",
        action="store_true",
        help="Exit successfully when discovery finds no open paper position.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = S23LivePaperIngressConfig.from_yaml(args.config)
    timezone_name = args.timezone or config.broker.timezone
    timezone = ZoneInfo(timezone_name)
    session_date = (
        date.fromisoformat(args.session_date)
        if args.session_date
        else datetime.now(timezone).date()
    )
    until_time = _parse_hhmm(args.until)
    state_dir = _resolve_state_dir(
        state_dir=args.state_dir,
        search_roots=tuple(args.state_search_root or ()),
        default_artifact_root=Path("tmp/s23_fyers_morning_supervised_decision"),
        no_open_ok=args.no_open_ok,
    )
    if state_dir is None:
        print("No open S23 paper position state found; nothing to watch.")
        return 0
    state = S23PaperPositionStateStore().load_state(state_dir)
    live_state_store = build_s23_paper_live_state_store_from_yaml(args.config)
    trade_id = S23PaperTradeLedgerStore.trade_id_for_state(state)
    owner_id = s23_live_state_owner_id()
    lock_ttl_seconds = max(30, int(args.poll_seconds * 6))
    if not live_state_store.acquire_trade_lock(
        trade_id=trade_id,
        owner_id=owner_id,
        ttl_seconds=lock_ttl_seconds,
    ):
        raise RuntimeError(f"Another S23 paper watcher already owns {trade_id}.")

    adapter = FyersBrokerAdapter(source_timezone=timezone_name)
    manager = S23PaperPositionManager(
        live_state_store=live_state_store,
        slippage_exit_points=config.costs.slippage_exit_points or 0.0,
    )
    expiry_governance = S23PaperExpiryGovernance(DeterministicExpiryCalendar())

    print(f"Watching S23 paper position: {state.selected_contract_symbol}")
    print(f"State directory: {state_dir}")
    print(f"Session date: {session_date.isoformat()}")

    iterations = 0
    try:
        prepare_fyers_env_from_tfis(tfis_root=args.tfis_root, skip_refresh=args.skip_refresh)
        adapter.connect()
        adapter.subscribe_symbols((state.selected_contract_symbol,))
        while True:
            iterations += 1
            evaluated_at = datetime.now(timezone)
            events = _fetch_selected_contract_events(
                adapter=adapter,
                selected_contract_symbol=state.selected_contract_symbol,
                session_date=session_date,
            )
            result = manager.process_session(
                state_dir,
                session_date=session_date,
                market_events=events,
                evaluated_at=evaluated_at,
                expiry_governance=expiry_governance,
                allow_reverse_on_stoploss=args.allow_reverse_on_stoploss,
                provenance_source_ids=("s23_paper_position_watch",),
            )
            live_state_store.set_watch_heartbeat(
                session_date=session_date,
                trade_id=trade_id,
                payload={
                    "trade_id": trade_id,
                    "owner_id": owner_id,
                    "timestamp": evaluated_at.isoformat(),
                    "status": result.status.value,
                    "selected_contract_symbol": state.selected_contract_symbol,
                    "state_directory": str(state_dir),
                },
            )
            live_state_store.acquire_trade_lock(
                trade_id=trade_id,
                owner_id=owner_id,
                ttl_seconds=lock_ttl_seconds,
            )
            print(
                f"{evaluated_at.isoformat()} {result.status.value} "
                f"{result.event.reason_code} exit={result.event.exit_price}"
            )
            if result.status in TERMINAL_STATUSES:
                return 0
            if args.once:
                return 0
            if args.max_iterations and iterations >= args.max_iterations:
                return 0
            if evaluated_at.timetz().replace(tzinfo=None) >= until_time:
                return 0
            time_module.sleep(max(1.0, args.poll_seconds))
    except (BrokerAdapterError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            adapter.disconnect()
        except Exception:
            pass
        live_state_store.release_trade_lock(trade_id=trade_id, owner_id=owner_id)


def _fetch_selected_contract_events(
    *,
    adapter: FyersBrokerAdapter,
    selected_contract_symbol: str,
    session_date: date,
) -> tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...]:
    events: list[SelectedContractQuoteEvent | SelectedContractBarEvent] = []
    try:
        stream_events = adapter.stream_ticks()
        for event in stream_events:
            if isinstance(event, SelectedContractQuoteEvent | SelectedContractBarEvent):
                if event.symbol == selected_contract_symbol:
                    events.append(event)
    except BrokerAdapterError:
        pass
    if events:
        return tuple(events)
    return (
        adapter.get_option_quote(
            selected_contract_symbol,
            session_date=session_date,
        ),
    )


def _resolve_state_dir(
    *,
    state_dir: str | None,
    search_roots: tuple[str, ...],
    default_artifact_root: Path,
    no_open_ok: bool,
) -> Path | None:
    if state_dir:
        return Path(state_dir)
    roots = tuple(Path(item) for item in search_roots) or (default_artifact_root,)
    candidate = S23OpenPaperPositionDiscovery().find_latest_open_position(roots)
    if candidate is None:
        if no_open_ok:
            return None
        searched = ", ".join(str(root) for root in roots)
        raise RuntimeError(
            "No open S23 paper position state was found. Searched: " + searched
        )
    return candidate.state_directory


def _parse_hhmm(value: str) -> time:
    try:
        hour_text, minute_text = value.split(":", 1)
        return time(int(hour_text), int(minute_text))
    except Exception as exc:
        raise argparse.ArgumentTypeError("--until must be HH:MM") from exc


if __name__ == "__main__":
    raise SystemExit(main())
