from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from tfis.backtest.hsre_option_references import (
    NiftyHsreSelectedContractReferenceBuilder,
)
from tfis.backtest.nifty_hsre_data_adapter import (
    HistoricalOptionIdentity,
    HistoricalOptionMinuteBar,
    HistoricalSpotMinuteBar,
    HsreDataError,
    NiftyHsreHistoricalMarketDataProvider,
    parse_nifty_option_symbol,
)
from tfis.domain.enums import OptionType
from tfis.market_metadata.lot_size import effective_lot_size, minimum_oi_units


class HistoricalMarketExplorerError(ValueError):
    """Raised when a read-only explorer request cannot be satisfied."""


@dataclass(frozen=True, slots=True)
class _InstrumentConfig:
    symbol: str
    folder_candidates: tuple[str, ...]


_INSTRUMENTS = {
    "NIFTY": _InstrumentConfig("NIFTY", ("Nifty", "NIFTY", "nifty")),
    "BANKNIFTY": _InstrumentConfig(
        "BANKNIFTY",
        ("BankNifty", "BANKNIFTY", "banknifty"),
    ),
}


def parse_contract_symbol(symbol: str) -> HistoricalOptionIdentity:
    return parse_nifty_option_symbol(symbol)


class HistoricalMarketExplorerService:
    """Read-only historical market explorer backend.

    This service intentionally exposes market facts only. It does not run
    StrategyEvaluator, contract selection, S23 decisions, paper/live code, or
    broker adapters.
    """

    def __init__(
        self,
        data_root: str | Path = r"D:\HistoricalData",
        *,
        max_cached_sessions: int = 16,
    ) -> None:
        self.data_root = Path(data_root)
        self.max_cached_sessions = max_cached_sessions
        self._providers: dict[str, NiftyHsreHistoricalMarketDataProvider] = {}

    def instruments(self) -> tuple[str, ...]:
        available = []
        for instrument in _INSTRUMENTS:
            try:
                self._instrument_root(instrument)
            except HistoricalMarketExplorerError:
                continue
            available.append(instrument)
        return tuple(available or _INSTRUMENTS.keys())

    def sessions(self, instrument: str) -> dict[str, Any]:
        provider = self._provider(instrument)
        spot = provider.available_spot_sessions()
        options = provider.available_option_sessions()
        return {
            "instrument": self._normalize_instrument(instrument),
            "spot_sessions": [item.isoformat() for item in spot],
            "option_sessions": [item.isoformat() for item in options],
            "common_sessions": [
                item.isoformat() for item in sorted(set(spot).intersection(options))
            ],
        }

    def expiries(self, instrument: str, session_date: date) -> dict[str, Any]:
        provider = self._provider(instrument)
        return {
            "instrument": self._normalize_instrument(instrument),
            "date": session_date.isoformat(),
            "expiries": [
                item.isoformat() for item in provider.get_available_expiries(session_date)
            ],
        }

    def strikes(
        self,
        instrument: str,
        session_date: date,
        expiry: date,
        option_type: OptionType | None = None,
    ) -> dict[str, Any]:
        rows = [
            bar.identity.strike
            for bar in self._provider(instrument).get_option_session_bars(session_date)
            if bar.identity.expiry == expiry
            and (option_type is None or bar.identity.option_type is option_type)
        ]
        return {
            "instrument": self._normalize_instrument(instrument),
            "date": session_date.isoformat(),
            "expiry": expiry.isoformat(),
            "option_type": option_type.value if option_type else None,
            "strikes": sorted(set(rows)),
        }

    def lot_size_payload(
        self,
        *,
        instrument: str,
        reference_date: date,
    ) -> dict[str, Any]:
        symbol = self._normalize_instrument(instrument)
        try:
            lot_size = effective_lot_size(symbol, reference_date)
        except ValueError as exc:
            raise HistoricalMarketExplorerError(str(exc)) from exc
        return {
            "instrument": symbol,
            "reference_date": reference_date.isoformat(),
            "lot_size": lot_size,
            "source": "date_effective_instrument_schedule",
            "editable": True,
        }

    def contract_payload(
        self,
        *,
        instrument: str,
        session_date: date,
        expiry: date,
        strike: int,
        option_type: OptionType,
        start_time: time | None = None,
        end_time: time | None = None,
    ) -> dict[str, Any]:
        provider = self._provider(instrument)
        identity = self._resolve_identity(
            provider=provider,
            session_date=session_date,
            expiry=expiry,
            strike=strike,
            option_type=option_type,
        )
        option_bars_all = provider.get_contract_session_bars(session_date, identity)
        option_bars = self._time_filter(option_bars_all, start_time, end_time)
        spot_bars_all = provider.get_spot_session_bars(session_date)
        spot_bars = self._time_filter(spot_bars_all, start_time, end_time)
        option_daily = self._option_daily_summary(option_bars_all)
        spot_daily = self._spot_daily_summary(spot_bars_all)
        option_references = NiftyHsreSelectedContractReferenceBuilder(
            provider
        ).build_references(session_date=session_date, identity=identity)
        prior_option_sessions = tuple(
            date.fromisoformat(item)
            for item in option_references.prior_exact_contract_sessions_available
        )
        prior_spot_daily = self._prior_spot_daily(provider, session_date, limit=4)
        quality = self._quality_warnings(
            provider=provider,
            session_date=session_date,
            identity=identity,
            option_bars=option_bars_all,
            spot_bars=spot_bars_all,
            option_reference_status=str(option_references.status),
        )
        lot_size, minimum_oi = self._lot_size_values(instrument, session_date)
        return {
            "selection": {
                "instrument": self._normalize_instrument(instrument),
                "date": session_date.isoformat(),
                "symbol": identity.raw_symbol,
                "expiry": identity.expiry.isoformat(),
                "strike": identity.strike,
                "option_type": identity.option_type.value,
            },
            "summary": option_daily,
            "spot_summary": spot_daily,
            "minute_marks": {
                "premium_0916": self._minute_bar(option_bars_all, time(9, 16)),
                "spot_0916": self._minute_bar(spot_bars_all, time(9, 16)),
                "orpt_0924": self._minute_bar(option_bars_all, time(9, 24)),
                "spot_orpt_0924": self._minute_bar(spot_bars_all, time(9, 24)),
                "rc_0929": self._minute_bar(option_bars_all, time(9, 29)),
                "spot_rc_0929": self._minute_bar(spot_bars_all, time(9, 29)),
            },
            "option_bars": [self._option_bar_dict(item) for item in option_bars],
            "spot_bars": [self._spot_bar_dict(item) for item in spot_bars],
            "prior_option_history": {
                "label": "Derived using TFIS HSRE exact-contract history semantics",
                "rows": [
                    self._daily_option_dict(
                        provider.get_contract_session_bars(item, identity),
                        session_date=item,
                        highlight=item in prior_option_sessions[-3:],
                    )
                    for item in prior_option_sessions
                ],
                "references": {
                    "status": option_references.status,
                    "status_reason": option_references.status_reason,
                    "OPT_PRV_2DHH": option_references.opt_prv_2dhh,
                    "OPT_PRV_2DLL": option_references.opt_prv_2dll,
                    "OPT_PRV_3DHH": option_references.opt_prv_3dhh,
                    "OPT_PRV_3DLL": option_references.opt_prv_3dll,
                    "prior_sessions_used": option_references.prior_sessions_used,
                },
            },
            "prior_spot_history": {
                "label": "Derived using TFIS HSRE completed-prior-spot daily semantics",
                "rows": [
                    self._daily_spot_dict(item, highlight=item in prior_spot_daily[-4:])
                    for item in prior_spot_daily
                ],
                "references": self._spot_references(prior_spot_daily),
            },
            "s23_workbook_validation": {
                "label": "S23 reference only - no strategy decision is made",
                "spot": self._spot_references(prior_spot_daily),
                "selected_option": {
                    "OPT_PRV_2DHH": option_references.opt_prv_2dhh,
                    "OPT_PRV_2DLL": option_references.opt_prv_2dll,
                    "OPT_PRV_3DHH": option_references.opt_prv_3dhh,
                    "OPT_PRV_3DLL": option_references.opt_prv_3dll,
                },
                "premium_0916": self._minute_bar(option_bars_all, time(9, 16)),
                "orpt": self._minute_bar(option_bars_all, time(9, 24)),
                "rc": self._minute_bar(option_bars_all, time(9, 29)),
                "historical_lot_size": lot_size,
                "minimum_oi_units": minimum_oi,
            },
            "multi_day_option_bars": self._multi_day_option_bars(
                provider,
                session_date=session_date,
                identity=identity,
                prior_limit=4,
            ),
            "data_quality": quality,
        }

    def option_chain_payload(
        self,
        *,
        instrument: str,
        session_date: date,
        expiry: date,
        snapshot_time: time = time(9, 16),
        selected_strike: int | None = None,
        ideal_premium: float | None = None,
        minimum_premium: float | None = None,
        minimum_oi: int | None = None,
        start_strike: int | None = None,
        end_strike: int | None = None,
    ) -> dict[str, Any]:
        chain = self._provider(instrument).get_option_chain(
            session_date,
            snapshot_time,
            expiry=expiry,
            exact=True,
        )
        rows_by_strike: dict[int, dict[str, Any]] = {}
        for item in chain:
            row = rows_by_strike.setdefault(item.identity.strike, {"strike": item.identity.strike})
            prefix = "CE" if item.identity.option_type is OptionType.CALL else "PE"
            row[f"{prefix}_symbol"] = item.identity.raw_symbol
            row[f"{prefix}_ltp"] = item.ltp
            row[f"{prefix}_oi"] = item.oi
            row[f"{prefix}_volume"] = item.volume
        rows = []
        for strike in sorted(rows_by_strike):
            row = rows_by_strike[strike]
            row["selected"] = selected_strike == strike
            for prefix in ("CE", "PE"):
                ltp = row.get(f"{prefix}_ltp")
                oi = row.get(f"{prefix}_oi")
                row[f"{prefix}_meets_ideal"] = (
                    ltp is not None and ideal_premium is not None and ltp >= ideal_premium
                )
                row[f"{prefix}_meets_minimum"] = (
                    ltp is not None and minimum_premium is not None and ltp >= minimum_premium
                )
                row[f"{prefix}_meets_oi"] = (
                    oi is not None and minimum_oi is not None and oi >= minimum_oi
                )
            rows.append(row)
        return {
            "instrument": self._normalize_instrument(instrument),
            "date": session_date.isoformat(),
            "expiry": expiry.isoformat(),
            "time": snapshot_time.isoformat(),
            "rows": rows,
            "search_order": self._search_order_rows(
                rows,
                start_strike=start_strike,
                end_strike=end_strike,
                ideal_premium=ideal_premium,
                minimum_premium=minimum_premium,
                minimum_oi=minimum_oi,
            ),
        }

    def manual_strike_scan_payload(
        self,
        *,
        instrument: str,
        session_date: date,
        expiry: date,
        option_type: OptionType,
        snapshot_time: time = time(9, 16),
        start_strike: int,
        end_strike: int,
        history_sessions: int = 3,
        premium_reference: float | None = None,
        ideal_factor_pct: float | None = None,
        minimum_factor_pct: float | None = None,
        ideal_premium: float | None = None,
        minimum_premium: float | None = None,
        minimum_oi: int | None = None,
    ) -> dict[str, Any]:
        if history_sessions < 1:
            raise HistoricalMarketExplorerError("history_sessions must be positive")
        provider = self._provider(instrument)
        ideal_threshold = self._premium_threshold(
            direct=ideal_premium,
            reference=premium_reference,
            factor_pct=ideal_factor_pct,
        )
        minimum_threshold = self._premium_threshold(
            direct=minimum_premium,
            reference=premium_reference,
            factor_pct=minimum_factor_pct,
        )
        chain = provider.get_option_chain(
            session_date,
            snapshot_time,
            expiry=expiry,
            exact=True,
        )
        by_strike = {
            item.identity.strike: item
            for item in chain
            if item.identity.option_type is option_type
        }
        low = min(start_strike, end_strike)
        high = max(start_strike, end_strike)
        strikes = sorted(
            strike for strike in by_strike
            if low <= strike <= high
        )
        if start_strike > end_strike:
            strikes.reverse()

        rows: list[dict[str, Any]] = []
        for strike in strikes:
            observation = by_strike[strike]
            prior_daily = provider.get_prior_contract_daily_bars(
                session_date=session_date,
                identity=observation.identity,
                limit=history_sessions,
            )
            row = self._manual_scan_row(
                observation=observation,
                prior_daily=prior_daily,
                history_sessions=history_sessions,
                ideal_threshold=ideal_threshold,
                minimum_threshold=minimum_threshold,
                minimum_oi=minimum_oi,
            )
            rows.append(row)

        selected = self._select_manual_scan_row(rows)
        if selected is not None:
            for row in rows:
                row["selected"] = row["strike"] == selected["strike"]
            selected = dict(selected)

        return {
            "instrument": self._normalize_instrument(instrument),
            "date": session_date.isoformat(),
            "expiry": expiry.isoformat(),
            "option_type": option_type.value,
            "time": snapshot_time.isoformat(),
            "start_strike": start_strike,
            "end_strike": end_strike,
            "search_direction": "start_to_end",
            "history_sessions": history_sessions,
            "thresholds": {
                "premium_reference": premium_reference,
                "ideal_factor_pct": ideal_factor_pct,
                "minimum_factor_pct": minimum_factor_pct,
                "ideal_premium": ideal_threshold,
                "minimum_premium": minimum_threshold,
                "minimum_oi": minimum_oi,
            },
            "selected": selected,
            "rows": rows,
        }

    def daily_option_history_payload(
        self,
        *,
        instrument: str,
        session_date: date,
        expiry: date,
        strike: int,
        option_type: OptionType,
        from_date: date | None = None,
        to_date: date | None = None,
        sessions_back: int | None = None,
    ) -> dict[str, Any]:
        provider = self._provider(instrument)
        identity = self._resolve_identity(
            provider=provider,
            session_date=session_date,
            expiry=expiry,
            strike=strike,
            option_type=option_type,
        )
        sessions = self._history_sessions(
            available=provider.available_option_sessions(),
            session_date=session_date,
            from_date=from_date,
            to_date=to_date,
            sessions_back=sessions_back,
        )
        rows: list[dict[str, Any]] = []
        for item in sessions:
            try:
                bars = provider.get_contract_session_bars(item, identity)
            except HsreDataError:
                bars = ()
            rows.append(
                self._daily_option_dict(
                    bars,
                    session_date=item,
                    highlight=item == session_date,
                )
            )
        available = [row for row in rows if row.get("status") != "MISSING"]
        return {
            "instrument": self._normalize_instrument(instrument),
            "date": session_date.isoformat(),
            "symbol": identity.raw_symbol,
            "expiry": expiry.isoformat(),
            "strike": strike,
            "option_type": option_type.value,
            "from_date": sessions[0].isoformat() if sessions else None,
            "to_date": sessions[-1].isoformat() if sessions else None,
            "available_count": len(available),
            "missing_count": len(rows) - len(available),
            "DHH": max((row["high"] for row in available), default=None),
            "DLL": min((row["low"] for row in available), default=None),
            "rows": rows,
        }

    def export_csv(self, payload: dict[str, Any], section: str) -> str:
        if section == "contract_history":
            rows = payload["prior_option_history"]["rows"]
        elif section == "option_chain":
            rows = payload["rows"]
        elif section == "manual_scan":
            rows = payload["rows"]
        elif section == "daily_option_history":
            rows = payload["rows"]
        elif section == "workbook_inputs":
            rows = [self._flatten_workbook_inputs(payload["s23_workbook_validation"])]
        else:
            raise HistoricalMarketExplorerError(f"Unsupported export section: {section}")
        return self._rows_to_csv(rows)

    def _provider(self, instrument: str) -> NiftyHsreHistoricalMarketDataProvider:
        symbol = self._normalize_instrument(instrument)
        cached = self._providers.get(symbol)
        if cached is not None:
            return cached
        root = self._instrument_root(symbol)
        provider = NiftyHsreHistoricalMarketDataProvider(
            root,
            instrument=symbol,
            max_cached_sessions=self.max_cached_sessions,
        )
        self._providers[symbol] = provider
        return provider

    def _instrument_root(self, instrument: str) -> Path:
        symbol = self._normalize_instrument(instrument)
        if (self.data_root / "spot").is_dir() and (self.data_root / "options").is_dir():
            return self.data_root
        for folder in _INSTRUMENTS[symbol].folder_candidates:
            candidate = self.data_root / folder
            if (candidate / "spot").is_dir() and (candidate / "options").is_dir():
                return candidate
        raise HistoricalMarketExplorerError(
            f"Could not find historical folder for {symbol} under {self.data_root}"
        )

    @staticmethod
    def _normalize_instrument(instrument: str) -> str:
        symbol = instrument.strip().upper()
        if symbol not in _INSTRUMENTS:
            raise HistoricalMarketExplorerError(f"Unsupported instrument: {instrument!r}")
        return symbol

    @staticmethod
    def _resolve_identity(
        *,
        provider: NiftyHsreHistoricalMarketDataProvider,
        session_date: date,
        expiry: date,
        strike: int,
        option_type: OptionType,
    ) -> HistoricalOptionIdentity:
        identities = {
            bar.identity.raw_symbol: bar.identity
            for bar in provider.get_option_session_bars(session_date)
            if bar.identity.expiry == expiry
            and bar.identity.strike == strike
            and bar.identity.option_type is option_type
        }
        if not identities:
            raise HistoricalMarketExplorerError(
                "No exact contract found for "
                f"date={session_date.isoformat()} expiry={expiry.isoformat()} "
                f"strike={strike} option_type={option_type.value}"
            )
        return identities[sorted(identities)[0]]

    @staticmethod
    def _time_filter(
        bars: tuple[HistoricalOptionMinuteBar, ...] | tuple[HistoricalSpotMinuteBar, ...],
        start_time: time | None,
        end_time: time | None,
    ) -> tuple[Any, ...]:
        return tuple(
            item for item in bars
            if (start_time is None or item.timestamp.time() >= start_time)
            and (end_time is None or item.timestamp.time() <= end_time)
        )

    @classmethod
    def _option_daily_summary(cls, bars: tuple[HistoricalOptionMinuteBar, ...]) -> dict[str, Any]:
        if not bars:
            return {"status": "MISSING"}
        ordered = tuple(sorted(bars, key=lambda item: item.timestamp))
        oi_values = [item.oi for item in ordered]
        return {
            "first_traded_time": ordered[0].timestamp.isoformat(),
            "last_traded_time": ordered[-1].timestamp.isoformat(),
            "day_open": ordered[0].open,
            "day_high": max(item.high for item in ordered),
            "day_low": min(item.low for item in ordered),
            "day_close": ordered[-1].close,
            "day_volume": sum(item.volume for item in ordered),
            "opening_oi": ordered[0].oi,
            "closing_oi": ordered[-1].oi,
            "maximum_oi": max(oi_values),
            "minimum_oi": min(oi_values),
            "oi_change": ordered[-1].oi - ordered[0].oi,
            "minute_count": len(ordered),
        }

    @staticmethod
    def _spot_daily_summary(bars: tuple[HistoricalSpotMinuteBar, ...]) -> dict[str, Any]:
        if not bars:
            return {"status": "MISSING"}
        ordered = tuple(sorted(bars, key=lambda item: item.timestamp))
        return {
            "first_time": ordered[0].timestamp.isoformat(),
            "last_time": ordered[-1].timestamp.isoformat(),
            "day_open": ordered[0].open,
            "day_high": max(item.high for item in ordered),
            "day_low": min(item.low for item in ordered),
            "day_close": ordered[-1].close,
            "minute_count": len(ordered),
        }

    @classmethod
    def _minute_bar(cls, bars: tuple[Any, ...], target: time) -> dict[str, Any]:
        matches = [item for item in bars if item.timestamp.time() == target]
        if not matches:
            return {"status": "MISSING", "time": target.isoformat()}
        item = matches[0]
        row = {
            "status": "FOUND",
            "timestamp": item.timestamp.isoformat(),
            "open": item.open,
            "high": item.high,
            "low": item.low,
            "close": item.close,
        }
        if hasattr(item, "oi"):
            row["oi"] = item.oi
        if hasattr(item, "volume"):
            row["volume"] = item.volume
        return row

    @staticmethod
    def _option_bar_dict(item: HistoricalOptionMinuteBar) -> dict[str, Any]:
        return {
            "timestamp": item.timestamp.isoformat(),
            "open": item.open,
            "high": item.high,
            "low": item.low,
            "close": item.close,
            "oi": item.oi,
            "volume": item.volume,
        }

    @staticmethod
    def _spot_bar_dict(item: HistoricalSpotMinuteBar) -> dict[str, Any]:
        return {
            "timestamp": item.timestamp.isoformat(),
            "open": item.open,
            "high": item.high,
            "low": item.low,
            "close": item.close,
        }

    @staticmethod
    def _daily_option_dict(
        bars: tuple[HistoricalOptionMinuteBar, ...],
        *,
        session_date: date,
        highlight: bool,
    ) -> dict[str, Any]:
        ordered = tuple(sorted(bars, key=lambda item: item.timestamp))
        if not ordered:
            return {
                "date": session_date.isoformat(),
                "status": "MISSING",
                "highlight_recent_3": highlight,
            }
        return {
            "date": session_date.isoformat(),
            "open": ordered[0].open,
            "high": max(item.high for item in ordered),
            "low": min(item.low for item in ordered),
            "close": ordered[-1].close,
            "volume": sum(item.volume for item in ordered),
            "opening_oi": ordered[0].oi,
            "closing_oi": ordered[-1].oi,
            "minute_count": len(ordered),
            "highlight_recent_3": highlight,
        }

    @staticmethod
    def _daily_spot_dict(item: Any, *, highlight: bool) -> dict[str, Any]:
        return {
            "date": item.session_date.isoformat(),
            "open": item.open,
            "high": item.high,
            "low": item.low,
            "close": item.close,
            "highlight_recent_4": highlight,
        }

    @staticmethod
    def _prior_spot_daily(
        provider: NiftyHsreHistoricalMarketDataProvider,
        session_date: date,
        *,
        limit: int,
    ) -> tuple[Any, ...]:
        sessions = [item for item in provider.available_spot_sessions() if item < session_date]
        result = [provider.aggregate_spot_session(item) for item in sessions[-limit:]]
        return tuple(result)

    @staticmethod
    def _spot_references(prior_daily: tuple[Any, ...]) -> dict[str, Any]:
        last_two = prior_daily[-2:]
        last_three = prior_daily[-3:]
        last_four = prior_daily[-4:]
        return {
            "PRV_2DHH": max((item.high for item in last_two), default=None),
            "PRV_2DLL": min((item.low for item in last_two), default=None),
            "PRV_3DHH": max((item.high for item in last_three), default=None),
            "PRV_3DLL": min((item.low for item in last_three), default=None),
            "PRV_4DHH": max((item.high for item in last_four), default=None),
            "PRV_4DLL": min((item.low for item in last_four), default=None),
        }

    @classmethod
    def _multi_day_option_bars(
        cls,
        provider: NiftyHsreHistoricalMarketDataProvider,
        *,
        session_date: date,
        identity: HistoricalOptionIdentity,
        prior_limit: int,
    ) -> list[dict[str, Any]]:
        prior = provider.get_prior_contract_daily_bars(
            session_date=session_date,
            identity=identity,
            limit=prior_limit,
        )
        sessions = [item.session_date for item in prior] + [session_date]
        rows: list[dict[str, Any]] = []
        for session in sessions:
            for bar in provider.get_contract_session_bars(session, identity):
                item = cls._option_bar_dict(bar)
                item["session_date"] = session.isoformat()
                rows.append(item)
        return rows

    @staticmethod
    def _quality_warnings(
        *,
        provider: NiftyHsreHistoricalMarketDataProvider,
        session_date: date,
        identity: HistoricalOptionIdentity,
        option_bars: tuple[HistoricalOptionMinuteBar, ...],
        spot_bars: tuple[HistoricalSpotMinuteBar, ...],
        option_reference_status: str,
    ) -> list[dict[str, str]]:
        warnings: list[dict[str, str]] = []
        if not option_bars:
            warnings.append({"code": "missing_option_contract", "message": "Selected contract has no rows."})
        if not spot_bars:
            warnings.append({"code": "missing_spot_file", "message": "Selected spot session has no rows."})
        option_times = Counter(item.timestamp for item in option_bars)
        spot_times = Counter(item.timestamp for item in spot_bars)
        if any(count > 1 for count in option_times.values()):
            warnings.append({"code": "duplicate_option_rows", "message": "Duplicate selected-contract timestamps found."})
        if any(count > 1 for count in spot_times.values()):
            warnings.append({"code": "duplicate_spot_rows", "message": "Duplicate spot timestamps found."})
        for label, target in (("missing_0916", time(9, 16)), ("missing_orpt_0924", time(9, 24)), ("missing_rc_0929", time(9, 29))):
            if not any(item.timestamp.time() == target for item in option_bars):
                warnings.append({"code": label, "message": f"Selected option minute {target.isoformat()} is missing."})
        if any(item.oi < 0 for item in option_bars):
            warnings.append({"code": "negative_oi", "message": "Negative OI found."})
        if option_reference_status != "READY":
            warnings.append({
                "code": "insufficient_exact_contract_lookback",
                "message": "Fewer than 3 completed exact-contract prior sessions are available.",
            })
        try:
            provider.resolve_spot_file(session_date)
        except HsreDataError as exc:
            warnings.append({"code": "missing_spot_file", "message": str(exc)})
        try:
            provider.resolve_option_file(session_date)
        except HsreDataError as exc:
            warnings.append({"code": "missing_option_file", "message": str(exc)})
        return warnings

    @staticmethod
    def _lot_size_values(instrument: str, session_date: date) -> tuple[int | None, int | None]:
        try:
            return (
                effective_lot_size(instrument, session_date),
                minimum_oi_units(instrument, session_date),
            )
        except ValueError:
            return None, None

    @staticmethod
    def _search_order_rows(
        rows: list[dict[str, Any]],
        *,
        start_strike: int | None,
        end_strike: int | None,
        ideal_premium: float | None,
        minimum_premium: float | None,
        minimum_oi: int | None,
    ) -> dict[str, list[dict[str, Any]]]:
        if start_strike is None or end_strike is None:
            return {"start_to_end": [], "end_to_start": []}
        low = min(start_strike, end_strike)
        high = max(start_strike, end_strike)
        filtered = [row for row in rows if low <= row["strike"] <= high]
        start_to_end = sorted(filtered, key=lambda item: item["strike"], reverse=start_strike > end_strike)
        end_to_start = list(reversed(start_to_end))
        return {
            "start_to_end": [
                HistoricalMarketExplorerService._search_row(
                    row, ideal_premium, minimum_premium, minimum_oi
                )
                for row in start_to_end
            ],
            "end_to_start": [
                HistoricalMarketExplorerService._search_row(
                    row, ideal_premium, minimum_premium, minimum_oi
                )
                for row in end_to_start
            ],
        }

    @staticmethod
    def _search_row(
        row: dict[str, Any],
        ideal_premium: float | None,
        minimum_premium: float | None,
        minimum_oi: int | None,
    ) -> dict[str, Any]:
        def side(prefix: str) -> dict[str, Any]:
            ltp = row.get(f"{prefix}_ltp")
            oi = row.get(f"{prefix}_oi")
            return {
                "symbol": row.get(f"{prefix}_symbol"),
                "premium": ltp,
                "oi": oi,
                "meets_ideal": ltp is not None and ideal_premium is not None and ltp >= ideal_premium,
                "meets_minimum": ltp is not None and minimum_premium is not None and ltp >= minimum_premium,
                "meets_oi": oi is not None and minimum_oi is not None and oi >= minimum_oi,
            }

        return {"strike": row["strike"], "CE": side("CE"), "PE": side("PE")}

    @staticmethod
    def _premium_threshold(
        *,
        direct: float | None,
        reference: float | None,
        factor_pct: float | None,
    ) -> float | None:
        if direct is not None:
            return direct
        if reference is None or factor_pct is None:
            return None
        return reference * factor_pct / 100.0

    @classmethod
    def _manual_scan_row(
        cls,
        *,
        observation: Any,
        prior_daily: tuple[Any, ...],
        history_sessions: int,
        ideal_threshold: float | None,
        minimum_threshold: float | None,
        minimum_oi: int | None,
    ) -> dict[str, Any]:
        premium = observation.ltp
        oi = observation.oi
        meets_oi = minimum_oi is None or oi >= minimum_oi
        meets_ideal = ideal_threshold is not None and premium >= ideal_threshold
        meets_minimum = minimum_threshold is not None and premium >= minimum_threshold
        history_available = len(prior_daily)
        history_ready = history_available >= history_sessions
        row = {
            "strike": observation.identity.strike,
            "symbol": observation.identity.raw_symbol,
            "premium": premium,
            "oi": oi,
            "volume": observation.volume,
            "OPT_PRV_DHH": max((item.high for item in prior_daily), default=None),
            "OPT_PRV_DLL": min((item.low for item in prior_daily), default=None),
            "history_sessions_requested": history_sessions,
            "history_sessions_available": history_available,
            "history_ready": history_ready,
            "prior_sessions_used": ",".join(item.session_date.isoformat() for item in prior_daily),
            "meets_oi": meets_oi,
            "meets_ideal": meets_ideal,
            "meets_minimum": meets_minimum,
            "selected": False,
            "selection_stage": "",
        }
        row["reason"] = cls._manual_scan_reason(
            premium=premium,
            oi=oi,
            meets_oi=meets_oi,
            meets_ideal=meets_ideal,
            meets_minimum=meets_minimum,
            ideal_threshold=ideal_threshold,
            minimum_threshold=minimum_threshold,
            minimum_oi=minimum_oi,
            history_ready=history_ready,
        )
        return row

    @staticmethod
    def _manual_scan_reason(
        *,
        premium: float,
        oi: int,
        meets_oi: bool,
        meets_ideal: bool,
        meets_minimum: bool,
        ideal_threshold: float | None,
        minimum_threshold: float | None,
        minimum_oi: int | None,
        history_ready: bool,
    ) -> str:
        parts: list[str] = []
        if not history_ready:
            parts.append("lookback incomplete")
        if minimum_oi is not None and not meets_oi:
            parts.append(f"OI {oi} < {minimum_oi}")
        if ideal_threshold is not None:
            parts.append(
                f"premium {premium} {'>=' if meets_ideal else '<'} ideal {ideal_threshold:.2f}"
            )
        if minimum_threshold is not None:
            parts.append(
                f"premium {premium} {'>=' if meets_minimum else '<'} minimum {minimum_threshold:.2f}"
            )
        if not parts:
            return "No premium/OI thresholds supplied"
        return "; ".join(parts)

    @staticmethod
    def _select_manual_scan_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        for stage, predicate in (
            ("ideal", lambda row: row["meets_oi"] and row["meets_ideal"]),
            ("minimum", lambda row: row["meets_oi"] and row["meets_minimum"]),
        ):
            for row in rows:
                if predicate(row):
                    row["selection_stage"] = stage
                    row["reason"] = f"Selected first {stage} qualifying strike in start-to-end order"
                    return row
        return None

    @staticmethod
    def _history_sessions(
        *,
        available: tuple[date, ...],
        session_date: date,
        from_date: date | None,
        to_date: date | None,
        sessions_back: int | None,
    ) -> tuple[date, ...]:
        if sessions_back is not None and sessions_back < 1:
            raise HistoricalMarketExplorerError("sessions_back must be positive")
        if from_date is not None or to_date is not None:
            start = from_date or session_date
            end = to_date or session_date
            if end < start:
                raise HistoricalMarketExplorerError("to_date must be on or after from_date")
            days = []
            cursor = start
            while cursor <= end:
                days.append(cursor)
                cursor += timedelta(days=1)
            return tuple(days)
        eligible = [item for item in available if item <= session_date]
        limit = sessions_back or 5
        return tuple(eligible[-limit:])

    @staticmethod
    def _flatten_workbook_inputs(payload: dict[str, Any]) -> dict[str, Any]:
        row: dict[str, Any] = {}
        for group in ("spot", "selected_option"):
            for key, value in payload[group].items():
                row[key] = value
        for prefix in ("premium_0916", "orpt", "rc"):
            for key, value in payload[prefix].items():
                row[f"{prefix}_{key}"] = value
        row["historical_lot_size"] = payload["historical_lot_size"]
        row["minimum_oi_units"] = payload["minimum_oi_units"]
        return row

    @staticmethod
    def _rows_to_csv(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return ""
        fieldnames = sorted({key for row in rows for key in row})
        handle = io.StringIO()
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        return handle.getvalue()


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_time(value: str | None, default: time | None = None) -> time | None:
    if value is None or value == "":
        return default
    return time.fromisoformat(value)


def parse_option_type(value: str) -> OptionType:
    normalized = value.strip().upper()
    if normalized in {"CE", "CALL"}:
        return OptionType.CALL
    if normalized in {"PE", "PUT"}:
        return OptionType.PUT
    raise HistoricalMarketExplorerError(f"Unsupported option type: {value!r}")
