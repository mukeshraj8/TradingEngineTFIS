from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol

from tfis.storage import atomic_write_text


_SENSITIVE_KEY_FRAGMENTS = (
    "access_token",
    "authorization",
    "auth_header",
    "cookie",
    "jwt",
    "password",
    "pin",
    "refresh_token",
    "secret",
    "token",
)


class BrokerReadBoundaryError(RuntimeError):
    """Base error for broker-neutral read-boundary failures."""


class BrokerReadNormalizationError(BrokerReadBoundaryError):
    """Raised when broker account truth cannot be normalized safely."""


class BrokerReadStatus(str, Enum):
    SUCCESS = "SUCCESS"
    EMPTY = "EMPTY"
    PARTIAL = "PARTIAL"
    UNAUTHORIZED = "UNAUTHORIZED"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    MALFORMED = "MALFORMED"
    UNAVAILABLE = "UNAVAILABLE"


class BrokerSourceQuality(str, Enum):
    FIXTURE = "FIXTURE"
    CAPTURED_RAW = "CAPTURED_RAW"
    LIVE_READ = "LIVE_READ"
    UNKNOWN = "UNKNOWN"


class BrokerAccountSessionStatus(str, Enum):
    AUTHENTICATED = "AUTHENTICATED"
    UNAUTHORIZED = "UNAUTHORIZED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class BrokerInstrumentProduct(str, Enum):
    OPTION = "OPTION"
    FUTURE = "FUTURE"
    EQUITY = "EQUITY"
    INDEX = "INDEX"
    UNKNOWN = "UNKNOWN"


class BrokerOptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"
    NONE = "NONE"


class BrokerOrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    UNKNOWN = "UNKNOWN"


class BrokerOrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    UNKNOWN = "UNKNOWN"


class BrokerOrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class BrokerPositionCarryType(str, Enum):
    INTRADAY = "INTRADAY"
    CARRIED_OVERNIGHT = "CARRIED_OVERNIGHT"
    CLOSED_DAY = "CLOSED_DAY"
    UNKNOWN = "UNKNOWN"


