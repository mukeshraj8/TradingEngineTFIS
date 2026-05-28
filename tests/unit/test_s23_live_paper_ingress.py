from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest
import yaml

from tfis.brokers import BrokerAdapter, BrokerConnectionState, BrokerHealthEvent
from tfis.paper import (
    PaperEventType,
    PaperSessionState,
    S23NormalizedPaperEventLoader,
)
from tfis.paper.live_ingress import (
    S23BrokerPaperIngressRunner,
    S23LivePaperIngressError,
)


PRELUDE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "paper"
    / "s23_fyers_prelude.jsonl"
)
FULL_NORMALIZED_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "paper"
    / "s23_archive_ingress_dry_run.jsonl"
)
PAYLOAD_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "paper"
    / "fyers_market_data_payloads.json"
)


class _FakeBrokerAdapter(BrokerAdapter):
    broker_name = "fake"

    def __init__(self) -> None:
        loader = S23NormalizedPaperEventLoader()
        events = loader.load_jsonl(FULL_NORMALIZED_FIXTURE)
        self._underlying = next(
            event for event in events if event.envelope.event_type is PaperEventType.UNDERLYING_QUOTE
        )
        self._chain = next(
            event
            for event in events
            if event.envelope.event_type is PaperEventType.OPTION_CHAIN_SNAPSHOT
        )
        self._selected = next(
            event
            for event in events
            if event.envelope.event_type is PaperEventType.SELECTED_CONTRACT_QUOTE
        )
        self._connected = False

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def subscribe_symbols(self, symbols: tuple[str, ...]) -> tuple[str, ...]:
        return symbols

    def get_underlying_quote(self, symbol: str, *, session_date: date):
        return self._underlying

    def get_option_chain(self, symbol: str, expiry: date, *, session_date: date):
        return self._chain

    def get_option_quote(self, option_symbol: str, *, session_date: date):
        return self._selected

    def stream_ticks(self):
        return ()

    def health(self) -> BrokerHealthEvent:
        return BrokerHealthEvent(
            broker_name=self.broker_name,
            as_of=datetime.fromisoformat("2026-05-08T09:30:02+05:30"),
            connection_state=BrokerConnectionState.CONNECTED,
            source_id="fake:health",
            is_connected=self._connected,
        )

    def reconnect(self) -> BrokerHealthEvent:
        self.connect()
        return self.health()


def _write_config(
    tmp_path: Path,
    *,
    payload_fixture_path: Path | None = PAYLOAD_FIXTURE,
    capture_stream_events: bool = False,
    max_quote_age_seconds: float = 5.0,
    broker_overrides: dict[str, object] | None = None,
    paper_overrides: dict[str, object] | None = None,
    market_overrides: dict[str, object] | None = None,
) -> Path:
    payload_value = str(payload_fixture_path) if payload_fixture_path is not None else None
    broker_payload = {
        "provider": "fyers",
        "timezone": "Asia/Kolkata",
        "payload_fixture_path": payload_value,
        "capture_stream_events": capture_stream_events,
    }
    if broker_overrides:
        broker_payload.update(broker_overrides)
    paper_payload = {
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
    }
    if paper_overrides:
        paper_payload.update(paper_overrides)
    market_payload = {
        "underlying_symbol": "NIFTY",
        "weekly_expiry": "2026-05-12",
        "selected_contract_symbol": "NIFTY_20260512_25000_PE",
    }
    if market_overrides:
        market_payload.update(market_overrides)
    config_payload = {
        "source_mode": "broker_fyers_live_paper_ingress",
        "broker": broker_payload,
        "paper": paper_payload,
        "market": market_payload,
        "costs": {
            "brokerage_per_lot": 20.0,
            "slippage_entry_points": 1.0,
            "slippage_exit_points": 1.0,
            "spread_buffer_policy": "bid_ask_guard",
            "version_label": "paper-cost-v1",
        },
        "thresholds": {
            "max_quote_age_seconds": max_quote_age_seconds,
            "max_timing_drift_seconds": 5.0,
            "max_stale_events": 0,
            "max_missing_chains": 0,
            "required_selected_contract_availability_ratio": 1.0,
            "max_no_trade_rate": 0.0,
        },
    }
    path = tmp_path / "paper.s23.yaml"
    path.write_text(yaml.safe_dump(config_payload, sort_keys=False), encoding="utf-8")
    return path


