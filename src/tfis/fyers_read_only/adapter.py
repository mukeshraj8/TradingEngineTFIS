from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Protocol

from tfis.broker.authentication import ValidatedBrokerSession

from .models import (
    CompletedCandleSet,
    FyersMarketDepth,
    FyersOptionChainSnapshot,
    FyersQuote,
    InstrumentMasterRecord,
    canonical_hash,
    normalize_history_payload,
    normalize_market_depth_payload,
    normalize_option_chain_payload,
    normalize_quote_payload,
    normalize_symbol_master_rows,
)


SENSITIVE_FRAGMENTS = (
    "access_token",
    "app_id",
    "authorization",
    "auth_code",
    "app_secret",
    "client_secret",
    "cookie",
    "display_name",
    "email",
    "fy_id",
    "mobile",
    "name",
    "pan",
    "password",
    "pin",
    "pin_change_date",
    "pwd",
    "refresh_token",
    "secret",
    "session",
    "totp",
)


class FyersReadOnlyStatus(str, Enum):
    SUCCESS = "SUCCESS"
    AUTHENTICATED = "AUTHENTICATED"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    MALFORMED = "MALFORMED"
    UNAVAILABLE = "UNAVAILABLE"


class FyersReadOnlyError(RuntimeError):
    def __init__(self, status: FyersReadOnlyStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True, slots=True)
class FyersReadOnlyCredentials:
    app_id: str
    access_token: str
    client_id: str | None = None

    @classmethod
    def from_env(
        cls,
        *,
        app_id_env: str = "FYERS_APP_ID",
        access_token_env: str = "FYERS_ACCESS_TOKEN",
        client_id_env: str = "FYERS_CLIENT_ID",
    ) -> "FyersReadOnlyCredentials":
        app_id = os.getenv(app_id_env, "").strip()
        access_token = os.getenv(access_token_env, "").strip()
        client_id = os.getenv(client_id_env, "").strip() or None
        if not app_id or not access_token:
            raise FyersReadOnlyError(
                FyersReadOnlyStatus.AUTHENTICATION_REQUIRED,
                "Set FYERS_APP_ID and FYERS_ACCESS_TOKEN through the approved local secret mechanism.",
            )
        return cls(app_id=app_id, access_token=access_token, client_id=client_id)

    def redacted(self) -> dict[str, str | None]:
        return {
            "app_id": self.app_id,
            "access_token": "REDACTED",
            "client_id": self.client_id,
        }


@dataclass(frozen=True, slots=True)
class FyersReadOnlyResult:
    status: FyersReadOnlyStatus
    captured_at: datetime
    payload: Any = None
    warnings: tuple[str, ...] = ()
    source_hash: str | None = None
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return redact_sensitive(
            {
                "status": self.status.value,
                "captured_at": self.captured_at.isoformat(),
                "payload": _to_jsonable(self.payload),
                "warnings": list(self.warnings),
                "source_hash": self.source_hash,
                "retry_count": self.retry_count,
            }
        )