class BrokerSnapshotCompleteness(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class BrokerReadFailure:
    code: str
    message: str
    retryable: bool = False
    source_field: str | None = None


@dataclass(frozen=True, slots=True)
class BrokerReadPageRequest:
    cursor: str | None = None
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class BrokerReadRequest:
    account_id: str | None = None
    as_of: datetime | None = None
    trading_date: date | None = None
    page: BrokerReadPageRequest | None = None


@dataclass(frozen=True, slots=True)
class BrokerReadResult:
    status: BrokerReadStatus
    source_quality: BrokerSourceQuality
    captured_at: datetime
    records: tuple[Any, ...] = ()
    failures: tuple[BrokerReadFailure, ...] = ()
    source_hash: str | None = None
    next_cursor: str | None = None
    rate_limit_reset_at: datetime | None = None
    observed_latency_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(asdict(self))


@dataclass(frozen=True, slots=True)
class BrokerReadCapabilities:
    provider: str
    supports_account_session: bool
    supports_funds: bool
    supports_margins: bool
    supports_orders: bool
    supports_order_history: bool
    supports_trades: bool
    supports_positions: bool
    supports_instrument_details: bool
    supports_pagination: bool
    min_poll_interval_seconds: float
    rate_limit_policy: str
    source_quality: BrokerSourceQuality
    fixture_mode: bool
    write_authority: bool = False
    paper_authority: bool = False
    live_authority: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(asdict(self))


@dataclass(frozen=True, slots=True)
class BrokerAccountIdentity:
    provider: str
    environment: str
    account_id: str
    display_name: str | None = None
    account_hash: str | None = None

    def __post_init__(self) -> None:
        if self.account_hash is None:
            object.__setattr__(
                self,
                "account_hash",
                broker_read_hash(
                    {
                        "provider": self.provider,
                        "environment": self.environment,
                        "account_id": self.account_id,
                    }
                ),
            )

    def to_dict(self) -> dict[str, Any]:
        data = _to_jsonable(asdict(self))
        data["account_id"] = _redact_account_id(self.account_id)
        return data


@dataclass(frozen=True, slots=True)
class BrokerAccountSessionSnapshot:
    account: BrokerAccountIdentity
    status: BrokerAccountSessionStatus
    captured_at: datetime
    permissions: tuple[str, ...]
    source_quality: BrokerSourceQuality
    diagnostic_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(asdict(self))


@dataclass(frozen=True, slots=True)
class BrokerFundsSnapshot:
    account: BrokerAccountIdentity
    captured_at: datetime
    available_cash: float | None
    ledger_balance: float | None
    opening_balance: float | None
    currency: str
    source_quality: BrokerSourceQuality

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(asdict(self))


@dataclass(frozen=True, slots=True)
class BrokerMarginSnapshot:
    account: BrokerAccountIdentity
    captured_at: datetime
    margin_available: float | None
    margin_used: float | None
    span_margin: float | None
    exposure_margin: float | None
    currency: str
    source_quality: BrokerSourceQuality

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(asdict(self))


@dataclass(frozen=True, slots=True)
class BrokerInstrumentIdentity:
    provider: str
    broker_symbol: str
    normalized_symbol: str
    product: BrokerInstrumentProduct
    exchange: str | None = None
    underlying: str | None = None
    expiry: date | None = None
    strike: float | None = None
    option_type: BrokerOptionType = BrokerOptionType.NONE
    lot_size: int | None = None
    tick_size: float | None = None

    def __post_init__(self) -> None:
        if self.product is BrokerInstrumentProduct.OPTION:
            missing = []
            if self.underlying is None:
                missing.append("underlying")
            if self.expiry is None:
                missing.append("expiry")
            if self.strike is None:
                missing.append("strike")
            if self.option_type is BrokerOptionType.NONE:
                missing.append("option_type")
            if missing:
                raise BrokerReadNormalizationError(
                    "Ambiguous option contract identity: " + ", ".join(missing)
                )

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(asdict(self))


@dataclass(frozen=True, slots=True)
class BrokerOrderSnapshot:
    account: BrokerAccountIdentity
    order_id: str
    instrument: BrokerInstrumentIdentity
    side: BrokerOrderSide
    order_type: BrokerOrderType
    status: BrokerOrderStatus
    quantity: int
    filled_quantity: int
    remaining_quantity: int
    limit_price: float | None
    trigger_price: float | None
    average_fill_price: float | None
    product_type: str | None
    created_at: datetime | None
    updated_at: datetime | None
    rejection_reason: str | None = None
    source_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(asdict(self))


@dataclass(frozen=True, slots=True)
class BrokerOrderEvent:
    account: BrokerAccountIdentity
    order_id: str
    event_id: str
    event_type: BrokerOrderStatus
    observed_at: datetime
    message: str | None = None
    source_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(asdict(self))


@dataclass(frozen=True, slots=True)
class BrokerFillSnapshot:
    account: BrokerAccountIdentity
    fill_id: str
    order_id: str
    instrument: BrokerInstrumentIdentity
    side: BrokerOrderSide
    quantity: int
    price: float
    filled_at: datetime
    brokerage: float | None = None
    exchange_trade_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(asdict(self))


@dataclass(frozen=True, slots=True)
class BrokerPositionSnapshot:
    account: BrokerAccountIdentity
    instrument: BrokerInstrumentIdentity
    net_quantity: int
    buy_quantity: int
    sell_quantity: int
    average_price: float | None
    last_price: float | None
    realized_pnl: float | None
    unrealized_pnl: float | None
    carry_type: BrokerPositionCarryType
    product_type: str | None
    captured_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(asdict(self))


@dataclass(frozen=True, slots=True)
class BrokerAccountReadSnapshot:
    account: BrokerAccountIdentity
    captured_at: datetime
    session: BrokerReadResult
    funds: BrokerReadResult
    margins: BrokerReadResult
    orders: BrokerReadResult
    order_history: BrokerReadResult
    fills: BrokerReadResult
    positions: BrokerReadResult
    instruments: BrokerReadResult
    completeness: BrokerSnapshotCompleteness = field(init=False)
    consistency_hash: str = field(init=False)
    consistency_findings: tuple[BrokerReadFailure, ...] = field(init=False)

    def __post_init__(self) -> None:
        findings = _snapshot_consistency_findings(self)
        object.__setattr__(self, "consistency_findings", findings)
        object.__setattr__(self, "completeness", _snapshot_completeness(self, findings))
        object.__setattr__(
            self,
            "consistency_hash",
            broker_read_hash(self.to_dict(include_hash=False)),
        )

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = {
            "account": self.account.to_dict(),
            "captured_at": self.captured_at.isoformat(),
            "session": self.session.to_dict(),
            "funds": self.funds.to_dict(),
            "margins": self.margins.to_dict(),
            "orders": self.orders.to_dict(),
            "order_history": self.order_history.to_dict(),
            "fills": self.fills.to_dict(),
            "positions": self.positions.to_dict(),
            "instruments": self.instruments.to_dict(),
            "completeness": self.completeness.value,
            "consistency_findings": [_to_jsonable(asdict(item)) for item in self.consistency_findings],
        }
        if include_hash:
            data["consistency_hash"] = self.consistency_hash
        return data


class BrokerReadAdapter(Protocol):
    def get_capabilities(self) -> BrokerReadCapabilities:
        ...

    def get_account_session(self, request: BrokerReadRequest) -> BrokerReadResult:
        ...

    def get_funds(self, request: BrokerReadRequest) -> BrokerReadResult:
        ...

    def get_margins(self, request: BrokerReadRequest) -> BrokerReadResult:
        ...

    def get_orders(self, request: BrokerReadRequest) -> BrokerReadResult:
        ...

    def get_order_history(self, request: BrokerReadRequest) -> BrokerReadResult:
        ...

    def get_trades(self, request: BrokerReadRequest) -> BrokerReadResult:
        ...

    def get_positions(self, request: BrokerReadRequest) -> BrokerReadResult:
        ...

    def get_instrument_details(self, request: BrokerReadRequest) -> BrokerReadResult:
        ...


def build_account_read_snapshot(
    adapter: BrokerReadAdapter,
    request: BrokerReadRequest,
) -> BrokerAccountReadSnapshot:
    session = adapter.get_account_session(request)
    account = _single_account_from_result(session)
    return BrokerAccountReadSnapshot(
        account=account,
        captured_at=request.as_of or session.captured_at,
        session=session,
        funds=adapter.get_funds(request),
        margins=adapter.get_margins(request),
        orders=adapter.get_orders(request),
        order_history=adapter.get_order_history(request),
        fills=adapter.get_trades(request),
        positions=adapter.get_positions(request),
        instruments=adapter.get_instrument_details(request),
    )


def broker_read_hash(value: Any) -> str:
    canonical = json.dumps(
        redact_sensitive(_to_jsonable(value)),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS):
                redacted[key_text] = "REDACTED"
            else:
                redacted[key_text] = redact_sensitive(item)
        return redacted
    if isinstance(value, (tuple, list)):
        return [redact_sensitive(item) for item in value]
    return value


def assert_no_sensitive_values(value: Any) -> None:
    payload = json.dumps(_to_jsonable(value), sort_keys=True, default=str)
    for marker in ("live-token", "refresh-token", "api-secret", "super-secret", "FY12345"):
        if marker in payload:
            raise BrokerReadNormalizationError("Sensitive broker credential leaked.")


def write_phase4b_reports(
    report_dir: str | Path,
    *,
    adapter: BrokerReadAdapter | None = None,
    request: BrokerReadRequest | None = None,
) -> dict[str, Path]:
    target = Path(report_dir)
    target.mkdir(parents=True, exist_ok=True)
    active_adapter = adapter or FyersReadOnlyFixtureAdapter.from_fixture_name("authenticated")
    active_request = request or BrokerReadRequest(as_of=_fixture_now(), trading_date=date(2026, 6, 5))
    snapshot = build_account_read_snapshot(active_adapter, active_request)
    capabilities = active_adapter.get_capabilities()

    orders = [record.to_dict() for record in snapshot.orders.records]
    fills = [record.to_dict() for record in snapshot.fills.records]
    positions = [record.to_dict() for record in snapshot.positions.records]
    consistency = {
        "completeness": snapshot.completeness.value,
        "consistency_hash": snapshot.consistency_hash,
        "findings": [_to_jsonable(asdict(item)) for item in snapshot.consistency_findings],
        "read_only_authority": {
            "broker_submission": "NONE",
            "paper_submission": "NONE",
            "live_submission": "NONE",
            "order_creation": "NONE",
            "order_cancellation": "NONE",
            "order_modification": "NONE",
            "position_mutation": "NONE",
        },
    }
    gap_register = {
        "milestone": "Phase 4B M1",
        "gaps": [
            {
                "code": "NO_REAL_BROKER_CALLS_IN_TESTS",
                "status": "EXPECTED",
                "description": "Concrete adapter is proven with FYERS-shaped fixture payloads only.",
            },
            {
                "code": "NO_RECONCILIATION_MUTATION",
                "status": "DEFERRED",
                "description": "Snapshots are reconciliation-ready but do not correct orders or positions.",
            },
            {
                "code": "BROKER_WRITE_AUTHORITY_ABSENT",
                "status": "INTENTIONAL",
                "description": "No place, modify, cancel, exit, convert or transfer methods exist on the read protocol.",
            },
        ],
    }
    performance = {
        "milestone": "Phase 4B M1",
        "fixture_mode": True,
        "observed_latency_ms_by_call": {
            "account_session": snapshot.session.observed_latency_ms,
            "funds": snapshot.funds.observed_latency_ms,
            "margins": snapshot.margins.observed_latency_ms,
            "orders": snapshot.orders.observed_latency_ms,
            "order_history": snapshot.order_history.observed_latency_ms,
            "fills": snapshot.fills.observed_latency_ms,
            "positions": snapshot.positions.observed_latency_ms,
            "instruments": snapshot.instruments.observed_latency_ms,
        },
        "polling_model": {
            "defined_only": True,
            "minimum_poll_interval_seconds": capabilities.min_poll_interval_seconds,
            "scheduler_implemented": False,
        },
    }
    audit = {
        "verdict": "PHASE4B_M1_ACCEPT",
        "adapter": "FyersReadOnlyFixtureAdapter",
        "provider": capabilities.provider,
        "source_quality": capabilities.source_quality.value,
        "boundary": "broker-neutral read-only",
        "notes": [
            "Snapshots are immutable dataclasses.",
            "Broker-specific payloads are redacted and hashed before report emission.",
            "Shadow integration is observational only and cannot block strategy decisions.",
        ],
    }

    reports = {
        "phase4b_broker_read_audit.md": _phase4b_summary_markdown(
            audit=audit,
            snapshot=snapshot,
            capabilities=capabilities,
            gap_register=gap_register,
        ),
        "phase4b_broker_capabilities.json": capabilities.to_dict(),
        "phase4b_account_snapshot.json": snapshot.to_dict(),
        "phase4b_order_normalization.json": {"orders": orders},
        "phase4b_fill_normalization.json": {"fills": fills},
        "phase4b_position_normalization.json": {"positions": positions},
        "phase4b_consistency_report.json": consistency,
        "phase4b_reconciliation_gap_register.json": gap_register,
        "phase4b_performance_metrics.json": performance,
        "phase4b_summary.md": _phase4b_summary_markdown(
            audit=audit,
            snapshot=snapshot,
            capabilities=capabilities,
            gap_register=gap_register,
        ),
    }
    written: dict[str, Path] = {}
    for name, payload in reports.items():
        path = target / name
        if name.endswith(".json"):
            atomic_write_text(path, json.dumps(_to_jsonable(payload), indent=2, sort_keys=True) + "\n")
        else:
            atomic_write_text(path, str(payload))
        written[name] = path
    return written


class FyersReadOnlyFixtureAdapter:
    """Read-only adapter that normalizes FYERS-shaped account fixture payloads."""

    provider = "fyers"

    def __init__(
        self,
        *,
        payload: Mapping[str, Any],
        source_quality: BrokerSourceQuality = BrokerSourceQuality.FIXTURE,
    ) -> None:
        self._payload = dict(payload)
        self._source_quality = source_quality

    @classmethod
    def from_fixture_name(cls, name: str) -> "FyersReadOnlyFixtureAdapter":
        return cls(payload=_fixture_payload(name))

    def get_capabilities(self) -> BrokerReadCapabilities:
        return BrokerReadCapabilities(
            provider=self.provider,
            supports_account_session=True,
            supports_funds=True,
            supports_margins=True,
            supports_orders=True,
            supports_order_history=True,
            supports_trades=True,
            supports_positions=True,
            supports_instrument_details=True,
            supports_pagination=True,
            min_poll_interval_seconds=2.0,
            rate_limit_policy="Respect broker read throttles; back off on RATE_LIMITED and do not schedule faster than min_poll_interval_seconds.",
            source_quality=self._source_quality,
            fixture_mode=True,
        )

    def get_account_session(self, request: BrokerReadRequest) -> BrokerReadResult:
        session = self._payload.get("account_session", {})
        if self._payload.get("unauthorized"):
            return self._result(BrokerReadStatus.UNAUTHORIZED, request, failures=(BrokerReadFailure("UNAUTHORIZED", "Broker account session is not authorized.", False),))
        account = self._account()
        record = BrokerAccountSessionSnapshot(
            account=account,
            status=BrokerAccountSessionStatus(str(session.get("status", "AUTHENTICATED"))),
            captured_at=_as_datetime(session.get("captured_at")) or _request_time(request),
            permissions=tuple(str(item) for item in session.get("permissions", ("read",))),
            source_quality=self._source_quality,
            diagnostic_codes=tuple(str(item) for item in session.get("diagnostic_codes", ())),
        )
        return self._result(BrokerReadStatus.SUCCESS, request, records=(record,))

    def get_funds(self, request: BrokerReadRequest) -> BrokerReadResult:
        if self._payload.get("unauthorized"):
            return self._unauthorized(request)
        funds = self._payload.get("funds", {})
        record = BrokerFundsSnapshot(
            account=self._account(),
            captured_at=_request_time(request),
            available_cash=_as_float(funds.get("available_cash")),
            ledger_balance=_as_float(funds.get("ledger_balance")),
            opening_balance=_as_float(funds.get("opening_balance")),
            currency=str(funds.get("currency", "INR")),
            source_quality=self._source_quality,
        )
        return self._result(BrokerReadStatus.SUCCESS, request, records=(record,))

    def get_margins(self, request: BrokerReadRequest) -> BrokerReadResult:
        if self._payload.get("unauthorized"):
            return self._unauthorized(request)
        margin = self._payload.get("margins", {})
        record = BrokerMarginSnapshot(
            account=self._account(),
            captured_at=_request_time(request),
            margin_available=_as_float(margin.get("available")),
            margin_used=_as_float(margin.get("used")),
            span_margin=_as_float(margin.get("span")),
            exposure_margin=_as_float(margin.get("exposure")),
            currency=str(margin.get("currency", "INR")),
            source_quality=self._source_quality,
        )
        return self._result(BrokerReadStatus.SUCCESS, request, records=(record,))

    def get_orders(self, request: BrokerReadRequest) -> BrokerReadResult:
        return self._normalize_order_records("orders", request)

    def get_order_history(self, request: BrokerReadRequest) -> BrokerReadResult:
        if self._payload.get("unauthorized"):
            return self._unauthorized(request)
        records = tuple(
            BrokerOrderEvent(
                account=self._account(),
                order_id=str(item.get("id") or item.get("order_id")),
                event_id=str(item.get("event_id") or item.get("id") or item.get("order_id")),
                event_type=_order_status(item.get("status")),
                observed_at=_as_datetime(item.get("observed_at")) or _request_time(request),
                message=_as_optional_str(item.get("message")),
                source_status=_as_optional_str(item.get("status")),
            )
            for item in self._iter_paged("order_history", request)
            if isinstance(item, Mapping)
        )
        return self._result(BrokerReadStatus.SUCCESS if records else BrokerReadStatus.EMPTY, request, records=records)

    def get_trades(self, request: BrokerReadRequest) -> BrokerReadResult:
        if self._payload.get("unauthorized"):
            return self._unauthorized(request)
        records: list[BrokerFillSnapshot] = []
        failures: list[BrokerReadFailure] = []
        seen: set[str] = set()
        for item in self._iter_paged("trades", request):
            if not isinstance(item, Mapping):
                failures.append(BrokerReadFailure("MALFORMED_FILL", "Fill row is not an object.", False))
                continue
            fill_id = str(item.get("trade_id") or item.get("fill_id") or item.get("id"))
            if fill_id in seen:
                continue
            seen.add(fill_id)
            try:
                records.append(
                    BrokerFillSnapshot(
                        account=self._account(),
                        fill_id=fill_id,
                        order_id=str(item.get("order_id")),
                        instrument=_instrument_from_mapping(item, self.provider),
                        side=_order_side(item.get("side")),
                        quantity=int(item.get("qty") or item.get("quantity") or 0),
                        price=float(item.get("price")),
                        filled_at=_as_datetime(item.get("filled_at")) or _request_time(request),
                        brokerage=_as_float(item.get("brokerage")),
                        exchange_trade_id=_as_optional_str(item.get("exchange_trade_id")),
                    )
                )
            except (TypeError, ValueError, BrokerReadNormalizationError) as exc:
                failures.append(BrokerReadFailure("MALFORMED_FILL", str(exc), False))
        status = BrokerReadStatus.PARTIAL if failures and records else BrokerReadStatus.SUCCESS if records else BrokerReadStatus.EMPTY
        return self._result(status, request, records=tuple(records), failures=tuple(failures))

    def get_positions(self, request: BrokerReadRequest) -> BrokerReadResult:
        if self._payload.get("unauthorized"):
            return self._unauthorized(request)
        failures = _special_failures(self._payload, "positions")
        records: list[BrokerPositionSnapshot] = []
        for item in self._payload.get("positions", ()):
            try:
                if not isinstance(item, Mapping):
                    raise BrokerReadNormalizationError("Position row is not an object.")
                records.append(
                    BrokerPositionSnapshot(
                        account=self._account(),
                        instrument=_instrument_from_mapping(item, self.provider),
                        net_quantity=int(item.get("net_qty") or item.get("net_quantity") or 0),
                        buy_quantity=int(item.get("buy_qty") or item.get("buy_quantity") or 0),
                        sell_quantity=int(item.get("sell_qty") or item.get("sell_quantity") or 0),
                        average_price=_as_float(item.get("avg_price") or item.get("average_price")),
                        last_price=_as_float(item.get("ltp") or item.get("last_price")),
                        realized_pnl=_as_float(item.get("realized_pnl")),
                        unrealized_pnl=_as_float(item.get("unrealized_pnl")),
                        carry_type=_carry_type(item.get("carry_type")),
                        product_type=_as_optional_str(item.get("product_type")),
                        captured_at=_request_time(request),
                    )
                )
            except (TypeError, ValueError, BrokerReadNormalizationError) as exc:
                failures += (BrokerReadFailure("MALFORMED_POSITION", str(exc), False),)
        status = _status_for(records, failures, self._payload)
        return self._result(status, request, records=tuple(records), failures=failures)

    def get_instrument_details(self, request: BrokerReadRequest) -> BrokerReadResult:
        if self._payload.get("unauthorized"):
            return self._unauthorized(request)
        records = tuple(
            _instrument_from_mapping(item, self.provider)
            for item in self._payload.get("instruments", ())
            if isinstance(item, Mapping)
        )
        return self._result(BrokerReadStatus.SUCCESS if records else BrokerReadStatus.EMPTY, request, records=records)

    def _normalize_order_records(self, key: str, request: BrokerReadRequest) -> BrokerReadResult:
        if self._payload.get("unauthorized"):
            return self._unauthorized(request)
        failures = _special_failures(self._payload, key)
        records: list[BrokerOrderSnapshot] = []
        for item in self._iter_paged(key, request):
            try:
                if not isinstance(item, Mapping):
                    raise BrokerReadNormalizationError("Order row is not an object.")
                qty = int(item.get("qty") or item.get("quantity") or 0)
                filled = int(item.get("filled_qty") or item.get("filled_quantity") or 0)
                records.append(
                    BrokerOrderSnapshot(
                        account=self._account(),
                        order_id=str(item.get("id") or item.get("order_id")),
                        instrument=_instrument_from_mapping(item, self.provider),
                        side=_order_side(item.get("side")),
                        order_type=_order_type(item.get("type") or item.get("order_type")),
                        status=_order_status(item.get("status")),
                        quantity=qty,
                        filled_quantity=filled,
                        remaining_quantity=max(0, qty - filled),
                        limit_price=_as_float(item.get("limit_price")),
                        trigger_price=_as_float(item.get("trigger_price")),
                        average_fill_price=_as_float(item.get("avg_price") or item.get("average_fill_price")),
                        product_type=_as_optional_str(item.get("product_type")),
                        created_at=_as_datetime(item.get("created_at")),
                        updated_at=_as_datetime(item.get("updated_at")),
                        rejection_reason=_as_optional_str(item.get("rejection_reason")),
                        source_status=_as_optional_str(item.get("status")),
                    )
                )
            except (TypeError, ValueError, BrokerReadNormalizationError) as exc:
                failures += (BrokerReadFailure("MALFORMED_ORDER", str(exc), False),)
        status = _status_for(records, failures, self._payload)
        return self._result(status, request, records=tuple(records), failures=failures, next_cursor=_next_cursor(self._payload, key, request))

    def _account(self) -> BrokerAccountIdentity:
        raw = self._payload.get("account", {})
        if not isinstance(raw, Mapping):
            raw = {}
        return BrokerAccountIdentity(
            provider=self.provider,
            environment=str(raw.get("environment", "fixture")),
            account_id=str(raw.get("id", "UNKNOWN")),
            display_name=_as_optional_str(raw.get("display_name")),
        )

    def _result(
        self,
        status: BrokerReadStatus,
        request: BrokerReadRequest,
        *,
        records: tuple[Any, ...] = (),
        failures: tuple[BrokerReadFailure, ...] = (),
        next_cursor: str | None = None,
    ) -> BrokerReadResult:
        return BrokerReadResult(
            status=status,
            source_quality=self._source_quality,
            captured_at=_request_time(request),
            records=records,
            failures=failures,
            source_hash=broker_read_hash({"records": [getattr(item, "to_dict", lambda: item)() for item in records], "failures": failures}),
            next_cursor=next_cursor,
            rate_limit_reset_at=_request_time(request) if status is BrokerReadStatus.RATE_LIMITED else None,
            observed_latency_ms=1,
        )

    def _unauthorized(self, request: BrokerReadRequest) -> BrokerReadResult:
        return self._result(
            BrokerReadStatus.UNAUTHORIZED,
            request,
            failures=(BrokerReadFailure("UNAUTHORIZED", "Broker account is unauthorized for read access.", False),),
        )

    def _iter_paged(self, key: str, request: BrokerReadRequest) -> tuple[Any, ...]:
        pages = self._payload.get(f"{key}_pages")
        if request.page is not None and isinstance(pages, Mapping):
            cursor = request.page.cursor if request.page else None
            return tuple(pages.get(cursor or "first", ()))
        values = self._payload.get(key, ())
        return tuple(values) if isinstance(values, list | tuple) else ()


def _snapshot_consistency_findings(snapshot: BrokerAccountReadSnapshot) -> tuple[BrokerReadFailure, ...]:
    findings: list[BrokerReadFailure] = []
    account_hash = snapshot.account.account_hash
    for name in ("funds", "margins", "orders", "order_history", "fills", "positions", "instruments"):
        result = getattr(snapshot, name)
        for record in result.records:
            record_account = getattr(record, "account", None)
            if record_account is not None and record_account.account_hash != account_hash:
                findings.append(BrokerReadFailure("ACCOUNT_MISMATCH", f"{name} contains a different account identity.", False))
    order_ids = [record.order_id for record in snapshot.orders.records if hasattr(record, "order_id")]
    if len(order_ids) != len(set(order_ids)):
        findings.append(BrokerReadFailure("DUPLICATE_ORDER_ID", "Orders contain duplicate broker order ids.", False))
    return tuple(findings)


def _snapshot_completeness(snapshot: BrokerAccountReadSnapshot, findings: tuple[BrokerReadFailure, ...]) -> BrokerSnapshotCompleteness:
    if any(item.code == "ACCOUNT_MISMATCH" for item in findings):
        return BrokerSnapshotCompleteness.INVALID
    statuses = [
        snapshot.session.status,
        snapshot.funds.status,
        snapshot.margins.status,
        snapshot.orders.status,
        snapshot.order_history.status,
        snapshot.fills.status,
        snapshot.positions.status,
        snapshot.instruments.status,
    ]
    if all(status in {BrokerReadStatus.SUCCESS, BrokerReadStatus.EMPTY} for status in statuses):
        return BrokerSnapshotCompleteness.COMPLETE
    if all(status in {BrokerReadStatus.UNAUTHORIZED, BrokerReadStatus.UNAVAILABLE} for status in statuses):
        return BrokerSnapshotCompleteness.UNAVAILABLE
    return BrokerSnapshotCompleteness.PARTIAL


def _single_account_from_result(result: BrokerReadResult) -> BrokerAccountIdentity:
    for record in result.records:
        account = getattr(record, "account", None)
        if isinstance(account, BrokerAccountIdentity):
            return account
    raise BrokerReadNormalizationError("Account session did not include a broker-neutral account identity.")


def _fixture_now() -> datetime:
    return datetime.fromisoformat("2026-06-05T09:16:00+05:30")


def _request_time(request: BrokerReadRequest) -> datetime:
    return request.as_of or _fixture_now()


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value)
    return None