def _write_payload_fixture(
    tmp_path: Path,
    *,
    drop_keys: tuple[str, ...] = (),
    mutate: dict[tuple[str, ...], object] | None = None,
) -> Path:
    payload = json.loads(PAYLOAD_FIXTURE.read_text(encoding="utf-8"))
    for key in drop_keys:
        payload.pop(key, None)
    for path_tokens, value in (mutate or {}).items():
        target = payload
        for token in path_tokens[:-1]:
            target = target[token]
        target[path_tokens[-1]] = value
    path = tmp_path / "fyers_payloads.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def test_preflight_missing_fyers_credentials_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path, payload_fixture_path=None)
    runner = S23BrokerPaperIngressRunner(artifact_root=tmp_path / "artifacts")
    monkeypatch.delenv("FYERS_APP_ID", raising=False)
    monkeypatch.delenv("FYERS_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FYERS_CLIENT_ID", raising=False)

    summary = runner.preflight(
        config_path=config_path,
        prelude_jsonl=PRELUDE_PATH,
        session_id="preflight-missing-creds",
    )

    assert summary.preflight_status == "NO_GO"
    assert summary.can_run is False
    assert any(issue.code == "missing_broker_credentials" for issue in summary.issues)


def test_preflight_fails_when_order_placement_block_is_disabled(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        paper_overrides={"no_live_orders_allowed": False},
    )
    runner = S23BrokerPaperIngressRunner(artifact_root=tmp_path / "artifacts")

    summary = runner.preflight(
        config_path=config_path,
        prelude_jsonl=PRELUDE_PATH,
        session_id="preflight-live-order-disabled",
    )

    assert summary.preflight_status == "NO_GO"
    assert any(issue.code == "live_order_block_disabled" for issue in summary.issues)


def test_preflight_fails_for_wrong_strategy(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        paper_overrides={"strategy_code": "S99"},
    )
    runner = S23BrokerPaperIngressRunner(artifact_root=tmp_path / "artifacts")

    summary = runner.preflight(
        config_path=config_path,
        prelude_jsonl=PRELUDE_PATH,
        session_id="preflight-wrong-strategy",
    )

    assert summary.preflight_status == "NO_GO"
    assert any(issue.code == "unsupported_strategy" for issue in summary.issues)


def test_preflight_fails_for_non_paper_mode(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        paper_overrides={"mode": "live"},
    )
    runner = S23BrokerPaperIngressRunner(artifact_root=tmp_path / "artifacts")

    summary = runner.preflight(
        config_path=config_path,
        prelude_jsonl=PRELUDE_PATH,
        session_id="preflight-non-paper",
    )

    assert summary.preflight_status == "NO_GO"
    assert any(issue.code == "non_paper_mode" for issue in summary.issues)


