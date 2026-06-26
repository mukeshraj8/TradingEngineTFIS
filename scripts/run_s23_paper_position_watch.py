from __future__ import annotations

import argparse
import os
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
    S23PaperOrderState,
    S23PaperOrderStateStore,
    S23PaperOrderStatus,
    S23PaperPositionManager,
    S23PaperPositionManagerStatus,
    S23PaperPositionStateStore,
    S23PaperTradeLedgerStore,
    build_s23_paper_live_state_store_from_yaml,
    s23_live_state_owner_id,
)
from tfis.paper.live_ingress import S23LivePaperIngressConfig
from tfis.paper.models import SelectedContractBarEvent, SelectedContractQuoteEvent
from tfis.dashboard import StrategyDashboardConfig, TfisOperatorDashboardBuilder


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
    parser.add_argument("--order-dir", help="Directory containing paper_order_state.json.")
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
    parser.add_argument("--dashboard-output-root", default="tmp/operator_dashboard")
    parser.add_argument("--s23-artifact-root", default="tmp/s23_fyers_morning_supervised_decision")
    parser.add_argument(
        "--disable-dashboard-rebuild",
        action="store_true",
        help="Do not rebuild the static operator dashboard after each watch update.",
    )
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
    state_dir = (
        None
        if args.order_dir and not args.state_dir
        else _resolve_state_dir(
            state_dir=args.state_dir,
            search_roots=tuple(args.state_search_root or ()),
            default_artifact_root=Path("tmp/s23_fyers_morning_supervised_decision"),
            no_open_ok=True,
        )
    )
    order_dir = None
    order_state = None
    state = None
    if state_dir is None:
        order_dir = _resolve_order_dir(
            order_dir=args.order_dir,
            search_roots=tuple(args.state_search_root or ()),
            default_artifact_root=Path("tmp/s23_fyers_morning_supervised_decision"),
            no_open_ok=args.no_open_ok,
            session_date=session_date,
        )
        if order_dir is None:
            print("No open S23 paper position or waiting order found; nothing to watch.")
            return 0
        order_state = S23PaperOrderStateStore().load_state(order_dir)
    else:
        state = S23PaperPositionStateStore().load_state(state_dir)
    live_state_store = build_s23_paper_live_state_store_from_yaml(args.config)
    trade_id = (
        S23PaperTradeLedgerStore.trade_id_for_state(state)
        if state is not None
        else _order_id_for_state(order_state)
    )
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
    order_store = S23PaperOrderStateStore()
    expiry_governance = S23PaperExpiryGovernance(DeterministicExpiryCalendar())

    watched_symbol = (
        state.selected_contract_symbol
        if state is not None
        else order_state.selected_contract_symbol
    )
    watch_lock_handle = _acquire_watch_file_lock(Path(state_dir or order_dir))
    print("=" * 60, flush=True)
    print("TFIS S23 PAPER POSITION WATCHER", flush=True)
    print(f"Process ID       : {os.getpid()}", flush=True)
    print(f"Watching         : {'position' if state is not None else 'order'}", flush=True)
    print(f"Selected contract: {watched_symbol}", flush=True)
    print(f"State directory  : {state_dir or order_dir}", flush=True)
    print(f"Session date     : {session_date.isoformat()}", flush=True)
    print(f"Poll seconds     : {args.poll_seconds}", flush=True)
    print(f"Cutoff time      : {args.until} {timezone_name}", flush=True)
    print(
        "Dashboard rebuild: "
        + ("disabled" if args.disable_dashboard_rebuild else str(args.dashboard_output_root)),
        flush=True,
    )
    print("Status           : starting broker connection and quote watch", flush=True)
    print("=" * 60, flush=True)

    iterations = 0
    try:
        if (
            state is None
            and order_state is not None
            and order_dir is not None
            and order_state.status is S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER
            and order_state.entry_date < session_date
        ):
            evaluated_at = datetime.now(timezone)
            order_state, order_event, _order_state_path, _order_events_path = order_store.mark_not_filled(
                order_dir,
                marked_at=evaluated_at,
                reason_code="paper_order_expired_untriggered_previous_session",
                message=(
                    "Pending S23 paper entry orders are session-only. This order "
                    "did not trigger on its entry date, so it was cancelled instead "
                    "of being carried forward."
                ),
            )
            print(
                f"{evaluated_at.isoformat()} {order_state.status.value} "
                f"{order_event.reason_code} fill={order_state.fill_price}",
                flush=True,
            )
            if not args.disable_dashboard_rebuild:
                _rebuild_dashboard(
                    output_root=Path(args.dashboard_output_root),
                    artifact_root=Path(args.s23_artifact_root),
                )
            return 0
        prepare_fyers_env_from_tfis(tfis_root=args.tfis_root, skip_refresh=args.skip_refresh)
        adapter.connect()
        adapter.subscribe_symbols((watched_symbol,))
        while True:
            iterations += 1
            evaluated_at = datetime.now(timezone)
            try:
                events = _fetch_selected_contract_events(
                    adapter=adapter,
                    selected_contract_symbol=watched_symbol,
                    session_date=session_date,
                )
            except BrokerAdapterError as exc:
                print(
                    f"{evaluated_at.isoformat()} WARNING quote_fetch_failed "
                    f"{exc}; keeping watcher alive",
                    flush=True,
                )
                events = ()
            if state is None:
                assert order_dir is not None
                order_state, order_event, _order_state_path, _order_events_path = order_store.evaluate_waiting_order(
                    order_dir,
                    market_events=events,
                    evaluated_at=evaluated_at,
                )
                print(
                    f"{evaluated_at.isoformat()} {order_state.status.value} "
                    f"{order_event.reason_code} fill={order_state.fill_price}",
                    flush=True,
                )
                if not args.disable_dashboard_rebuild:
                    _rebuild_dashboard(
                        output_root=Path(args.dashboard_output_root),
                        artifact_root=Path(args.s23_artifact_root),
                    )
                live_state_store.set_watch_heartbeat(
                    session_date=session_date,
                    trade_id=trade_id,
                    payload={
                        "trade_id": trade_id,
                        "owner_id": owner_id,
                        "timestamp": evaluated_at.isoformat(),
                        "status": order_state.status.value,
                        "selected_contract_symbol": order_state.selected_contract_symbol,
                        "state_directory": str(order_dir),
                    },
                )
                live_state_store.acquire_trade_lock(
                    trade_id=trade_id,
                    owner_id=owner_id,
                    ttl_seconds=lock_ttl_seconds,
                )
                if order_state.status is not S23PaperOrderStatus.PAPER_ORDER_FILLED:
                    if args.once:
                        return 0
                    if args.max_iterations and iterations >= args.max_iterations:
                        return 0
                    if evaluated_at.timetz().replace(tzinfo=None) >= until_time:
                        order_state, order_event, _order_state_path, _order_events_path = order_store.mark_not_filled(
                            order_dir,
                            marked_at=evaluated_at,
                            reason_code="paper_order_not_triggered_by_watch_cutoff",
                            message=(
                                "Selected option premium did not reach entry before "
                                "the paper watch cutoff, so the pending S23 paper order was not filled."
                            ),
                        )
                        print(
                            f"{evaluated_at.isoformat()} {order_state.status.value} "
                            f"{order_event.reason_code} fill={order_state.fill_price}",
                            flush=True,
                        )
                        if not args.disable_dashboard_rebuild:
                            _rebuild_dashboard(
                                output_root=Path(args.dashboard_output_root),
                                artifact_root=Path(args.s23_artifact_root),
                            )
                        return 0
                    time_module.sleep(max(1.0, args.poll_seconds))
                    continue
                opened = manager.open_from_filled_order(
                    order_dir,
                    order_state=order_state,
                    provenance_source_ids=("paper_order_state.json", "s23_paper_position_watch"),
                )
                state = opened.state
                state_dir = order_dir
                trade_id = S23PaperTradeLedgerStore.trade_id_for_state(state)
                watched_symbol = state.selected_contract_symbol
                print(
                    f"{evaluated_at.isoformat()} {opened.status.value} "
                    f"{opened.event.reason_code} entry={state.entry_price}",
                    flush=True,
                )

            assert state_dir is not None
            assert state is not None
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
                f"{result.event.reason_code} exit={result.event.exit_price}",
                flush=True,
            )
            if not args.disable_dashboard_rebuild:
                _rebuild_dashboard(
                    output_root=Path(args.dashboard_output_root),
                    artifact_root=Path(args.s23_artifact_root),
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
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        try:
            adapter.disconnect()
        except Exception:
            pass
        _release_watch_file_lock(watch_lock_handle)
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
    except (AttributeError, BrokerAdapterError):
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


def _rebuild_dashboard(*, output_root: Path, artifact_root: Path) -> None:
    resolved_output_root = REPO_ROOT / output_root
    lock_handle = _acquire_dashboard_build_lock(resolved_output_root)
    try:
        TfisOperatorDashboardBuilder(
            strategy_configs=(
                StrategyDashboardConfig(
                    strategy_code="S23",
                    display_name="S23 Operator Dashboard",
                    artifact_root=REPO_ROOT / artifact_root,
                    strategy_path=(
                        REPO_ROOT
                        / "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL"
                    ),
                    reference_packet_path=(
                        REPO_ROOT
                        / "config/reference_packets/s23_bear_put_live_decision_reference.json"
                    ),
                    session_id_prefix="s23-fyers-morning-supervised-decision",
                ),
            )
        ).build(output_root=resolved_output_root)
    finally:
        _release_watch_file_lock(lock_handle)


def _acquire_dashboard_build_lock(output_root: Path):
    lock_path = output_root / ".operator_dashboard_build.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()}\n")
        handle.flush()
        return handle
    except OSError:
        handle.close()
        raise