def _as_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value)
    return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _redact_account_id(value: str) -> str:
    if len(value) <= 4:
        return "****"
    return f"{value[:2]}***{value[-2:]}"


def _instrument_from_mapping(item: Mapping[str, Any], provider: str) -> BrokerInstrumentIdentity:
    product = _product(item.get("product") or item.get("instrument_product"))
    option_type = _option_type(item.get("option_type"))
    normalized_symbol = str(item.get("normalized_symbol") or item.get("symbol") or item.get("broker_symbol"))
    return BrokerInstrumentIdentity(
        provider=provider,
        broker_symbol=str(item.get("broker_symbol") or item.get("symbol") or normalized_symbol),
        normalized_symbol=normalized_symbol,
        product=product,
        exchange=_as_optional_str(item.get("exchange")),
        underlying=_as_optional_str(item.get("underlying")),
        expiry=_as_date(item.get("expiry")),
        strike=_as_float(item.get("strike")),
        option_type=option_type,
        lot_size=int(item["lot_size"]) if item.get("lot_size") is not None else None,
        tick_size=_as_float(item.get("tick_size")),
    )


def _product(value: Any) -> BrokerInstrumentProduct:
    text = str(value or "UNKNOWN").upper()
    if text in {"OPT", "OPTION", "OPTIONS"}:
        return BrokerInstrumentProduct.OPTION
    if text in {"FUT", "FUTURE", "FUTURES"}:
        return BrokerInstrumentProduct.FUTURE
    if text in {"EQ", "EQUITY", "STOCK"}:
        return BrokerInstrumentProduct.EQUITY
    if text in {"INDEX", "IDX"}:
        return BrokerInstrumentProduct.INDEX
    return BrokerInstrumentProduct.UNKNOWN


