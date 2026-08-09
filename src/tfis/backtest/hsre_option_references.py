from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Literal

from tfis.backtest.csv_loader import OptionLevelsSnapshot
from tfis.backtest.nifty_hsre_data_adapter import (
    HistoricalDailyOhlc,
    HistoricalOptionChainObservation,
    HistoricalOptionIdentity,
    NiftyHsreHistoricalMarketDataProvider,
)
from tfis.domain.enums import OptionType


HsreOptionReferenceStatus = Literal["READY", "INSUFFICIENT_OPTION_LOOKBACK"]


@dataclass(frozen=True, slots=True)
class HsreOptionContract:
    underlying: str
    expiry: str
    strike: int
    option_type: str
    raw_symbol: str


@dataclass(frozen=True, slots=True)
class HsreOptionDailyReferenceProvenance:
    session_date: str
    open: float
    high: float
    low: float
    close: float
    source_files: tuple[str, ...]
    first_timestamp: str | None
    last_timestamp: str | None
    observed_minutes: int
    missing_minutes_synthesized: bool


@dataclass(frozen=True, slots=True)
class HsreSelectedContractReferencePacket:
    session_date: str
    contract: HsreOptionContract
    status: HsreOptionReferenceStatus
    status_reason: str
    prior_exact_contract_sessions_available: tuple[str, ...]
    prior_sessions_used: tuple[str, ...]
    opt_prv_2dhh: float | None
    opt_prv_2dll: float | None
    opt_prv_3dhh: float | None
    opt_prv_3dll: float | None
    two_day_ready: bool
    three_day_ready: bool
    prior_session_provenance: tuple[HsreOptionDailyReferenceProvenance, ...]
    lookahead_assertions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HsreOptionReferenceDiscoveryRow:
    session_date: str
    contract: HsreOptionContract
    prior_exact_contract_sessions_available: tuple[str, ...]
    two_day_ready: bool
    three_day_ready: bool
    opt_prv_2dhh: float | None
    opt_prv_2dll: float | None
    opt_prv_3dhh: float | None
    opt_prv_3dll: float | None
    status: HsreOptionReferenceStatus


