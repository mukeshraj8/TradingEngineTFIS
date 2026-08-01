from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date, datetime
import inspect

import pytest

from tfis.broker import (
    BrokerInstrumentIdentity,
    BrokerInstrumentProduct,
    BrokerOptionType,
    BrokerReadAdapter,
    BrokerReadNormalizationError,
    BrokerReadPageRequest,
    BrokerReadRequest,
    BrokerReadStatus,
    BrokerSnapshotCompleteness,
    BrokerSourceQuality,
    FyersReadOnlyFixtureAdapter,
    assert_no_sensitive_values,
    broker_read_hash,
    build_account_read_snapshot,
    redact_sensitive,
    write_phase4b_reports,
)


def _request() -> BrokerReadRequest:
    return BrokerReadRequest(
        as_of=datetime.fromisoformat("2026-06-05T09:16:00+05:30"),
        trading_date=date(2026, 6, 5),
    )


def test_read_adapter_protocol_exposes_only_read_methods() -> None:
    methods = {
        name
        for name, value in inspect.getmembers(BrokerReadAdapter)
        if inspect.isfunction(value) and not name.startswith("_")
    }

    assert methods == {
        "get_capabilities",
        "get_account_session",
        "get_funds",
        "get_margins",
        "get_orders",
        "get_order_history",
        "get_trades",
        "get_positions",
        "get_instrument_details",
    }
    assert not {"place_order", "modify_order", "cancel_order", "exit_position", "transfer_funds"} & methods


def test_capability_reporting_is_read_only_and_fixture_backed() -> None:
    capabilities = FyersReadOnlyFixtureAdapter.from_fixture_name("authenticated").get_capabilities()

    assert capabilities.provider == "fyers"
    assert capabilities.source_quality is BrokerSourceQuality.FIXTURE
    assert capabilities.supports_account_session
    assert capabilities.supports_funds
    assert capabilities.supports_margins
    assert capabilities.supports_orders
    assert capabilities.supports_order_history
    assert capabilities.supports_trades
    assert capabilities.supports_positions
    assert capabilities.supports_instrument_details
    assert capabilities.supports_pagination
    assert capabilities.min_poll_interval_seconds > 0
    assert capabilities.write_authority is False
    assert capabilities.paper_authority is False
    assert capabilities.live_authority is False


def test_account_session_is_redacted_and_immutable() -> None:
    adapter = FyersReadOnlyFixtureAdapter.from_fixture_name("authenticated")
    result = adapter.get_account_session(_request())

    assert result.status is BrokerReadStatus.SUCCESS
    session = result.records[0]
    assert session.status.value == "AUTHENTICATED"
    assert session.account.to_dict()["account_id"] == "FY***45"
    assert session.account.account_hash == broker_read_hash(
        {"provider": "fyers", "environment": "fixture", "account_id": "FY12345"}
    )
    with pytest.raises(FrozenInstanceError):
        session.account.provider = "other"  # type: ignore[misc]


def test_unauthorized_account_returns_fail_closed_results() -> None:
    adapter = FyersReadOnlyFixtureAdapter.from_fixture_name("unauthorized")

    assert adapter.get_account_session(_request()).status is BrokerReadStatus.UNAUTHORIZED
    assert adapter.get_funds(_request()).status is BrokerReadStatus.UNAUTHORIZED
    assert adapter.get_margins(_request()).status is BrokerReadStatus.UNAUTHORIZED
    assert adapter.get_orders(_request()).status is BrokerReadStatus.UNAUTHORIZED
    assert adapter.get_trades(_request()).status is BrokerReadStatus.UNAUTHORIZED
    assert adapter.get_positions(_request()).status is BrokerReadStatus.UNAUTHORIZED