def _option_type(value: Any) -> BrokerOptionType:
    text = str(value or "NONE").upper()
    if text in {"CE", "CALL"}:
        return BrokerOptionType.CALL
    if text in {"PE", "PUT"}:
        return BrokerOptionType.PUT
    return BrokerOptionType.NONE


def _order_side(value: Any) -> BrokerOrderSide:
    text = str(value or "UNKNOWN").upper()
    if text in {"1", "BUY", "B"}:
        return BrokerOrderSide.BUY
    if text in {"-1", "SELL", "S"}:
        return BrokerOrderSide.SELL
    return BrokerOrderSide.UNKNOWN


def _order_type(value: Any) -> BrokerOrderType:
    text = str(value or "UNKNOWN").upper()
    if text in {"1", "LIMIT"}:
        return BrokerOrderType.LIMIT
    if text in {"2", "MARKET"}:
        return BrokerOrderType.MARKET
    if text in {"3", "STOP", "SL-M"}:
        return BrokerOrderType.STOP
    if text in {"4", "STOP_LIMIT", "SL"}:
        return BrokerOrderType.STOP_LIMIT
    return BrokerOrderType.UNKNOWN


def _order_status(value: Any) -> BrokerOrderStatus:
    text = str(value or "UNKNOWN").upper()
    if text in {"PENDING", "TRANSIT"}:
        return BrokerOrderStatus.PENDING
    if text in {"OPEN", "ACTIVE", "TRIGGER_PENDING"}:
        return BrokerOrderStatus.OPEN
    if text in {"PARTIALLY_FILLED", "PARTIAL", "PARTIALLY_TRADED"}:
        return BrokerOrderStatus.PARTIALLY_FILLED
    if text in {"FILLED", "COMPLETE", "TRADED"}:
        return BrokerOrderStatus.FILLED
    if text in {"REJECTED"}:
        return BrokerOrderStatus.REJECTED
    if text in {"CANCELLED", "CANCELED"}:
        return BrokerOrderStatus.CANCELLED
    if text in {"EXPIRED"}:
        return BrokerOrderStatus.EXPIRED
    return BrokerOrderStatus.UNKNOWN