class FyersLikeClient(Protocol):
    def get_profile(self) -> Mapping[str, Any]:
        ...

    def history(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        ...

    def quotes(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        ...

    def optionchain(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


class FyersReadOnlyAdapter:
    """FYERS market/reference-data adapter with no order-write surface."""

    provider = "fyers"

    def __init__(
        self,
        *,
        credentials: FyersReadOnlyCredentials | None = None,
        client: FyersLikeClient | None = None,
        now_provider: Callable[[], datetime] | None = None,
        timeout_seconds: float = 15.0,
        max_retries: int = 2,
        symbol_master_downloader: Callable[[str], str] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._credentials = credentials
        self._client = client
        self._now = now_provider or (lambda: datetime.now().astimezone())
        self._timeout_seconds = timeout_seconds
        self._max_retries = max(0, int(max_retries))
        self._symbol_master_downloader = symbol_master_downloader or self._download_symbol_master
        self._sleeper = sleeper

    @classmethod
    def from_env(cls, **kwargs: Any) -> "FyersReadOnlyAdapter":
        return cls(credentials=FyersReadOnlyCredentials.from_env(), **kwargs)

    @classmethod
    def from_validated_session(cls, session: ValidatedBrokerSession, **kwargs: Any) -> "FyersReadOnlyAdapter":
        return cls(client=session.client, **kwargs)

    def validate_session(self) -> FyersReadOnlyResult:
        if self._credentials is None and self._client is None:
            return FyersReadOnlyResult(
                status=FyersReadOnlyStatus.AUTHENTICATION_REQUIRED,
                captured_at=self._now(),
                warnings=("FYERS_APP_ID and FYERS_ACCESS_TOKEN are required for real capture.",),
            )
        client = self._require_client()
        try:
            body, retries = self._call_with_retries(client.get_profile)
        except FyersReadOnlyError as exc:
            return FyersReadOnlyResult(exc.status, self._now(), warnings=(str(exc),))
        status = FyersReadOnlyStatus.AUTHENTICATED if str(body.get("s", "")).lower() == "ok" else self._status_from_payload(body)
        return FyersReadOnlyResult(
            status=status,
            captured_at=self._now(),
            payload={"profile": "REDACTED"},
            source_hash=canonical_hash(redact_sensitive(body)),
            retry_count=retries,
        )

    def fetch_symbol_master(self, exchange: str) -> FyersReadOnlyResult:
        captured_at = self._now()
        try:
            raw = self._symbol_master_downloader(exchange)
            records = normalize_symbol_master_rows(
                raw,
                exchange=exchange,
                source_version=f"fyers-symbol-master:{exchange}:{captured_at.date().isoformat()}",
                downloaded_at=captured_at,
            )
        except TimeoutError as exc:
            return FyersReadOnlyResult(FyersReadOnlyStatus.TIMEOUT, captured_at, warnings=(str(exc),))
        except Exception as exc:
            return FyersReadOnlyResult(FyersReadOnlyStatus.MALFORMED, captured_at, warnings=(str(exc),))
        return FyersReadOnlyResult(
            status=FyersReadOnlyStatus.SUCCESS,
            captured_at=captured_at,
            payload=records,
            source_hash=canonical_hash([record.to_dict() for record in records]),
        )

    def fetch_historical_candles(
        self,
        *,
        symbol: str,
        resolution: str,
        range_from: date,
        range_to: date,
        cont_flag: bool = False,
        exclude_incomplete_after: datetime | None = None,
    ) -> FyersReadOnlyResult:
        client = self._require_client()
        request = {
            "symbol": symbol,
            "resolution": resolution,
            "date_format": "1",
            "range_from": range_from.isoformat(),
            "range_to": range_to.isoformat(),
            "cont_flag": "1" if cont_flag else "0",
        }
        try:
            body, retries = self._call_with_retries(lambda: client.history(request))
            candles = normalize_history_payload(
                body,
                symbol=symbol,
                interval=resolution,
                source_id=f"fyers:history:{symbol}",
                as_of=self._now(),
                exclude_incomplete_after=exclude_incomplete_after,
            )
        except FyersReadOnlyError as exc:
            return FyersReadOnlyResult(exc.status, self._now(), warnings=(str(exc),))
        except Exception as exc:
            return FyersReadOnlyResult(FyersReadOnlyStatus.MALFORMED, self._now(), warnings=(str(exc),))
        return FyersReadOnlyResult(
            FyersReadOnlyStatus.SUCCESS,
            self._now(),
            payload=candles,
            source_hash=candles.source_hash,
            retry_count=retries,
        )

    def fetch_quotes(self, symbols: tuple[str, ...]) -> FyersReadOnlyResult:
        client = self._require_client()
        request = {"symbols": ",".join(symbols)}
        try:
            body, retries = self._call_with_retries(lambda: client.quotes(request))
            quotes = tuple(normalize_quote_payload(body, symbol=symbol) for symbol in symbols)
        except FyersReadOnlyError as exc:
            return FyersReadOnlyResult(exc.status, self._now(), warnings=(str(exc),))
        except Exception as exc:
            return FyersReadOnlyResult(FyersReadOnlyStatus.MALFORMED, self._now(), warnings=(str(exc),))
        return FyersReadOnlyResult(FyersReadOnlyStatus.SUCCESS, self._now(), payload=quotes, source_hash=canonical_hash(body), retry_count=retries)

    def fetch_market_depth(self, symbols: tuple[str, ...]) -> FyersReadOnlyResult:
        client = self._require_client()
        depth = getattr(client, "depth", None)
        if depth is None:
            return FyersReadOnlyResult(FyersReadOnlyStatus.UNAVAILABLE, self._now(), warnings=("FYERS client does not expose depth().",))
        request = {"symbol": ",".join(symbols), "ohlcv_flag": "1"}
        try:
            body, retries = self._call_with_retries(lambda: depth(request))
            records = tuple(normalize_market_depth_payload(body, symbol=symbol) for symbol in symbols)
        except FyersReadOnlyError as exc:
            return FyersReadOnlyResult(exc.status, self._now(), warnings=(str(exc),))
        except Exception as exc:
            return FyersReadOnlyResult(FyersReadOnlyStatus.MALFORMED, self._now(), warnings=(str(exc),))
        return FyersReadOnlyResult(FyersReadOnlyStatus.SUCCESS, self._now(), payload=records, source_hash=canonical_hash(body), retry_count=retries)

    def fetch_option_chain(
        self,
        *,
        underlying: str,
        expiry: date | None = None,
        strike_count: int = 50,
        instrument_records: Iterable[InstrumentMasterRecord] = (),
    ) -> FyersReadOnlyResult:
        client = self._require_client()
        records = tuple(instrument_records)
        request: dict[str, Any] = {"symbol": underlying, "strikecount": int(strike_count)}
        if expiry is not None:
            request["timestamp"] = _expiry_timestamp_from_records(records, expiry) or str(
                int(datetime.combine(expiry, datetime.min.time()).timestamp())
            )
        try:
            body, retries = self._call_with_retries(lambda: client.optionchain(request))
            chain = normalize_option_chain_payload(
                body,
                underlying=underlying.split(":")[-1],
                expiry=expiry,
                instrument_records=records,
                captured_at=self._now(),
            )
        except FyersReadOnlyError as exc:
            return FyersReadOnlyResult(exc.status, self._now(), warnings=(str(exc),))
        except Exception as exc:
            return FyersReadOnlyResult(FyersReadOnlyStatus.MALFORMED, self._now(), warnings=(str(exc),))
        return FyersReadOnlyResult(FyersReadOnlyStatus.SUCCESS, self._now(), payload=chain, source_hash=chain.source_hash, retry_count=retries)

    def resolve_contracts(
        self,
        *,
        records: Iterable[InstrumentMasterRecord],
        underlying: str,
        expiry: date,
        option_type: str | None = None,
    ) -> tuple[InstrumentMasterRecord, ...]:
        normalized_option = option_type.upper() if option_type else None
        return tuple(
            record
            for record in records
            if record.underlying == underlying.upper()
            and record.expiry == expiry
            and (normalized_option is None or record.option_type == normalized_option)
        )

    def retrieve_source_health(self) -> FyersReadOnlyResult:
        return self.validate_session()

    def _require_client(self) -> FyersLikeClient:
        if self._client is not None:
            return self._client
        if self._credentials is None:
            raise FyersReadOnlyError(
                FyersReadOnlyStatus.AUTHENTICATION_REQUIRED,
                "FYERS read-only capture requires approved local credentials.",
            )
        try:
            from fyers_apiv3 import fyersModel
        except Exception as exc:
            raise FyersReadOnlyError(
                FyersReadOnlyStatus.AUTHENTICATION_REQUIRED,
                "Install/use the existing FYERS environment before real read-only capture.",
            ) from exc
        self._client = fyersModel.FyersModel(
            client_id=self._credentials.app_id,
            token=self._credentials.access_token,
            log_path="",
        )
        return self._client

    def _call_with_retries(self, func: Callable[[], Mapping[str, Any]]) -> tuple[Mapping[str, Any], int]:
        last_status = FyersReadOnlyStatus.UNAVAILABLE
        last_message = "unavailable"
        for attempt in range(self._max_retries + 1):
            try:
                body = func()
            except TimeoutError as exc:
                last_status = FyersReadOnlyStatus.TIMEOUT
                last_message = str(exc)
            except Exception as exc:
                last_status = FyersReadOnlyStatus.UNAVAILABLE
                last_message = str(exc)
            else:
                status = self._status_from_payload(body)
                if status in {FyersReadOnlyStatus.SUCCESS, FyersReadOnlyStatus.AUTHENTICATED}:
                    return body, attempt
                if status in {FyersReadOnlyStatus.AUTHENTICATION_REQUIRED, FyersReadOnlyStatus.TOKEN_EXPIRED, FyersReadOnlyStatus.MALFORMED}:
                    raise FyersReadOnlyError(status, str(body.get("message") or body.get("errmsg") or status.value))
                last_status = status
                last_message = str(body.get("message") or body.get("errmsg") or status.value)
            if attempt < self._max_retries:
                self._sleeper(min(1.0, 0.1 * (attempt + 1)))
        raise FyersReadOnlyError(last_status, last_message)

    @staticmethod
    def _status_from_payload(body: Mapping[str, Any]) -> FyersReadOnlyStatus:
        status = str(body.get("s") or body.get("status") or "").lower()
        code = str(body.get("code") or "").lower()
        message = str(body.get("message") or body.get("errmsg") or "").lower()
        if status == "ok" or status == "success":
            return FyersReadOnlyStatus.SUCCESS
        if "token" in message and ("expired" in message or "invalid" in message):
            return FyersReadOnlyStatus.TOKEN_EXPIRED
        if code in {"-16", "401"} or "unauthorized" in message:
            return FyersReadOnlyStatus.AUTHENTICATION_REQUIRED
        if "rate" in message or code == "429":
            return FyersReadOnlyStatus.RATE_LIMITED
        if status == "error":
            return FyersReadOnlyStatus.MALFORMED
        return FyersReadOnlyStatus.SUCCESS

    def _download_symbol_master(self, exchange: str) -> str:
        exchange_key = exchange.upper()
        urls = {
            "NSE": "https://public.fyers.in/sym_details/NSE_CM.csv",
            "NSEFO": "https://public.fyers.in/sym_details/NSE_FO.csv",
        }
        if exchange_key not in urls:
            raise ValueError(f"Unsupported FYERS symbol-master exchange: {exchange}")
        with urllib.request.urlopen(urls[exchange_key], timeout=self._timeout_seconds) as response:
            return response.read().decode("utf-8")


def _expiry_timestamp_from_records(records: Iterable[InstrumentMasterRecord], expiry: date) -> str | None:
    for record in records:
        if record.expiry != expiry:
            continue
        raw_expiry = record.source_row.get("expiry") if isinstance(record.source_row, Mapping) else None
        if raw_expiry and str(raw_expiry).isdigit():
            return str(raw_expiry)
    return None


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            redacted[str(key)] = "REDACTED" if any(fragment in lowered for fragment in SENSITIVE_FRAGMENTS) else redact_sensitive(item)
        return redacted
    if isinstance(value, tuple | list):
        return [redact_sensitive(item) for item in value]
    return value


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _to_jsonable(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, tuple | list):
        return [_to_jsonable(item) for item in value]
    return value
