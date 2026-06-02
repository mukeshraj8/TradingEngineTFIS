from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Any, TYPE_CHECKING
from tfis.market_data import UnderlyingHistoryBar

if TYPE_CHECKING:
    from tfis.paper.models import (
        CalendarContextEvent,
        OptionChainSnapshotEvent,
        SelectedContractBarEvent,
        SelectedContractQuoteEvent,
        UnderlyingQuoteEvent,
    )


class BrokerAdapterError(RuntimeError):
    """Base error for broker-adapter failures."""


class BrokerCredentialsError(BrokerAdapterError):
    """Raised when required broker credentials are missing."""


class BrokerConnectionError(BrokerAdapterError):
    """Raised when a broker connection cannot be established safely."""


class BrokerNormalizationError(BrokerAdapterError):
    """Raised when raw broker payloads cannot be normalized safely."""


class BrokerOrderPlacementBlockedError(BrokerAdapterError):
    """Raised when any order-placement method is attempted in TFIS paper mode."""


class BrokerConnectionState(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    COOLDOWN = "COOLDOWN"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class BrokerHealthEvent:
    broker_name: str
    as_of: datetime
    connection_state: BrokerConnectionState
    source_id: str
    is_connected: bool
    cooldown_seconds: float | None = None
    reconnect_attempts: int = 0
    rate_limit_remaining: int | None = None
    rate_limit_limit: int | None = None
    warnings: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()


NormalizedBrokerEvent = Any


class BrokerAdapter(ABC):
    """Broker-agnostic market-data adapter for TFIS paper mode."""

    broker_name: str

    @abstractmethod
    def connect(self) -> None:
        """Connect to the broker market-data source."""

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the broker market-data source."""

    @abstractmethod
    def subscribe_symbols(self, symbols: tuple[str, ...]) -> tuple[str, ...]:
        """Subscribe to the requested symbols and return the accepted set."""

    @abstractmethod
    def get_underlying_quote(
        self,
        symbol: str,
        *,
        session_date: date,
    ) -> UnderlyingQuoteEvent:
        """Fetch one normalized underlying quote."""

    @abstractmethod
    def get_option_chain(
        self,
        symbol: str,
        expiry: date,
        *,
        session_date: date,
    ) -> OptionChainSnapshotEvent:
        """Fetch one normalized option-chain snapshot."""

    @abstractmethod
    def get_option_quote(
        self,
        option_symbol: str,
        *,
        session_date: date,
    ) -> SelectedContractQuoteEvent:
        """Fetch one normalized selected-contract quote."""

    @abstractmethod
    def get_underlying_bars(
        self,
        symbol: str,
        *,
        session_date: date,
        from_time: time,
        to_time: time,
        interval_minutes: int = 1,
    ) -> tuple[UnderlyingHistoryBar, ...]:
        """Fetch a bounded normalized set of underlying history bars."""

    @abstractmethod
    def get_underlying_daily_bars(
        self,
        symbol: str,
        *,
        session_date: date,
        lookback_days: int = 90,
    ) -> tuple[UnderlyingHistoryBar, ...]:
        """Fetch normalized daily bars ending at the requested TFIS session date."""

    @abstractmethod
    def stream_ticks(self) -> tuple[NormalizedBrokerEvent, ...]:
        """Return a bounded normalized event batch from the live stream."""

    @abstractmethod
    def health(self) -> BrokerHealthEvent:
        """Return current broker health diagnostics."""

    @abstractmethod
    def reconnect(self) -> BrokerHealthEvent:
        """Reconnect the broker market-data source and return health diagnostics."""

    def place_order(self, *args: object, **kwargs: object) -> None:
        raise BrokerOrderPlacementBlockedError(
            "TFIS broker adapters are market-data only in S23 paper mode. "
            "Order placement is blocked."
        )

    def modify_order(self, *args: object, **kwargs: object) -> None:
        raise BrokerOrderPlacementBlockedError(
            "TFIS broker adapters are market-data only in S23 paper mode. "
            "Order modification is blocked."
        )

    def cancel_order(self, *args: object, **kwargs: object) -> None:
        raise BrokerOrderPlacementBlockedError(
            "TFIS broker adapters are market-data only in S23 paper mode. "
            "Order cancellation is blocked."
        )