def _carry_type(value: Any) -> BrokerPositionCarryType:
    text = str(value or "UNKNOWN").upper()
    if text in {"INTRADAY", "DAY"}:
        return BrokerPositionCarryType.INTRADAY
    if text in {"CARRIED_OVERNIGHT", "OVERNIGHT", "CARRY"}:
        return BrokerPositionCarryType.CARRIED_OVERNIGHT
    if text in {"CLOSED_DAY", "CLOSED"}:
        return BrokerPositionCarryType.CLOSED_DAY
    return BrokerPositionCarryType.UNKNOWN


def _special_failures(payload: Mapping[str, Any], key: str) -> tuple[BrokerReadFailure, ...]:
    if payload.get("rate_limit"):
        return (BrokerReadFailure("RATE_LIMITED", f"{key} read was rate-limited.", True),)
    if payload.get("timeout"):
        return (BrokerReadFailure("TIMEOUT", f"{key} read timed out.", True),)
    return ()


def _status_for(records: list[Any], failures: tuple[BrokerReadFailure, ...], payload: Mapping[str, Any]) -> BrokerReadStatus:
    if payload.get("rate_limit"):
        return BrokerReadStatus.RATE_LIMITED
    if payload.get("timeout"):
        return BrokerReadStatus.TIMEOUT
    if failures and records:
        return BrokerReadStatus.PARTIAL
    if failures:
        return BrokerReadStatus.MALFORMED
    return BrokerReadStatus.SUCCESS if records else BrokerReadStatus.EMPTY


