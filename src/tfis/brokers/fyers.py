from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from tfis.domain.enums import OptionType
from tfis.normalized_events import (
    CalendarContextEvent,
    EventEnvelope,
    OptionChainContract,
    OptionChainSnapshotEvent,
    PaperEventType,
    SelectedContractBarEvent,
    SelectedContractQuoteEvent,
    UnderlyingQuoteEvent,
)

from .base import (
    BrokerAdapter,
    BrokerConnectionError,
    BrokerConnectionState,
    BrokerCredentialsError,
    BrokerHealthEvent,
    BrokerNormalizationError,
    NormalizedBrokerEvent,
    UnderlyingHistoryBar,
)


_IST = ZoneInfo("Asia/Kolkata")
_MONTH_TO_FYERS = {
    1: "1",
    2: "2",
    3: "3",
    4: "4",
    5: "5",
    6: "6",
    7: "7",
    8: "8",
    9: "9",
    10: "A",
    11: "B",
    12: "C",
}
_FYERS_TO_MONTH = {value: key for key, value in _MONTH_TO_FYERS.items()}


@dataclass(frozen=True, slots=True)
class FyersCredentials:
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
    ) -> "FyersCredentials":
        app_id = (os.getenv(app_id_env) or "").strip()
        access_token = (os.getenv(access_token_env) or "").strip()
        client_id = (os.getenv(client_id_env) or "").strip() or None
        if not app_id or not access_token:
            raise BrokerCredentialsError(
                "Fyers live-paper ingress requires FYERS_APP_ID and "
                "FYERS_ACCESS_TOKEN unless sample payload mode is used."
            )
        return cls(
            app_id=app_id,
            access_token=access_token,
            client_id=client_id,
        )


