from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import yaml

from tfis.brokers import BrokerNormalizationError
from tfis.domain import ExpiryType
from tfis.market_data import UnderlyingHistoryBar
from tfis.paper import (
    OptionChainContract,
    OptionChainSnapshotEvent,
    PaperEventType,
    S23FyersSnapshotCollector,
    S23FyersSnapshotCollectorError,
    S23NormalizedPaperEventLoader,
)


IST = ZoneInfo("Asia/Kolkata")
BASE_EVENTS = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "paper"
    / "s23_archive_ingress_dry_run.jsonl"
)


def _ts(day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 5, day, hour, minute, second, tzinfo=IST)


class _CountingFakeBrokerAdapter:
    broker_name = "fake"

    def __init__(
        self,
        *,
        underlying=None,
        underlying_bars=None,
        daily_bars=None,
        option_chain=None,
        option_chain_by_expiry: dict[date, OptionChainSnapshotEvent] | None = None,
        preserve_contract_symbols_for_expiries: set[date] | None = None,
        return_first_expiry_symbols_on_second_chain_call: bool = False,
        underlying_quote_failures: tuple[Exception, ...] = (),
        option_chain_failures: tuple[Exception, ...] = (),
    ) -> None:
        loader = S23NormalizedPaperEventLoader()
        events = loader.load_jsonl(BASE_EVENTS)
        self._underlying = underlying or next(
            event for event in events if event.envelope.event_type is PaperEventType.UNDERLYING_QUOTE
        )
        self._underlying_bars = underlying_bars or (
            UnderlyingHistoryBar(
                symbol="NIFTY",
                bar_start=_ts(8, 9, 14),
                bar_end=_ts(8, 9, 14, 59),
                open=22410.0,
                high=22425.0,
                low=22395.0,
                close=22420.0,
                volume=100.0,
                source_id="unit-test-bars",
            ),
            UnderlyingHistoryBar(
                symbol="NIFTY",
                bar_start=_ts(8, 9, 24),
                bar_end=_ts(8, 9, 24, 59),
                open=22420.0,
                high=22455.0,
                low=22400.0,
                close=22448.0,
                volume=120.0,
                source_id="unit-test-bars",
            ),
            UnderlyingHistoryBar(
                symbol="NIFTY",
                bar_start=_ts(8, 9, 29),
                bar_end=_ts(8, 9, 29, 59),
                open=22448.0,
                high=22462.0,
                low=22435.0,
                close=22440.0,
                volume=140.0,
                source_id="unit-test-bars",
            ),
        )
        self._chain = option_chain or next(
            event for event in events if event.envelope.event_type is PaperEventType.OPTION_CHAIN_SNAPSHOT
        )
        self._chain_by_expiry = option_chain_by_expiry or {}
        self._preserve_contract_symbols_for_expiries = preserve_contract_symbols_for_expiries or set()
        self._return_first_expiry_symbols_on_second_chain_call = (
            return_first_expiry_symbols_on_second_chain_call
        )
        self._underlying_quote_failures = list(underlying_quote_failures)
        self._option_chain_failures = list(option_chain_failures)
        self._first_requested_option_chain_expiry: date | None = None
        self._daily_bars = daily_bars or (
            UnderlyingHistoryBar(
                symbol="NIFTY",
                bar_start=_ts(2, 15, 15),
                bar_end=_ts(2, 15, 29, 59),
                open=22620.0,
                high=22680.0,
                low=22510.0,
                close=22560.0,
                volume=1000.0,
                source_id="unit-test-daily-bars",
            ),
            UnderlyingHistoryBar(
                symbol="NIFTY",
                bar_start=_ts(3, 15, 15),
                bar_end=_ts(3, 15, 29, 59),
                open=22560.0,
                high=22610.0,
                low=22420.0,
                close=22480.0,
                volume=1000.0,
                source_id="unit-test-daily-bars",
            ),
            UnderlyingHistoryBar(
                symbol="NIFTY",
                bar_start=_ts(4, 15, 15),
                bar_end=_ts(4, 15, 29, 59),
                open=22480.0,
                high=22520.0,
                low=22360.0,
                close=22410.0,
                volume=1000.0,
                source_id="unit-test-daily-bars",
            ),
            UnderlyingHistoryBar(
                symbol="NIFTY",
                bar_start=_ts(5, 15, 15),
                bar_end=_ts(5, 15, 29, 59),
                open=22410.0,
                high=22480.0,
                low=22310.0,
                close=22390.0,
                volume=1000.0,
                source_id="unit-test-daily-bars",
            ),
            UnderlyingHistoryBar(
                symbol="NIFTY",
                bar_start=_ts(6, 15, 15),
                bar_end=_ts(6, 15, 29, 59),
                open=22390.0,
                high=22430.0,
                low=22290.0,
                close=22340.0,
                volume=1000.0,
                source_id="unit-test-daily-bars",
            ),
            UnderlyingHistoryBar(
                symbol="NIFTY",
                bar_start=_ts(8, 9, 15),
                bar_end=_ts(8, 15, 29, 59),
                open=22410.0,
                high=22462.0,
                low=22395.0,
                close=22440.0,
                volume=1000.0,
                source_id="unit-test-daily-bars",
            ),
        )
        self.connected = False
        self.get_underlying_quote_calls = 0
        self.get_underlying_bars_calls = 0
        self.get_underlying_daily_bars_calls = 0
        self.get_option_chain_calls = 0
        self.requested_option_chain_expiries: list[date] = []
        self.get_option_quote_calls = 0
        self.stream_ticks_calls = 0
        self.order_api_calls = 0

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def subscribe_symbols(self, symbols: tuple[str, ...]) -> tuple[str, ...]:
        return symbols

    def get_underlying_quote(self, symbol: str, *, session_date: date):
        self.get_underlying_quote_calls += 1
        if self._underlying_quote_failures:
            raise self._underlying_quote_failures.pop(0)
        return self._underlying

    def get_underlying_bars(
        self,
        symbol: str,
        *,
        session_date: date,
        from_time,
        to_time,
        interval_minutes: int = 1,
    ):
        self.get_underlying_bars_calls += 1
        return self._underlying_bars

    def get_underlying_daily_bars(
        self,
        symbol: str,
        *,
        session_date: date,
        lookback_days: int = 90,
    ):
        self.get_underlying_daily_bars_calls += 1
        return self._daily_bars

    def get_option_chain(self, symbol: str, expiry: date, *, session_date: date):
        self.get_option_chain_calls += 1
        self.requested_option_chain_expiries.append(expiry)
        if self._option_chain_failures:
            raise self._option_chain_failures.pop(0)
        if self._first_requested_option_chain_expiry is None:
            self._first_requested_option_chain_expiry = expiry
        source_chain = self._chain_by_expiry.get(expiry, self._chain)
        expiry_token = expiry.isoformat().replace("-", "")
        if (
            self._return_first_expiry_symbols_on_second_chain_call
            and self.get_option_chain_calls == 2
            and self._first_requested_option_chain_expiry is not None
        ):
            expiry_token = self._first_requested_option_chain_expiry.isoformat().replace("-", "")
        contracts = tuple(
            replace(contract, expiry=expiry)
            for contract in source_chain.contracts
        )
        if expiry not in self._preserve_contract_symbols_for_expiries:
            contracts = tuple(
                replace(
                    contract,
                    symbol=_with_expiry_token(contract.symbol, expiry_token),
                    expiry=expiry,
                )
                for contract in source_chain.contracts
            )
        return replace(
            source_chain,
            expiry=expiry,
            contracts=contracts,
        )

    def get_option_quote(self, option_symbol: str, *, session_date: date):
        self.get_option_quote_calls += 1
        raise AssertionError("get_option_quote() must not be called in snapshot preflight")

    def stream_ticks(self):
        self.stream_ticks_calls += 1
        raise AssertionError("stream_ticks() must not be called in snapshot preflight")

    def health(self):
        return {
            "broker_name": self.broker_name,
            "as_of": _ts(8, 9, 30, 2),
            "is_connected": self.connected,
        }

    def reconnect(self):
        self.connect()
        return self.health()

    def place_order(self, *args: object, **kwargs: object) -> None:
        self.order_api_calls += 1
        raise AssertionError("place_order() must not be called in snapshot preflight")

    def modify_order(self, *args: object, **kwargs: object) -> None:
        self.order_api_calls += 1
        raise AssertionError("modify_order() must not be called in snapshot preflight")

    def cancel_order(self, *args: object, **kwargs: object) -> None:
        self.order_api_calls += 1
        raise AssertionError("cancel_order() must not be called in snapshot preflight")