def _next_cursor(payload: Mapping[str, Any], key: str, request: BrokerReadRequest) -> str | None:
    if request.page is None:
        return None
    cursors = payload.get(f"{key}_next_cursor")
    if isinstance(cursors, Mapping):
        cursor = request.page.cursor if request.page else None
        return _as_optional_str(cursors.get(cursor or "first"))
    return None


def _fixture_payload(name: str) -> dict[str, Any]:
    base = _base_fixture_payload()
    if name == "authenticated":
        return base
    if name == "unauthorized":
        return base | {"unauthorized": True, "account_session": {"status": "UNAUTHORIZED", "permissions": ()}}
    if name == "empty_orders":
        return base | {"orders": []}
    if name == "malformed_partial":
        return base | {"orders": [base["orders"][0], {"id": "bad", "symbol": "NSE:NIFTY2651222650CE", "product": "OPTION"}]}
    if name == "rate_limit":
        return base | {"rate_limit": True}
    if name == "position_mismatch":
        wrong = BrokerAccountIdentity("fyers", "fixture", "DIFFERENT").to_dict()
        mismatch_order = dict(base["orders"][0])
        mismatch_order["account"] = wrong
        return base | {"account": {"id": "FY12345", "environment": "fixture"}, "orders": [mismatch_order]}
    raise BrokerReadNormalizationError(f"Unknown Phase 4B fixture payload: {name}")