class FyersBrokerAdapter(BrokerAdapter):
    broker_name = "fyers"

    def __init__(
        self,
        *,
        client: Any | None = None,
        credentials: FyersCredentials | None = None,
        payloads: dict[str, Any] | None = None,
        source_timezone: str = "Asia/Kolkata",
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._client = client
        self._credentials = credentials
        self._payloads = payloads or {}
        self._timezone = source_timezone
        self._tzinfo = ZoneInfo(source_timezone)
        self._now_provider = now_provider or (lambda: datetime.now(tz=self._tzinfo))
        self._connected = False
        self._subscribed_symbols: tuple[str, ...] = ()
        self._reconnect_attempts = 0

    @classmethod
    def from_payload_file(
        cls,
        path: str | Path,
        *,
        source_timezone: str = "Asia/Kolkata",
    ) -> "FyersBrokerAdapter":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise BrokerNormalizationError("Fyers payload fixture must be a JSON object.")
        return cls(payloads=payload, source_timezone=source_timezone)

    @staticmethod
    def normalize_underlying_symbol(symbol: str) -> str:
        cleaned = symbol.strip().upper()
        if cleaned in {"NIFTY", "NSE:NIFTY50-INDEX", "NSE:NIFTY-INDEX"}:
            return "NIFTY"
        raise BrokerNormalizationError(f"Unsupported FYERS underlying symbol: {symbol}")

    @classmethod
    def normalize_option_symbol(cls, symbol: str) -> str:
        cleaned = symbol.strip().upper()
        if not cleaned.startswith("NSE:NIFTY"):
            raise BrokerNormalizationError(f"Unsupported FYERS option symbol: {symbol}")
        body = cleaned.replace("NSE:NIFTY", "", 1)
        if len(body) < 8 or not (body.endswith("CE") or body.endswith("PE")):
            raise BrokerNormalizationError(f"Malformed FYERS option symbol: {symbol}")
        option_type = body[-2:]
        strike_text = body[5:-2]
        expiry_id = body[:5]
        yy = int(expiry_id[:2])
        month_token = expiry_id[2]
        day = int(expiry_id[3:5])
        month = _FYERS_TO_MONTH.get(month_token)
        if month is None:
            raise BrokerNormalizationError(f"Unsupported FYERS month token: {month_token}")
        expiry = date(2000 + yy, month, day)
        strike = int(strike_text)
        return f"NIFTY_{expiry.isoformat().replace('-', '')}_{strike}_{option_type}"

    @classmethod
    def to_fyers_option_symbol(
        cls,
        normalized_symbol: str,
    ) -> str:
        prefix, expiry_text, strike_text, option_type = normalized_symbol.split("_", 3)
        if prefix.upper() != "NIFTY":
            raise BrokerNormalizationError(
                f"Unsupported normalized option symbol for FYERS: {normalized_symbol}"
            )
        expiry = date.fromisoformat(
            f"{expiry_text[0:4]}-{expiry_text[4:6]}-{expiry_text[6:8]}"
        )
        month_token = _MONTH_TO_FYERS[expiry.month]
        expiry_id = f"{str(expiry.year)[2:]}{month_token}{expiry.day:02d}"
        return f"NSE:NIFTY{expiry_id}{int(strike_text)}{option_type.upper()}"

    def connect(self) -> None:
        if self._payloads:
            self._connected = True
            return
        if self._client is None:
            self._client = self._build_default_client()
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False
        if self._client is not None and hasattr(self._client, "disconnect"):
            self._client.disconnect()

    def subscribe_symbols(self, symbols: tuple[str, ...]) -> tuple[str, ...]:
        accepted = tuple(dict.fromkeys(str(symbol) for symbol in symbols if str(symbol)))
        self._subscribed_symbols = accepted
        if self._payloads:
            return accepted
        if self._client is not None and hasattr(self._client, "subscribe_symbols"):
            self._client.subscribe_symbols(accepted)
        elif self._client is not None and hasattr(self._client, "subscribe"):
            self._client.subscribe(symbol=accepted)
        return accepted

    def get_underlying_quote(
        self,
        symbol: str,
        *,
        session_date: date,
    ) -> UnderlyingQuoteEvent:
        raw_symbol = self._to_fyers_underlying_symbol(symbol)
        if self._payloads:
            payload = self._payloads.get("underlying_quote")
        else:
            if self._client is None:
                raise BrokerConnectionError("Fyers client is not connected.")
            payload = self._client.quotes({"symbols": raw_symbol})
        return self._normalize_quote_payload(
            payload,
            raw_symbol=raw_symbol,
            session_date=session_date,
            quote_kind="underlying",
        )

    def get_option_chain(
        self,
        symbol: str,
        expiry: date,
        *,
        session_date: date,
    ) -> OptionChainSnapshotEvent:
        raw_symbol = self._to_fyers_underlying_symbol(symbol)
        if self._payloads:
            payload = self._payloads.get("option_chain")
        else:
            if self._client is None:
                raise BrokerConnectionError("Fyers client is not connected.")
            payload = self._client.optionchain(
                {
                    "symbol": raw_symbol,
                    "strikecount": 10,
                    "timestamp": "",
                }
            )
        return self._normalize_option_chain_payload(
            payload,
            raw_symbol=raw_symbol,
            expiry=expiry,
            session_date=session_date,
        )

    def get_option_quote(
        self,
        option_symbol: str,
        *,
        session_date: date,
    ) -> SelectedContractQuoteEvent:
        raw_symbol = (
            option_symbol
            if option_symbol.upper().startswith("NSE:")
            else self.to_fyers_option_symbol(option_symbol)
        )
        if self._payloads:
            payload = self._payloads.get("selected_contract_quote")
        else:
            if self._client is None:
                raise BrokerConnectionError("Fyers client is not connected.")
            payload = self._client.quotes({"symbols": raw_symbol})
        return self._normalize_quote_payload(
            payload,
            raw_symbol=raw_symbol,
            session_date=session_date,
            quote_kind="selected_contract",
        )

    def get_underlying_bars(
        self,
        symbol: str,
        *,
        session_date: date,
        from_time: time,
        to_time: time,
        interval_minutes: int = 1,
    ) -> tuple[UnderlyingHistoryBar, ...]:
        raw_symbol = self._to_fyers_underlying_symbol(symbol)
        if self._payloads:
            payload = (
                self._payloads.get("underlying_history_bars")
                or self._payloads.get("underlying_bars")
            )
        else:
            if self._client is None:
                raise BrokerConnectionError("Fyers client is not connected.")
            payload = self._client.history(
                {
                    "symbol": raw_symbol,
                    "resolution": str(interval_minutes),
                    "date_format": "1",
                    "range_from": session_date.isoformat(),
                    "range_to": session_date.isoformat(),
                    "cont_flag": "1",
                }
            )
        return self._normalize_underlying_history_payload(
            payload,
            raw_symbol=raw_symbol,
            session_date=session_date,
            from_time=from_time,
            to_time=to_time,
            interval_minutes=interval_minutes,
        )

    def stream_ticks(self) -> tuple[NormalizedBrokerEvent, ...]:
        if self._payloads:
            stream_payloads = self._payloads.get("stream_ticks", ())
        else:
            if self._client is None:
                raise BrokerConnectionError("Fyers client is not connected.")
            stream_payloads = tuple(self._client.stream_ticks())

        events: list[NormalizedBrokerEvent] = []
        for payload in stream_payloads:
            if not isinstance(payload, dict):
                raise BrokerNormalizationError("Fyers stream payload must be a dict.")
            payload_type = str(payload.get("type", "")).lower()
            session_date = date.fromisoformat(str(payload["session_date"]))
            if payload_type == "selected_contract_bar":
                events.append(self._normalize_selected_contract_bar_payload(payload, session_date))
            elif payload_type == "selected_contract_quote":
                events.append(
                    self._normalize_quote_payload(
                        payload,
                        raw_symbol=str(payload.get("symbol") or payload.get("n")),
                        session_date=session_date,
                        quote_kind="selected_contract",
                    )
                )
            elif payload_type == "underlying_quote":
                events.append(
                    self._normalize_quote_payload(
                        payload,
                        raw_symbol=str(payload.get("symbol") or payload.get("n")),
                        session_date=session_date,
                        quote_kind="underlying",
                    )
                )
        return tuple(events)

    def health(self) -> BrokerHealthEvent:
        payload = self._payloads.get("health") if self._payloads else None
        as_of = self._now_provider()
        if payload is None:
            return BrokerHealthEvent(
                broker_name=self.broker_name,
                as_of=as_of,
                connection_state=(
                    BrokerConnectionState.CONNECTED
                    if self._connected
                    else BrokerConnectionState.DISCONNECTED
                ),
                source_id="fyers:health",
                is_connected=self._connected,
                reconnect_attempts=self._reconnect_attempts,
            )
        return self._normalize_health_payload(payload)

    def reconnect(self) -> BrokerHealthEvent:
        self._reconnect_attempts += 1
        self.disconnect()
        self.connect()
        return self.health()

    def _build_default_client(self) -> Any:
        if self._credentials is None:
            self._credentials = FyersCredentials.from_env()
        try:
            from fyers_apiv3 import fyersModel  # type: ignore
        except Exception as exc:  # pragma: no cover - environment dependent
            raise BrokerConnectionError(
                "fyers_apiv3 is unavailable. Use sample payload mode or install the FYERS SDK."
            ) from exc
        try:
            return fyersModel.FyersModel(
                client_id=self._credentials.app_id,
                token=self._credentials.access_token,
                log_path="",
            )
        except Exception as exc:  # pragma: no cover - environment dependent
            raise BrokerConnectionError(f"Failed to initialize FYERS client: {exc}") from exc

    def _to_fyers_underlying_symbol(self, symbol: str) -> str:
        normalized = symbol.strip().upper()
        if normalized == "NIFTY":
            return "NSE:NIFTY50-INDEX"
        if normalized.startswith("NSE:"):
            return normalized
        raise BrokerNormalizationError(f"Unsupported underlying symbol: {symbol}")

    def _normalize_health_payload(self, payload: dict[str, Any]) -> BrokerHealthEvent:
        return BrokerHealthEvent(
            broker_name=self.broker_name,
            as_of=self._read_datetime(payload.get("as_of") or payload.get("timestamp")),
            connection_state=BrokerConnectionState(
                str(payload.get("connection_state", "CONNECTED")).upper()
            ),
            source_id=str(payload.get("source_id", "fyers:health")),
            is_connected=bool(payload.get("is_connected", True)),
            cooldown_seconds=self._optional_float(payload.get("cooldown_seconds")),
            reconnect_attempts=int(payload.get("reconnect_attempts", self._reconnect_attempts) or 0),
            rate_limit_remaining=self._optional_int(payload.get("rate_limit_remaining")),
            rate_limit_limit=self._optional_int(payload.get("rate_limit_limit")),
            warnings=tuple(str(item) for item in payload.get("warnings", ()) if str(item)),
            diagnostics=tuple(
                str(item) for item in payload.get("diagnostics", ()) if str(item)
            ),
        )

    def _normalize_quote_payload(
        self,
        payload: dict[str, Any] | None,
        *,
        raw_symbol: str,
        session_date: date,
        quote_kind: str,
    ) -> UnderlyingQuoteEvent | SelectedContractQuoteEvent:
        if payload is None:
            raise BrokerNormalizationError(f"Missing FYERS {quote_kind} payload.")

        record = self._extract_single_quote_record(payload, raw_symbol=raw_symbol)
        symbol = str(record.get("symbol") or record.get("n") or raw_symbol)
        values = record.get("v") if isinstance(record.get("v"), dict) else record
        effective_timestamp = self._read_datetime(
            record.get("effective_timestamp")
            or record.get("timestamp")
            or record.get("last_traded_time")
            or record.get("last_traded_time_epoch")
        )
        captured_at = self._read_datetime(
            record.get("captured_at")
            or record.get("received_at")
            or payload.get("captured_at")
            or payload.get("received_at")
        )
        envelope = EventEnvelope(
            event_type=(
                PaperEventType.UNDERLYING_QUOTE
                if quote_kind == "underlying"
                else PaperEventType.SELECTED_CONTRACT_QUOTE
            ),
            session_date=session_date,
            effective_timestamp=effective_timestamp,
            captured_at=captured_at,
            timezone=self._timezone,
            source_type="broker_fyers",
            source_id=str(payload.get("source_id", f"fyers:{quote_kind}_quote")),
            synthetic_fixture=bool(payload.get("synthetic_fixture", False)),
            normalized_by="fyers-adapter-v1",
            source_sequence=self._optional_int(payload.get("source_sequence")),
            data_quality_flags=tuple(str(item) for item in payload.get("data_quality_flags", ())),
        )
        ltp = self._optional_float(values.get("ltp") or values.get("lp"))
        bid = self._optional_float(
            values.get("bid")
            or values.get("bid_price")
            or values.get("bid_price1")
        )
        ask = self._optional_float(
            values.get("ask")
            or values.get("ask_price")
            or values.get("ask_price1")
        )
        volume = self._optional_float(values.get("volume") or values.get("vol_traded_today"))
        oi = self._optional_float(values.get("oi"))
        if quote_kind == "underlying":
            return UnderlyingQuoteEvent(
                envelope=envelope,
                symbol=self.normalize_underlying_symbol(symbol),
                ltp=ltp,
                bid=bid,
                ask=ask,
                volume=volume,
                source_latency_ms=self._optional_int(
                    values.get("source_latency_ms") or values.get("latency_ms")
                ),
            )
        normalized_symbol = self.normalize_option_symbol(symbol)
        expiry = self._optional_date(values.get("expiry") or record.get("expiry"))
        strike = self._optional_float(values.get("strike") or values.get("strike_price"))
        option_type = self._optional_option_type(
            values.get("option_type") or record.get("option_type") or symbol[-2:]
        )
        return SelectedContractQuoteEvent(
            envelope=envelope,
            symbol=normalized_symbol,
            option_type=option_type,
            strike=strike,
            expiry=expiry,
            bid=bid,
            ask=ask,
            ltp=ltp,
            oi=oi,
            volume=volume,
        )

    def _normalize_option_chain_payload(
        self,
        payload: dict[str, Any] | None,
        *,
        raw_symbol: str,
        expiry: date,
        session_date: date,
    ) -> OptionChainSnapshotEvent:
        if payload is None:
            raise BrokerNormalizationError("Missing FYERS option-chain payload.")
        chain = (
            payload.get("optionsChain")
            or payload.get("data", {}).get("optionsChain")
            or payload.get("data", {}).get("options_chain")
            or payload.get("contracts")
        )
        if not isinstance(chain, list):
            raise BrokerNormalizationError("FYERS option-chain payload is missing optionsChain.")
        effective_timestamp = self._read_datetime(
            payload.get("effective_timestamp")
            or payload.get("timestamp")
            or payload.get("last_traded_time")
        )
        captured_at = self._read_datetime(payload.get("captured_at") or payload.get("received_at"))
        envelope = EventEnvelope(
            event_type=PaperEventType.OPTION_CHAIN_SNAPSHOT,
            session_date=session_date,
            effective_timestamp=effective_timestamp,
            captured_at=captured_at,
            timezone=self._timezone,
            source_type="broker_fyers",
            source_id=str(payload.get("source_id", "fyers:option_chain")),
            synthetic_fixture=bool(payload.get("synthetic_fixture", False)),
            normalized_by="fyers-adapter-v1",
            source_sequence=self._optional_int(payload.get("source_sequence")),
            data_quality_flags=tuple(str(item) for item in payload.get("data_quality_flags", ())),
        )
        contracts: list[OptionChainContract] = []
        for raw_contract in chain:
            if not isinstance(raw_contract, dict):
                continue
            raw_option_symbol = str(
                raw_contract.get("symbol")
                or raw_contract.get("option_symbol")
                or raw_contract.get("n")
                or ""
            )
            if not raw_option_symbol:
                continue
            try:
                normalized_symbol = self.normalize_option_symbol(raw_option_symbol)
            except BrokerNormalizationError:
                # Live FYERS option-chain responses can include the underlying/index
                # row alongside actual option contracts. Ignore non-option entries.
                continue
            contracts.append(
                OptionChainContract(
                    symbol=normalized_symbol,
                    option_type=self._optional_option_type(
                        raw_contract.get("option_type") or raw_option_symbol[-2:]
                    ),
                    strike=self._optional_float(
                        raw_contract.get("strike")
                        or raw_contract.get("strike_price")
                    ),
                    expiry=self._optional_date(raw_contract.get("expiry")) or expiry,
                    bid=self._optional_float(
                        raw_contract.get("bid")
                        or raw_contract.get("bid_price")
                        or raw_contract.get("bid_price1")
                    ),
                    ask=self._optional_float(
                        raw_contract.get("ask")
                        or raw_contract.get("ask_price")
                        or raw_contract.get("ask_price1")
                    ),
                    ltp=self._optional_float(raw_contract.get("ltp") or raw_contract.get("lp")),
                    oi=self._optional_float(raw_contract.get("oi")),
                    volume=self._optional_float(
                        raw_contract.get("volume") or raw_contract.get("vol_traded_today")
                    ),
                )
            )
        return OptionChainSnapshotEvent(
            envelope=envelope,
            underlying_symbol=self.normalize_underlying_symbol(raw_symbol),
            expiry=expiry,
            contracts=tuple(contracts),
        )

    def _normalize_selected_contract_bar_payload(
        self,
        payload: dict[str, Any],
        session_date: date,
    ) -> SelectedContractBarEvent:
        raw_symbol = str(payload.get("symbol") or payload.get("n") or "")
        if not raw_symbol:
            raise BrokerNormalizationError("Selected-contract bar payload is missing symbol.")
        envelope = EventEnvelope(
            event_type=PaperEventType.SELECTED_CONTRACT_BAR,
            session_date=session_date,
            effective_timestamp=self._read_datetime(
                payload.get("effective_timestamp")
                or payload.get("bar_end")
                or payload.get("timestamp")
            ),
            captured_at=self._read_datetime(payload.get("captured_at") or payload.get("received_at")),
            timezone=self._timezone,
            source_type="broker_fyers",
            source_id=str(payload.get("source_id", "fyers:selected_contract_bar")),
            synthetic_fixture=bool(payload.get("synthetic_fixture", False)),
            normalized_by="fyers-adapter-v1",
            source_sequence=self._optional_int(payload.get("source_sequence")),
            data_quality_flags=tuple(str(item) for item in payload.get("data_quality_flags", ())),
        )
        return SelectedContractBarEvent(
            envelope=envelope,
            symbol=self.normalize_option_symbol(raw_symbol),
            open=self._optional_float(payload.get("open")),
            high=self._optional_float(payload.get("high")),
            low=self._optional_float(payload.get("low")),
            close=self._optional_float(payload.get("close")),
            bar_start=self._read_datetime(payload.get("bar_start")),
            bar_end=self._read_datetime(payload.get("bar_end")),
            volume=self._optional_float(payload.get("volume")),
        )

    def _normalize_underlying_history_payload(
        self,
        payload: dict[str, Any] | list[dict[str, Any]] | None,
        *,
        raw_symbol: str,
        session_date: date,
        from_time: time,
        to_time: time,
        interval_minutes: int,
    ) -> tuple[UnderlyingHistoryBar, ...]:
        if payload is None:
            raise BrokerNormalizationError("Missing FYERS underlying history payload.")
        candles = self._extract_history_candles(payload)
        if not candles:
            raise BrokerNormalizationError("FYERS underlying history payload returned no candles.")

        day_start = datetime.combine(session_date, time(0, 0), tzinfo=self._tzinfo)
        from_dt = datetime.combine(session_date, from_time, tzinfo=self._tzinfo)
        to_dt = datetime.combine(session_date, to_time, tzinfo=self._tzinfo)
        bars: list[UnderlyingHistoryBar] = []
        normalized_symbol = self.normalize_underlying_symbol(raw_symbol)
        source_id = (
            str(payload.get("source_id"))
            if isinstance(payload, dict) and payload.get("source_id")
            else "fyers:underlying_history"
        )
        interval_delta = timedelta(minutes=max(1, int(interval_minutes)))
        for candle in candles:
            if not isinstance(candle, (list, tuple)) or len(candle) < 6:
                raise BrokerNormalizationError("FYERS history candle must contain at least 6 values.")
            epoch = int(candle[0])
            bar_start = datetime.fromtimestamp(epoch, tz=self._tzinfo)
            if bar_start.date() != session_date:
                continue
            bar_end = bar_start + interval_delta - timedelta(seconds=1)
            if bar_end < from_dt or bar_start > to_dt:
                continue
            bars.append(
                UnderlyingHistoryBar(
                    symbol=normalized_symbol,
                    bar_start=bar_start,
                    bar_end=bar_end,
                    open=self._optional_float(candle[1]),
                    high=self._optional_float(candle[2]),
                    low=self._optional_float(candle[3]),
                    close=self._optional_float(candle[4]),
                    volume=self._optional_float(candle[5]),
                    source_id=source_id,
                )
            )
        if not bars:
            raise BrokerNormalizationError(
                "No underlying history candles matched the requested TFIS session window."
            )
        return tuple(sorted(bars, key=lambda item: (item.bar_start, item.bar_end)))

    def _extract_history_candles(
        self,
        payload: dict[str, Any] | list[dict[str, Any]],
    ) -> list[Any]:
        if isinstance(payload, dict):
            if "candles" in payload and isinstance(payload.get("candles"), list):
                return list(payload.get("candles") or [])
            data = payload.get("data")
            if isinstance(data, dict) and isinstance(data.get("candles"), list):
                return list(data.get("candles") or [])
        if isinstance(payload, list):
            return list(payload)
        raise BrokerNormalizationError("Unsupported FYERS history payload shape.")

    def _extract_single_quote_record(
        self,
        payload: dict[str, Any],
        *,
        raw_symbol: str,
    ) -> dict[str, Any]:
        if "d" in payload and isinstance(payload["d"], list) and payload["d"]:
            for item in payload["d"]:
                if not isinstance(item, dict):
                    continue
                candidate_symbol = str(item.get("n") or item.get("symbol") or raw_symbol)
                if candidate_symbol.upper() == raw_symbol.upper():
                    return item
            first = payload["d"][0]
            if isinstance(first, dict):
                return first
        if "symbol" in payload or "n" in payload:
            return payload
        if "data" in payload and isinstance(payload["data"], dict):
            return payload["data"]
        raise BrokerNormalizationError("FYERS quote payload does not contain a usable quote record.")

    def _read_datetime(self, value: Any) -> datetime:
        if value in (None, ""):
            return self._now_provider()
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=self._tzinfo)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=self._tzinfo)
        parsed = datetime.fromisoformat(str(value))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=self._tzinfo)

    def _optional_float(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        return float(value)

    def _optional_int(self, value: Any) -> int | None:
        if value in (None, ""):
            return None
        return int(value)

    def _optional_date(self, value: Any) -> date | None:
        if value in (None, ""):
            return None
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))

    def _optional_option_type(self, value: Any) -> OptionType | None:
        if value in (None, ""):
            return None
        token = str(value).upper()
        if token.endswith("CE"):
            return OptionType.CALL
        if token.endswith("PE"):
            return OptionType.PUT
        return OptionType(token)