class NiftyHsreSelectedContractReferenceBuilder:
    """Build chronology-safe OPT_PRV references for an explicit option contract."""

    def __init__(
        self,
        provider: NiftyHsreHistoricalMarketDataProvider,
        *,
        max_prior_calendar_days: int | None = 45,
    ) -> None:
        if max_prior_calendar_days is not None and max_prior_calendar_days < 1:
            raise ValueError("max_prior_calendar_days must be positive when supplied")
        self.provider = provider
        self.max_prior_calendar_days = max_prior_calendar_days
        self._available_option_sessions: tuple[date, ...] | None = None

    def build_references(
        self,
        *,
        session_date: date,
        identity: HistoricalOptionIdentity,
    ) -> HsreSelectedContractReferencePacket:
        prior_daily = self._prior_exact_contract_daily_bars(
            session_date=session_date,
            identity=identity,
        )
        prior_available = tuple(item.session_date.isoformat() for item in prior_daily)
        lookahead_assertions = (
            f"all_option_reference_sessions_strictly_before_{session_date.isoformat()}",
            "identity_match_includes_underlying_expiry_strike_option_type",
            "current_session_and_future_sessions_excluded_from_opt_prv",
            "no_option_minutes_synthesized",
        )

        if len(prior_daily) < 3:
            return HsreSelectedContractReferencePacket(
                session_date=session_date.isoformat(),
                contract=self._contract(identity),
                status="INSUFFICIENT_OPTION_LOOKBACK",
                status_reason=(
                    "At least 3 completed prior sessions for the exact option "
                    "contract are required to compute OPT_PRV_3DHH/OPT_PRV_3DLL."
                ),
                prior_exact_contract_sessions_available=prior_available,
                prior_sessions_used=(),
                opt_prv_2dhh=None,
                opt_prv_2dll=None,
                opt_prv_3dhh=None,
                opt_prv_3dll=None,
                two_day_ready=len(prior_daily) >= 2,
                three_day_ready=False,
                prior_session_provenance=tuple(
                    self._daily_provenance(item) for item in prior_daily
                ),
                lookahead_assertions=lookahead_assertions,
            )

        last_three = prior_daily[-3:]
        last_two = prior_daily[-2:]
        return HsreSelectedContractReferencePacket(
            session_date=session_date.isoformat(),
            contract=self._contract(identity),
            status="READY",
            status_reason=(
                "Exact selected-contract historical references are ready for "
                "conversion to TFIS option-level inputs."
            ),
            prior_exact_contract_sessions_available=prior_available,
            prior_sessions_used=tuple(item.session_date.isoformat() for item in last_three),
            opt_prv_2dhh=max(item.high for item in last_two),
            opt_prv_2dll=min(item.low for item in last_two),
            opt_prv_3dhh=max(item.high for item in last_three),
            opt_prv_3dll=min(item.low for item in last_three),
            two_day_ready=True,
            three_day_ready=True,
            prior_session_provenance=tuple(self._daily_provenance(item) for item in last_three),
            lookahead_assertions=lookahead_assertions,
        )

    def to_option_levels_snapshot(
        self,
        packet: HsreSelectedContractReferencePacket,
        *,
        timestamp: datetime | None = None,
    ) -> OptionLevelsSnapshot:
        if packet.status != "READY":
            raise ValueError(
                "Cannot convert selected-contract references to OptionLevelsSnapshot "
                f"unless packet is READY: {packet.status}"
            )
        resolved_timestamp = timestamp or datetime.combine(
            date.fromisoformat(packet.session_date),
            time(9, 16),
        )
        return OptionLevelsSnapshot(
            timestamp=resolved_timestamp,
            opt_levels={
                "OPT_PRV_2DHH": self._require_reference(packet.opt_prv_2dhh, "OPT_PRV_2DHH"),
                "OPT_PRV_2DLL": self._require_reference(packet.opt_prv_2dll, "OPT_PRV_2DLL"),
                "OPT_PRV_3DHH": self._require_reference(packet.opt_prv_3dhh, "OPT_PRV_3DHH"),
                "OPT_PRV_3DLL": self._require_reference(packet.opt_prv_3dll, "OPT_PRV_3DLL"),
            },
        )

    def discover_january_contract_references(
        self,
        *,
        year: int = 2024,
        chain_time: time = time(9, 16),
    ) -> tuple[HsreOptionReferenceDiscoveryRow, ...]:
        sessions = [
            item for item in self._option_sessions()
            if item.year == year and item.month == 1
        ]
        if not sessions:
            return ()

        targets: list[tuple[date, HistoricalOptionIdentity]] = []
        first_session = sessions[0]
        first_chain = self.provider.get_option_chain(first_session, chain_time, exact=True)
        targets.extend(self._representative_chain_identities_by_history(first_session, first_chain))

        post_roll = self._best_session_for_expiry(
            sessions=sessions,
            expiry=date(year, 1, 11),
            chain_time=chain_time,
        )
        if post_roll is not None:
            post_roll_chain = self.provider.get_option_chain(post_roll, chain_time, exact=True)
            targets.extend(self._representative_chain_identities_by_history(post_roll, post_roll_chain))

        later = self._best_later_january_session(
            sessions=sessions,
            excluded_expiries={date(year, 1, 4), date(year, 1, 11)},
            chain_time=chain_time,
        )
        if later is not None:
            later_chain = self.provider.get_option_chain(later, chain_time, exact=True)
            representative = self._representative_chain_identities_by_history(later, later_chain)
            if representative:
                targets.append(representative[0])

        deduped: list[tuple[date, HistoricalOptionIdentity]] = []
        seen: set[tuple[date, str]] = set()
        for session, identity in targets:
            key = (session, self._identity_key(identity))
            if key not in seen:
                seen.add(key)
                deduped.append((session, identity))

        rows: list[HsreOptionReferenceDiscoveryRow] = []
        for session, identity in deduped:
            packet = self.build_references(session_date=session, identity=identity)
            rows.append(
                HsreOptionReferenceDiscoveryRow(
                    session_date=session.isoformat(),
                    contract=packet.contract,
                    prior_exact_contract_sessions_available=packet.prior_exact_contract_sessions_available,
                    two_day_ready=packet.two_day_ready,
                    three_day_ready=packet.three_day_ready,
                    opt_prv_2dhh=packet.opt_prv_2dhh,
                    opt_prv_2dll=packet.opt_prv_2dll,
                    opt_prv_3dhh=packet.opt_prv_3dhh,
                    opt_prv_3dll=packet.opt_prv_3dll,
                    status=packet.status,
                )
            )
        return tuple(rows)

    @staticmethod
    def stable_packet_hash(packet: HsreSelectedContractReferencePacket) -> str:
        encoded = json.dumps(
            option_reference_packet_to_dict(packet),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _prior_exact_contract_daily_bars(
        self,
        *,
        session_date: date,
        identity: HistoricalOptionIdentity,
    ) -> tuple[HistoricalDailyOhlc, ...]:
        result: list[HistoricalDailyOhlc] = []
        earliest = (
            session_date - timedelta(days=self.max_prior_calendar_days)
            if self.max_prior_calendar_days is not None
            else None
        )
        for prior_session in self._option_sessions():
            if earliest is not None and prior_session < earliest:
                continue
            if prior_session >= session_date:
                break
            bars = self.provider.get_contract_session_bars(prior_session, identity)
            if not bars:
                continue
            result.append(
                NiftyHsreHistoricalMarketDataProvider._aggregate_option_bars(
                    prior_session,
                    identity,
                    bars,
                )
            )
        return tuple(result)

    def _option_sessions(self) -> tuple[date, ...]:
        if self._available_option_sessions is None:
            self._available_option_sessions = self.provider.available_option_sessions()
        return self._available_option_sessions

    @staticmethod
    def _representative_chain_identities(
        session_date: date,
        chain: tuple[HistoricalOptionChainObservation, ...],
    ) -> list[tuple[date, HistoricalOptionIdentity]]:
        if not chain:
            return []
        expiries = sorted({item.identity.expiry for item in chain})
        near_expiry = expiries[0]
        near = [item for item in chain if item.identity.expiry == near_expiry]
        by_side: list[tuple[date, HistoricalOptionIdentity]] = []
        for side in (OptionType.CALL, OptionType.PUT):
            side_rows = [item for item in near if item.identity.option_type is side]
            if not side_rows:
                continue
            middle = sorted(side_rows, key=lambda item: (item.identity.strike, item.identity.raw_symbol))
            by_side.append((session_date, middle[len(middle) // 2].identity))
        return by_side

    def _representative_chain_identities_by_history(
        self,
        session_date: date,
        chain: tuple[HistoricalOptionChainObservation, ...],
    ) -> list[tuple[date, HistoricalOptionIdentity]]:
        if not chain:
            return []
        expiries = sorted({item.identity.expiry for item in chain})
        near_expiry = expiries[0]
        near = [item for item in chain if item.identity.expiry == near_expiry]
        prior_counts = self._prior_symbol_counts(session_date=session_date)
        result: list[tuple[date, HistoricalOptionIdentity]] = []
        for side in (OptionType.CALL, OptionType.PUT):
            side_rows = [item for item in near if item.identity.option_type is side]
            if not side_rows:
                continue
            ranked = sorted(
                side_rows,
                key=lambda item: (
                    prior_counts.get(item.identity.raw_symbol, 0),
                    -abs(item.identity.strike - self._median_strike(side_rows)),
                    item.identity.raw_symbol,
                ),
                reverse=True,
            )
            result.append((session_date, ranked[0].identity))
        return result

    def _prior_symbol_counts(self, *, session_date: date) -> dict[str, int]:
        counts: dict[str, int] = {}
        earliest = (
            session_date - timedelta(days=self.max_prior_calendar_days)
            if self.max_prior_calendar_days is not None
            else None
        )
        for prior_session in self._option_sessions():
            if earliest is not None and prior_session < earliest:
                continue
            if prior_session >= session_date:
                break
            seen_this_session = {
                bar.identity.raw_symbol
                for bar in self.provider.get_option_session_bars(prior_session)
            }
            for symbol in seen_this_session:
                counts[symbol] = counts.get(symbol, 0) + 1
        return counts

    def _best_session_for_expiry(
        self,
        *,
        sessions: list[date],
        expiry: date,
        chain_time: time,
    ) -> date | None:
        candidates = [
            session for session in sessions
            if expiry in self.provider.get_available_expiries(session)
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda session: self._best_prior_count_for_chain(
                session_date=session,
                chain=self.provider.get_option_chain(
                    session,
                    chain_time,
                    expiry=expiry,
                    exact=True,
                ),
            ),
        )

    def _best_later_january_session(
        self,
        *,
        sessions: list[date],
        excluded_expiries: set[date],
        chain_time: time,
    ) -> date | None:
        candidates: list[tuple[int, date]] = []
        for session in sessions:
            expiries = [
                expiry for expiry in self.provider.get_available_expiries(session)
                if expiry not in excluded_expiries
            ]
            if not expiries:
                continue
            chain = self.provider.get_option_chain(
                session,
                chain_time,
                expiry=sorted(expiries)[0],
                exact=True,
            )
            candidates.append(
                (
                    self._best_prior_count_for_chain(
                        session_date=session,
                        chain=chain,
                    ),
                    session,
                )
            )
        if not candidates:
            return None
        return max(candidates)[1]

    def _best_prior_count_for_chain(
        self,
        *,
        session_date: date,
        chain: tuple[HistoricalOptionChainObservation, ...],
    ) -> int:
        prior_counts = self._prior_symbol_counts(session_date=session_date)
        if not chain:
            return 0
        return max(prior_counts.get(item.identity.raw_symbol, 0) for item in chain)

    @staticmethod
    def _median_strike(rows: list[HistoricalOptionChainObservation]) -> int:
        strikes = sorted(item.identity.strike for item in rows)
        return strikes[len(strikes) // 2]

    @staticmethod
    def _identity_key(identity: HistoricalOptionIdentity) -> str:
        return (
            f"{identity.underlying}|{identity.expiry.isoformat()}|"
            f"{identity.strike}|{identity.option_type.value}"
        )

    @staticmethod
    def _contract(identity: HistoricalOptionIdentity) -> HsreOptionContract:
        return HsreOptionContract(
            underlying=identity.underlying,
            expiry=identity.expiry.isoformat(),
            strike=identity.strike,
            option_type=identity.option_type.value,
            raw_symbol=identity.raw_symbol,
        )

    @staticmethod
    def _daily_provenance(bar: HistoricalDailyOhlc) -> HsreOptionDailyReferenceProvenance:
        return HsreOptionDailyReferenceProvenance(
            session_date=bar.session_date.isoformat(),
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            source_files=tuple(str(path) for path in bar.source_files),
            first_timestamp=bar.completeness.first_timestamp.isoformat()
            if bar.completeness.first_timestamp else None,
            last_timestamp=bar.completeness.last_timestamp.isoformat()
            if bar.completeness.last_timestamp else None,
            observed_minutes=bar.completeness.observed_minutes,
            missing_minutes_synthesized=bar.completeness.missing_minutes_synthesized,
        )

    @staticmethod
    def _require_reference(value: float | None, alias: str) -> float:
        if value is None:
            raise ValueError(f"Missing required option reference: {alias}")
        return float(value)


def option_reference_packet_to_dict(
    packet: HsreSelectedContractReferencePacket,
) -> dict[str, Any]:
    def convert(value: Any) -> Any:
        if hasattr(value, "__dataclass_fields__"):
            return {key: convert(item) for key, item in asdict(value).items()}
        if isinstance(value, dict):
            return {str(key): convert(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [convert(item) for item in value]
        return value

    return convert(packet)