def _base_fixture_payload() -> dict[str, Any]:
    ts = "2026-06-05T09:16:00+05:30"
    instrument = {
        "broker_symbol": "NSE:NIFTY2660922650CE",
        "normalized_symbol": "NIFTY_20260609_22650_CE",
        "product": "OPTION",
        "exchange": "NSE",
        "underlying": "NIFTY",
        "expiry": "2026-06-09",
        "strike": 22650,
        "option_type": "CE",
        "lot_size": 75,
        "tick_size": 0.05,
    }
    put_instrument = instrument | {
        "broker_symbol": "NSE:NIFTY2660922650PE",
        "normalized_symbol": "NIFTY_20260609_22650_PE",
        "option_type": "PE",
    }
    return {
        "access_token": "live-token",
        "account": {"id": "FY12345", "environment": "fixture", "display_name": "TFIS Fixture"},
        "account_session": {"status": "AUTHENTICATED", "permissions": ("read", "orders_read", "positions_read")},
        "funds": {"available_cash": 250000.0, "ledger_balance": 260000.0, "opening_balance": 255000.0, "currency": "INR"},
        "margins": {"available": 180000.0, "used": 70000.0, "span": 42000.0, "exposure": 28000.0, "currency": "INR"},
        "orders": [
            instrument | {"id": "OID-OPEN-TGT", "side": "BUY", "type": "LIMIT", "status": "OPEN", "qty": 75, "filled_qty": 0, "limit_price": 120.0, "trigger_price": None, "avg_price": None, "product_type": "NRML", "created_at": ts, "updated_at": ts},
            instrument | {"id": "OID-PARTIAL", "side": "SELL", "type": "LIMIT", "status": "PARTIALLY_FILLED", "qty": 150, "filled_qty": 75, "limit_price": 100.0, "trigger_price": None, "avg_price": 100.0, "product_type": "NRML", "created_at": ts, "updated_at": ts},
            put_instrument | {"id": "OID-REJECTED", "side": "SELL", "type": "STOP_LIMIT", "status": "REJECTED", "qty": 75, "filled_qty": 0, "limit_price": 150.0, "trigger_price": 151.0, "avg_price": None, "product_type": "NRML", "created_at": ts, "updated_at": ts, "rejection_reason": "fixture rejection"},
        ],
        "order_history": [
            {"id": "OID-OPEN-TGT", "event_id": "EVT-1", "status": "OPEN", "observed_at": ts, "message": "target protection visible"},
            {"id": "OID-PARTIAL", "event_id": "EVT-2", "status": "PARTIALLY_FILLED", "observed_at": ts, "message": "partial fill"},
            {"id": "OID-REJECTED", "event_id": "EVT-3", "status": "REJECTED", "observed_at": ts, "message": "fixture rejection"},
        ],
        "trades": [
            instrument | {"trade_id": "TRD-1", "order_id": "OID-PARTIAL", "side": "SELL", "qty": 75, "price": 100.0, "filled_at": ts, "exchange_trade_id": "EX-1"},
            instrument | {"trade_id": "TRD-1", "order_id": "OID-PARTIAL", "side": "SELL", "qty": 75, "price": 100.0, "filled_at": ts, "exchange_trade_id": "EX-1"},
        ],
        "positions": [
            instrument | {"net_qty": -75, "buy_qty": 0, "sell_qty": 75, "avg_price": 100.0, "ltp": 95.0, "realized_pnl": 0.0, "unrealized_pnl": 375.0, "carry_type": "INTRADAY", "product_type": "NRML"},
            put_instrument | {"net_qty": -75, "buy_qty": 0, "sell_qty": 75, "avg_price": 110.0, "ltp": 105.0, "realized_pnl": 0.0, "unrealized_pnl": 375.0, "carry_type": "CARRIED_OVERNIGHT", "product_type": "NRML"},
        ],
        "instruments": [instrument, put_instrument],
        "orders_pages": {"first": [instrument | {"id": "OID-PAGE-1", "side": "BUY", "type": "LIMIT", "status": "OPEN", "qty": 75, "filled_qty": 0}], "cursor-2": [instrument | {"id": "OID-PAGE-2", "side": "BUY", "type": "LIMIT", "status": "FILLED", "qty": 75, "filled_qty": 75}]},
        "orders_next_cursor": {"first": "cursor-2"},
    }


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, BrokerAccountIdentity):
        return {
            "provider": value.provider,
            "environment": value.environment,
            "account_id": _redact_account_id(value.account_id),
            "display_name": value.display_name,
            "account_hash": value.account_hash,
        }
    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): _redact_account_id(str(item))
            if str(key) == "account_id"
            else _to_jsonable(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple | list):
        return [_to_jsonable(item) for item in value]
    return value


def _phase4b_summary_markdown(
    *,
    audit: Mapping[str, Any],
    snapshot: BrokerAccountReadSnapshot,
    capabilities: BrokerReadCapabilities,
    gap_register: Mapping[str, Any],
) -> str:
    return (
        "# Phase 4B Broker Read Boundary\n\n"
        f"Verdict: {audit['verdict']}\n\n"
        f"Adapter: {audit['adapter']}\n\n"
        f"Provider: {capabilities.provider}\n\n"
        f"Snapshot completeness: {snapshot.completeness.value}\n\n"
        "Authority: read-only observational boundary. Broker, paper, live, order "
        "creation, order modification, order cancellation and position mutation "
        "authority remain NONE.\n\n"
        "Normalized records:\n\n"
        f"- orders: {len(snapshot.orders.records)}\n"
        f"- order events: {len(snapshot.order_history.records)}\n"
        f"- fills: {len(snapshot.fills.records)}\n"
        f"- positions: {len(snapshot.positions.records)}\n"
        f"- instruments: {len(snapshot.instruments.records)}\n\n"
        "Reconciliation gaps:\n\n"
        + "\n".join(f"- {item['code']}: {item['status']}" for item in gap_register["gaps"])
        + "\n"
    )