def test_funds_and_margins_normalize_account_truth() -> None:
    adapter = FyersReadOnlyFixtureAdapter.from_fixture_name("authenticated")
    funds = adapter.get_funds(_request()).records[0]
    margins = adapter.get_margins(_request()).records[0]

    assert funds.available_cash == 250000.0
    assert funds.currency == "INR"
    assert margins.margin_available == 180000.0
    assert margins.margin_used == 70000.0
    assert margins.account.account_hash == funds.account.account_hash


def test_orders_cover_empty_active_partial_rejected_and_exit_protection_orders() -> None:
    adapter = FyersReadOnlyFixtureAdapter.from_fixture_name("authenticated")
    orders = adapter.get_orders(_request()).records

    assert {order.status.value for order in orders} >= {"OPEN", "PARTIALLY_FILLED", "REJECTED"}
    assert {order.order_type.value for order in orders} >= {"LIMIT", "STOP_LIMIT"}
    assert any(order.trigger_price is not None for order in orders)
    assert any(order.limit_price == 120.0 and order.side.value == "BUY" for order in orders)
    assert FyersReadOnlyFixtureAdapter.from_fixture_name("empty_orders").get_orders(_request()).status is BrokerReadStatus.EMPTY


def test_order_history_events_are_normalized() -> None:
    events = FyersReadOnlyFixtureAdapter.from_fixture_name("authenticated").get_order_history(_request()).records

    assert len(events) == 3
    assert [event.event_id for event in events] == ["EVT-1", "EVT-2", "EVT-3"]
    assert events[2].event_type.value == "REJECTED"


def test_fills_are_deduplicated_by_broker_trade_id() -> None:
    fills = FyersReadOnlyFixtureAdapter.from_fixture_name("authenticated").get_trades(_request()).records

    assert len(fills) == 1
    assert fills[0].fill_id == "TRD-1"
    assert fills[0].quantity == 75
    assert fills[0].price == 100.0


def test_positions_include_intraday_and_carried_overnight_without_mutation() -> None:
    positions = FyersReadOnlyFixtureAdapter.from_fixture_name("authenticated").get_positions(_request()).records

    assert {position.carry_type.value for position in positions} == {"INTRADAY", "CARRIED_OVERNIGHT"}
    assert all(position.net_quantity == -75 for position in positions)


def test_instrument_identity_rejects_ambiguous_option_contracts() -> None:
    with pytest.raises(BrokerReadNormalizationError):
        BrokerInstrumentIdentity(
            provider="fixture",
            broker_symbol="NSE:NIFTY",
            normalized_symbol="NIFTY_UNKNOWN_CE",
            product=BrokerInstrumentProduct.OPTION,
            option_type=BrokerOptionType.CALL,
        )


def test_pagination_returns_next_cursor_and_second_page() -> None:
    adapter = FyersReadOnlyFixtureAdapter.from_fixture_name("authenticated")
    first = adapter.get_orders(BrokerReadRequest(as_of=_request().as_of, page=BrokerReadPageRequest(limit=1)))
    second = adapter.get_orders(BrokerReadRequest(as_of=_request().as_of, page=BrokerReadPageRequest(cursor=first.next_cursor, limit=1)))

    assert first.next_cursor == "cursor-2"
    assert first.records[0].order_id == "OID-PAGE-1"
    assert second.records[0].order_id == "OID-PAGE-2"


def test_partial_rate_limit_timeout_and_malformed_responses_are_explicit() -> None:
    partial = FyersReadOnlyFixtureAdapter.from_fixture_name("malformed_partial").get_orders(_request())
    rate_limited = FyersReadOnlyFixtureAdapter.from_fixture_name("rate_limit").get_orders(_request())
    base_payload = dict(FyersReadOnlyFixtureAdapter.from_fixture_name("authenticated")._payload)
    timeout = FyersReadOnlyFixtureAdapter(payload=base_payload | {"timeout": True}).get_orders(_request())
    malformed = FyersReadOnlyFixtureAdapter(payload=base_payload | {"orders": ["bad-row"]})

    assert partial.status is BrokerReadStatus.PARTIAL
    assert partial.failures[0].code == "MALFORMED_ORDER"
    assert rate_limited.status is BrokerReadStatus.RATE_LIMITED
    assert rate_limited.failures[0].retryable
    assert timeout.status is BrokerReadStatus.TIMEOUT
    assert malformed.get_orders(_request()).status is BrokerReadStatus.MALFORMED