def _resolve_order_dir(
    *,
    order_dir: str | None,
    search_roots: tuple[str, ...],
    default_artifact_root: Path,
    no_open_ok: bool,
    session_date: date,
) -> Path | None:
    if order_dir:
        return Path(order_dir)
    roots = tuple(Path(item) for item in search_roots) or (default_artifact_root,)
    candidates: list[tuple[datetime, Path]] = []
    store = S23PaperOrderStateStore()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("paper_order_state.json"):
            try:
                state = store.load_state(path.parent)
            except Exception:
                continue
            if (
                state.status is S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER
                and state.entry_date == session_date
            ):
                candidates.append((state.last_updated_timestamp, path.parent))
    if candidates:
        return sorted(candidates, key=lambda item: item[0])[-1][1]
    if no_open_ok:
        return None
    searched = ", ".join(str(root) for root in roots)
    raise RuntimeError(
        "No waiting S23 paper order state was found. Searched: " + searched
    )


def _acquire_watch_file_lock(state_directory: Path):
    lock_path = state_directory / ".s23_paper_watch.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()}\n")
        handle.flush()
        return handle
    except OSError as exc:
        handle.close()
        raise RuntimeError(
            f"Another S23 paper watcher already holds {lock_path}."
        ) from exc


def _release_watch_file_lock(handle) -> None:
    if handle is None:
        return
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _order_id_for_state(state: S23PaperOrderState | None) -> str:
    if state is None:
        return "unknown-order"
    timestamp = state.order_timestamp.strftime("%Y%m%dT%H%M%S")
    return (
        f"{state.strategy_code}-{state.strategy_branch}-"
        f"{state.selected_contract_symbol}-ORDER-{timestamp}"
    )


def _parse_hhmm(value: str) -> time:
    try:
        hour_text, minute_text = value.split(":", 1)
        return time(int(hour_text), int(minute_text))
    except Exception as exc:
        raise argparse.ArgumentTypeError("--until must be HH:MM") from exc


if __name__ == "__main__":
    raise SystemExit(main())