def _with_expiry_token(symbol: str, expiry_token: str) -> str:
    parts = symbol.split("_")
    if len(parts) >= 4 and len(parts[1]) == 8 and parts[1].isdigit():
        parts[1] = expiry_token
        return "_".join(parts)
    return symbol


def _write_strategy_folder(tmp_path: Path) -> Path:
    strategy_dir = tmp_path / "strategy"
    strategy_dir.mkdir()
    (strategy_dir / "strategy.yaml").write_text(
        yaml.safe_dump(
            {
                "strategy_code": "S23",
                "unique_code": "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
                "symbol": "NIFTY",
                "segment": "OPTIONS_SELL",
                "expiry_type": "WEEKLY",
                "rollover_policy": "T_MINUS_1",
                "no_carry_past_expiry": True,
                "allowed_monthly_statuses": ["BEAR", "BEAR_CF"],
                "option_type": "PUT",
                "entry_time": "09:24:59",
                "recalculation_time": "09:29:59",
                "minimum_oi": 500,
                "carry_forward_allowed": True,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (strategy_dir / "formulas.yaml").write_text(
        yaml.safe_dump(
            {
                "start_strike_formula": "ROUND_UP(PRV_3DHH - PARAM(strike_buffer_pct)%)",
                "end_strike_formula": "ROUND_UP(PRV_3DHH) + PARAM(strike_step)",
                "ideal_premium_formula": "PRV_3DHH * PARAM(ideal_premium_pct)%",
                "minimum_premium_formula": "PRV_3DHH * PARAM(minimum_premium_pct)%",
                "entry_formula": "OPT_PRV_3DLL - PARAM(entry_discount_pct)%",
                "target_formula": "ENTRY - PARAM(target_pct)%",
                "stoploss_formula": "MIN(ENTRY + PARAM(sl_entry_pct)%, OPT_PRV_2DHH + PARAM(sl_reference_pct)%)",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (strategy_dir / "parameters.yaml").write_text(
        yaml.safe_dump(
            {
                "strike_buffer_pct": 5.0,
                "strike_step": 50.0,
                "ideal_premium_pct": 1.2,
                "minimum_premium_pct": 0.9,
                "entry_discount_pct": 7.5,
                "target_pct": 60.0,
                "sl_entry_pct": 60.0,
                "sl_reference_pct": 7.0,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return strategy_dir


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "paper.s23.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "source_mode": "broker_fyers_live_paper_ingress",
                "broker": {
                    "provider": "fyers",
                    "timezone": "Asia/Kolkata",
                    "payload_fixture_path": str(tmp_path / "unused_fixture.json"),
                    "capture_stream_events": False,
                },
                "paper": {
                    "strategy_code": "S23",
                    "symbol": "NIFTY",
                    "contract_cycle": "WEEKLY",
                    "mode": "paper",
                    "operator_id": "unit-test-operator",
                    "paper_mode_enabled": True,
                    "same_day_square_off_only": True,
                    "allow_recalculation": False,
                    "allow_current_day_fsl_trp": True,
                    "kill_switch_enabled": True,
                    "session_kill_switch_active": False,
                    "no_live_orders_allowed": True,
                },
                "market": {
                    "underlying_symbol": "NIFTY",
                    "weekly_expiry": "2026-05-12",
                    "selected_contract_symbol": "NIFTY_20260512_25000_PE",
                },
                "costs": {
                    "brokerage_per_lot": 20.0,
                    "slippage_entry_points": 1.0,
                    "slippage_exit_points": 1.0,
                    "spread_buffer_policy": "bid_ask_guard",
                    "version_label": "paper-cost-v1",
                },
                "thresholds": {
                    "max_quote_age_seconds": 5.0,
                    "max_timing_drift_seconds": 5.0,
                    "max_stale_events": 0,
                    "max_missing_chains": 0,
                    "required_selected_contract_availability_ratio": 1.0,
                    "max_no_trade_rate": 0.0,
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return config_path


def _write_runtime_fixture(tmp_path: Path) -> Path:
    payload = {
        "strategy_branch": "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        "session_date": "2026-05-08",
        "timezone": "Asia/Kolkata",
        "generated_at": "2026-05-08T09:30:03+05:30",
        "weekly_expiry": "2026-05-12",
        "monthly_status_result": {
            "status": "BEAR",
            "trigger_name": "BEAR_A_THRESHOLD",
            "threshold_value": 22100.0,
            "reversal_dominated": False,
            "notes": "fixture",
        },
        "market_levels": {
            "d2hh": 22500.0,
            "d2ll": 22300.0,
            "d3hh": 25000.0,
            "d3ll": 22200.0,
            "current_day_high": 22462.0,
            "current_day_low": 22395.0,
        },
        "runtime_values": {
            "OPT_PRV_3DLL": 216.22,
            "OPT_PRV_2DHH": 300.0,
        },
        "snapshots": [
            {
                "snapshot_label": "0915",
                "open": 22410.0,
                "high": 22425.0,
                "low": 22395.0,
                "close": 22420.0,
                "bar_start": "2026-05-08T09:14:00+05:30",
                "bar_end": "2026-05-08T09:15:00+05:30",
                "complete": True,
            },
            {
                "snapshot_label": "ORPT",
                "open": 22420.0,
                "high": 22455.0,
                "low": 22400.0,
                "close": 22448.0,
                "bar_start": "2026-05-08T09:23:59+05:30",
                "bar_end": "2026-05-08T09:24:59+05:30",
                "complete": True,
            },
            {
                "snapshot_label": "RC",
                "open": 22448.0,
                "high": 22462.0,
                "low": 22435.0,
                "close": 22440.0,
                "bar_start": "2026-05-08T09:28:59+05:30",
                "bar_end": "2026-05-08T09:29:59+05:30",
                "complete": True,
            },
        ],
        "lots": 1,
        "quantity": 100,
        "source_workbook_rule": "AB6_OS_Z186",
        "workbook_row_number": 186,
        "fsl_price": 816.35,
    }
    path = tmp_path / "runtime_fixture.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _base_chain() -> OptionChainSnapshotEvent:
    loader = S23NormalizedPaperEventLoader()
    events = loader.load_jsonl(BASE_EVENTS)
    return next(
        event for event in events if event.envelope.event_type is PaperEventType.OPTION_CHAIN_SNAPSHOT
    )


def test_successful_snapshot_collection(tmp_path: Path) -> None:
    adapter = _CountingFakeBrokerAdapter()
    collector = S23FyersSnapshotCollector(artifact_root=tmp_path / "artifacts")

    artifact_set = collector.collect_from_files(
        config_path=_write_config(tmp_path),
        strategy_path=_write_strategy_folder(tmp_path),
        session_id="snapshot-success",
        adapter=adapter,
    )

    assert artifact_set.summary.preflight_status == "READY"
    expected_expiry = artifact_set.summary.session_date
    while expected_expiry.weekday() != 1:
        expected_expiry += timedelta(days=1)
    expected_next_expiry = expected_expiry + timedelta(days=7)
    assert artifact_set.summary.weekly_expiry == expected_expiry
    assert adapter.requested_option_chain_expiries == [expected_expiry, expected_next_expiry]
    assert {
        contract.expiry
        for contract in artifact_set.collected_inputs.option_chain_snapshot.contracts
    } == {expected_expiry, expected_next_expiry}
    assert any(
        issue.code == "configured_weekly_expiry_stale"
        for issue in artifact_set.summary.issues
    )
    assert artifact_set.normalized_underlying_snapshot_path.exists()
    assert artifact_set.normalized_underlying_bars_path.exists()
    assert artifact_set.normalized_underlying_daily_bars_path.exists()
    assert artifact_set.normalized_option_chain_snapshot_path.exists()
    assert artifact_set.summary_path.exists()
    assert adapter.get_underlying_quote_calls == 1
    assert adapter.get_underlying_bars_calls == 1
    assert adapter.get_underlying_daily_bars_calls == 1
    assert adapter.get_option_chain_calls == 2
    assert adapter.get_option_quote_calls == 0
    assert adapter.stream_ticks_calls == 0
    assert adapter.order_api_calls == 0


def test_monthly_strategy_advances_stale_configured_expiry_anchor() -> None:
    collector = S23FyersSnapshotCollector()
    config = SimpleNamespace(
        market=SimpleNamespace(
            weekly_expiry=date(2026, 7, 28),
        )
    )
    strategy = SimpleNamespace(
        symbol="BANKNIFTY",
        expiry_policy=SimpleNamespace(expiry_type=ExpiryType.MONTHLY),
    )

    assert collector._resolve_configured_expiry(
        config=config,
        strategy=strategy,
        session_date=date(2026, 8, 3),
    ) == date(2026, 8, 25)


def test_snapshot_collection_retries_transient_underlying_quote_payload_error(
    tmp_path: Path,
) -> None:
    adapter = _CountingFakeBrokerAdapter(
        underlying_quote_failures=(
            BrokerNormalizationError(
                "FYERS quote payload does not contain a usable quote record."
            ),
        ),
    )
    sleeps: list[float] = []
    collector = S23FyersSnapshotCollector(
        artifact_root=tmp_path / "artifacts",
        snapshot_fetch_retry_delay_seconds=0.01,
        sleeper=sleeps.append,
    )

    artifact_set = collector.collect_from_files(
        config_path=_write_config(tmp_path),
        strategy_path=_write_strategy_folder(tmp_path),
        session_id="snapshot-quote-retry",
        adapter=adapter,
    )

    assert artifact_set.summary.preflight_status == "READY"
    assert adapter.get_underlying_quote_calls == 2
    assert sleeps == [0.01]
    assert any(
        issue.code == "broker_snapshot_retry_succeeded"
        and "underlying_quote succeeded on attempt 2" in issue.message
        for issue in artifact_set.summary.issues
    )


def test_snapshot_collection_retries_transient_option_chain_payload_error(
    tmp_path: Path,
) -> None:
    adapter = _CountingFakeBrokerAdapter(
        option_chain_failures=(
            BrokerNormalizationError(
                "FYERS option-chain payload is missing optionsChain."
            ),
        ),
    )
    collector = S23FyersSnapshotCollector(
        artifact_root=tmp_path / "artifacts",
        snapshot_fetch_retry_delay_seconds=0,
    )

    artifact_set = collector.collect_from_files(
        config_path=_write_config(tmp_path),
        strategy_path=_write_strategy_folder(tmp_path),
        session_id="snapshot-chain-retry",
        adapter=adapter,
    )

    assert artifact_set.summary.preflight_status == "READY"
    assert adapter.get_option_chain_calls == 3
    assert len(adapter.requested_option_chain_expiries) == 3
    assert (
        adapter.requested_option_chain_expiries[0]
        == adapter.requested_option_chain_expiries[1]
    )
    assert any(
        issue.code == "broker_snapshot_retry_succeeded"
        and "option_chain:" in issue.message
        and "succeeded on attempt 2" in issue.message
        for issue in artifact_set.summary.issues
    )


def test_snapshot_collection_fails_closed_after_retries_are_exhausted(
    tmp_path: Path,
) -> None:
    adapter = _CountingFakeBrokerAdapter(
        option_chain_failures=(
            BrokerNormalizationError(
                "FYERS option-chain payload is missing optionsChain."
            ),
            BrokerNormalizationError(
                "FYERS option-chain payload is missing optionsChain."
            ),
        ),
    )
    collector = S23FyersSnapshotCollector(
        artifact_root=tmp_path / "artifacts",
        snapshot_fetch_attempts=2,
        snapshot_fetch_retry_delay_seconds=0,
    )

    with pytest.raises(S23FyersSnapshotCollectorError) as exc:
        collector.collect_from_files(
            config_path=_write_config(tmp_path),
            strategy_path=_write_strategy_folder(tmp_path),
            session_id="snapshot-chain-retry-exhausted",
            adapter=adapter,
        )

    assert exc.value.code == "BROKER_SNAPSHOT_FAILED"
    assert "option_chain:" in str(exc.value)
    assert "failed after 2 attempt(s)" in str(exc.value)
    assert "missing optionsChain" in str(exc.value)
    assert adapter.get_option_chain_calls == 2
    assert adapter.get_option_quote_calls == 0
    assert adapter.stream_ticks_calls == 0
    assert adapter.order_api_calls == 0


def test_next_expiry_request_must_return_true_next_expiry_contracts(tmp_path: Path) -> None:
    near_chain = _base_chain()
    adapter = _CountingFakeBrokerAdapter(
        option_chain=near_chain,
        return_first_expiry_symbols_on_second_chain_call=True,
    )
    collector = S23FyersSnapshotCollector(artifact_root=tmp_path / "artifacts")

    with pytest.raises(S23FyersSnapshotCollectorError) as exc:
        collector.collect_from_files(
            config_path=_write_config(tmp_path),
            strategy_path=_write_strategy_folder(tmp_path),
            session_id="snapshot-next-expiry-relabel",
            adapter=adapter,
        )

    assert exc.value.code == "NEXT_WEEKLY_OPTION_CHAIN_UNAVAILABLE"
    assert str(adapter.requested_option_chain_expiries[1]) in str(exc.value)
    assert str(adapter.requested_option_chain_expiries[0]) in str(exc.value)
    assert len(adapter.requested_option_chain_expiries) == 2
    assert adapter.get_option_quote_calls == 0
    assert adapter.stream_ticks_calls == 0
    assert adapter.order_api_calls == 0


def test_missing_option_chain_fails(tmp_path: Path) -> None:
    adapter = _CountingFakeBrokerAdapter(
        option_chain=replace(_base_chain(), contracts=()),
    )
    collector = S23FyersSnapshotCollector(artifact_root=tmp_path / "artifacts")

    with pytest.raises(S23FyersSnapshotCollectorError) as exc:
        collector.collect_from_files(
            config_path=_write_config(tmp_path),
            strategy_path=_write_strategy_folder(tmp_path),
            session_id="snapshot-missing-chain",
            adapter=adapter,
        )

    assert exc.value.code == "OPTION_CHAIN_MISSING"
    assert adapter.get_option_quote_calls == 0
    assert adapter.stream_ticks_calls == 0


def test_missing_oi_fails(tmp_path: Path) -> None:
    chain = _base_chain()
    mutated_contracts = tuple(
        replace(contract, oi=None) if index == 0 else contract
        for index, contract in enumerate(chain.contracts)
    )
    adapter = _CountingFakeBrokerAdapter(
        option_chain=replace(chain, contracts=mutated_contracts),
    )
    collector = S23FyersSnapshotCollector(artifact_root=tmp_path / "artifacts")

    with pytest.raises(S23FyersSnapshotCollectorError) as exc:
        collector.collect_from_files(
            config_path=_write_config(tmp_path),
            strategy_path=_write_strategy_folder(tmp_path),
            session_id="snapshot-missing-oi",
            adapter=adapter,
        )

    assert exc.value.code == "MISSING_CONTRACT_OI"
    assert adapter.stream_ticks_calls == 0
    assert adapter.order_api_calls == 0


def test_dry_run_prelude_build_works_from_collected_snapshot(tmp_path: Path) -> None:
    adapter = _CountingFakeBrokerAdapter()
    collector = S23FyersSnapshotCollector(artifact_root=tmp_path / "artifacts")

    artifact_set = collector.collect_from_files(
        config_path=_write_config(tmp_path),
        strategy_path=_write_strategy_folder(tmp_path),
        runtime_fixture_path=_write_runtime_fixture(tmp_path),
        session_id="snapshot-build-prelude",
        dry_run_build_prelude=True,
        adapter=adapter,
    )

    assert artifact_set.generated_prelude_events_path is not None
    assert artifact_set.generated_prelude_events_path.exists()
    assert artifact_set.generated_prelude_provenance_path is not None
    provenance = json.loads(
        artifact_set.generated_prelude_provenance_path.read_text(encoding="utf-8")
    )
    assert provenance["prelude_source"] == "generated_live_prelude"
    assert provenance["contract_selection_source"] == "runtime_option_chain_selector"
    assert provenance["snapshot_collection_source"] == "fyers_snapshot_preflight"
    assert adapter.get_option_quote_calls == 0
    assert adapter.stream_ticks_calls == 0
    assert adapter.order_api_calls == 0


def test_socket_loop_is_not_started_and_order_api_is_not_called(tmp_path: Path) -> None:
    adapter = _CountingFakeBrokerAdapter()
    collector = S23FyersSnapshotCollector(artifact_root=tmp_path / "artifacts")

    collector.collect_from_files(
        config_path=_write_config(tmp_path),
        strategy_path=_write_strategy_folder(tmp_path),
        session_id="snapshot-no-socket",
        adapter=adapter,
    )

    assert adapter.stream_ticks_calls == 0
    assert adapter.get_option_quote_calls == 0
    assert adapter.order_api_calls == 0