def test_account_snapshot_is_complete_deterministic_and_reconciliation_ready() -> None:
    adapter = FyersReadOnlyFixtureAdapter.from_fixture_name("authenticated")
    first = build_account_read_snapshot(adapter, _request())
    second = build_account_read_snapshot(adapter, _request())

    assert first.completeness is BrokerSnapshotCompleteness.COMPLETE
    assert first.consistency_hash == second.consistency_hash
    assert len(first.orders.records) == 3
    assert len(first.fills.records) == 1
    assert len(first.positions.records) == 2
    assert first.consistency_findings == ()


def test_multi_account_mismatch_is_classified_invalid() -> None:
    class _MismatchAdapter(FyersReadOnlyFixtureAdapter):
        def get_funds(self, request: BrokerReadRequest):  # type: ignore[no-untyped-def]
            result = super().get_funds(request)
            wrong = type(result.records[0])(
                account=type(result.records[0].account)("fyers", "fixture", "OTHER"),
                captured_at=result.records[0].captured_at,
                available_cash=result.records[0].available_cash,
                ledger_balance=result.records[0].ledger_balance,
                opening_balance=result.records[0].opening_balance,
                currency=result.records[0].currency,
                source_quality=result.records[0].source_quality,
            )
            return type(result)(
                status=result.status,
                source_quality=result.source_quality,
                captured_at=result.captured_at,
                records=(wrong,),
                failures=result.failures,
                source_hash=result.source_hash,
                next_cursor=result.next_cursor,
                rate_limit_reset_at=result.rate_limit_reset_at,
                observed_latency_ms=result.observed_latency_ms,
            )

    snapshot = build_account_read_snapshot(_MismatchAdapter.from_fixture_name("authenticated"), _request())

    assert snapshot.completeness is BrokerSnapshotCompleteness.INVALID
    assert snapshot.consistency_findings[0].code == "ACCOUNT_MISMATCH"


def test_redaction_and_secret_checks_cover_reports_and_hashing() -> None:
    payload = {
        "access_token": "live-token",
        "nested": {"refresh_token": "refresh-token", "value": "safe"},
    }

    assert redact_sensitive(payload)["access_token"] == "REDACTED"
    assert redact_sensitive(payload)["nested"]["refresh_token"] == "REDACTED"
    assert broker_read_hash(payload) == broker_read_hash(redact_sensitive(payload))
    with pytest.raises(BrokerReadNormalizationError):
        assert_no_sensitive_values(payload)


def test_phase4b_reports_are_written_as_observational_artifacts(tmp_path) -> None:  # type: ignore[no-untyped-def]
    written = write_phase4b_reports(tmp_path)

    assert set(written) == {
        "phase4b_broker_read_audit.md",
        "phase4b_broker_capabilities.json",
        "phase4b_account_snapshot.json",
        "phase4b_order_normalization.json",
        "phase4b_fill_normalization.json",
        "phase4b_position_normalization.json",
        "phase4b_consistency_report.json",
        "phase4b_reconciliation_gap_register.json",
        "phase4b_performance_metrics.json",
        "phase4b_summary.md",
    }
    summary = (tmp_path / "phase4b_summary.md").read_text(encoding="utf-8")
    assert "Authority: read-only observational boundary" in summary
    assert "order creation, order modification, order cancellation and position mutation authority remain NONE" in summary
    assert_no_sensitive_values((tmp_path / "phase4b_account_snapshot.json").read_text(encoding="utf-8"))