def test_valid_mock_config_passes_preflight_with_warning(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    runner = S23BrokerPaperIngressRunner(artifact_root=tmp_path / "artifacts")

    summary = runner.preflight(
        config_path=config_path,
        prelude_jsonl=PRELUDE_PATH,
        session_id="preflight-mock-pass",
    )

    assert summary.can_run is True
    assert summary.preflight_status == "WARNING"
    assert summary.uses_payload_fixture is True
    assert any(issue.code == "payload_fixture_mode_enabled" for issue in summary.issues)


def test_preflight_only_does_not_build_or_connect_broker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    runner = S23BrokerPaperIngressRunner(artifact_root=tmp_path / "artifacts")

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("Broker adapter must not be built during preflight-only mode.")

    monkeypatch.setattr(runner, "_build_adapter", _fail_if_called)

    summary = runner.preflight(
        config_path=config_path,
        prelude_jsonl=PRELUDE_PATH,
        session_id="preflight-no-connect",
    )

    assert summary.can_run is True


def test_live_broker_ingress_reaches_order_planned_and_persists_artifacts(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        capture_stream_events=True,
    )
    runner = S23BrokerPaperIngressRunner(artifact_root=tmp_path / "artifacts")

    artifact_set = runner.run(
        config_path=config_path,
        prelude_jsonl=PRELUDE_PATH,
        session_id="fyers-live-pass",
    )

    assert artifact_set.dry_run_artifacts.summary.terminal_state is PaperSessionState.ORDER_PLANNED
    assert artifact_set.summary.uses_broker_market_data is True
    assert artifact_set.broker_health_path.exists()
    assert artifact_set.normalized_events_path.exists()
    assert artifact_set.ingress_summary_path.exists()
    assert artifact_set.no_trade_or_order_plan_summary_path.exists()
    assert artifact_set.dry_run_artifacts.review_md_path.exists()

    rows = [
        json.loads(line)
        for line in artifact_set.normalized_events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    event_types = {row["event_type"] for row in rows}
    assert "UNDERLYING_QUOTE" in event_types
    assert "OPTION_CHAIN_SNAPSHOT" in event_types
    assert "SELECTED_CONTRACT_QUOTE" in event_types
    assert "SELECTED_CONTRACT_BAR" in event_types
    assert any(row["source_type"] == "broker_fyers" for row in rows)
    assert not any("optionsChain" in json.dumps(row) for row in rows)

    terminal_summary = json.loads(
        artifact_set.no_trade_or_order_plan_summary_path.read_text(encoding="utf-8")
    )
    assert terminal_summary["summary_kind"] == "order_plan"


def test_live_broker_ingress_accepts_generic_broker_adapter(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, payload_fixture_path=None)
    runner = S23BrokerPaperIngressRunner(artifact_root=tmp_path / "artifacts")

    artifact_set = runner.run(
        config_path=config_path,
        prelude_jsonl=PRELUDE_PATH,
        session_id="generic-adapter-pass",
        adapter=_FakeBrokerAdapter(),
    )

    assert artifact_set.dry_run_artifacts.summary.terminal_state is PaperSessionState.ORDER_PLANNED
    assert artifact_set.summary.broker_name == "fake"


def test_missing_selected_contract_quote_becomes_no_trade(tmp_path: Path) -> None:
    payload_path = _write_payload_fixture(
        tmp_path,
        drop_keys=("selected_contract_quote",),
    )
    config_path = _write_config(tmp_path, payload_fixture_path=payload_path)
    runner = S23BrokerPaperIngressRunner(artifact_root=tmp_path / "artifacts")

    artifact_set = runner.run(
        config_path=config_path,
        prelude_jsonl=PRELUDE_PATH,
        session_id="missing-selected-quote",
    )

    assert artifact_set.dry_run_artifacts.summary.terminal_state in {
        PaperSessionState.NO_TRADE,
        PaperSessionState.ABORTED,
    }
    assert (
        "missing_selected_contract_quote"
        in artifact_set.dry_run_artifacts.summary.no_trade_reasons
        or "missing_selected_contract_quote"
        in artifact_set.dry_run_artifacts.summary.abort_reasons
    )


def test_stale_selected_contract_quote_becomes_terminal_guardrail(tmp_path: Path) -> None:
    payload_path = _write_payload_fixture(
        tmp_path,
        mutate={
            ("selected_contract_quote", "d", 0, "last_traded_time"): "2026-05-08T09:20:00+05:30",
        },
    )
    config_path = _write_config(
        tmp_path,
        payload_fixture_path=payload_path,
        max_quote_age_seconds=5.0,
    )
    runner = S23BrokerPaperIngressRunner(artifact_root=tmp_path / "artifacts")

    artifact_set = runner.run(
        config_path=config_path,
        prelude_jsonl=PRELUDE_PATH,
        session_id="stale-selected-quote",
    )

    assert artifact_set.dry_run_artifacts.summary.terminal_state in {
        PaperSessionState.NO_TRADE,
        PaperSessionState.ABORTED,
    }
    assert (
        "stale_selected_contract_quote"
        in artifact_set.dry_run_artifacts.summary.no_trade_reasons
        or "stale_selected_contract_quote"
        in artifact_set.dry_run_artifacts.summary.abort_reasons
        or "stale_ingest_quote"
        in artifact_set.dry_run_artifacts.summary.abort_reasons
    )


def test_prelude_rejects_broker_market_event_types(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    runner = S23BrokerPaperIngressRunner(artifact_root=tmp_path / "artifacts")

    with pytest.raises(S23LivePaperIngressError):
        runner.run(
            config_path=config_path,
            prelude_jsonl=FULL_NORMALIZED_FIXTURE,
            session_id="invalid-prelude",
        )
