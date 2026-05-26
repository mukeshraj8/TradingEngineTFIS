from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from tfis.backtest.csv_loader import BacktestCsvError
from tfis.market_structure.ohlc import OhlcBar


CONTRACT_INTRADAY_REQUIRED_COLUMNS = (
    "timestamp",
    "symbol",
    "open",
    "high",
    "low",
    "close",
)


@dataclass(frozen=True, slots=True)
class ContractIntradayBar:
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None

    def to_ohlc_bar(self) -> OhlcBar:
        return OhlcBar(
            timestamp=self.timestamp,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
        )


def load_contract_intraday_bars_csv(path: str | Path) -> list[ContractIntradayBar]:
    csv_path = Path(path)
    rows = _read_rows(csv_path)
    bars: list[ContractIntradayBar] = []
    for index, row in enumerate(rows, start=2):
        bars.append(
            ContractIntradayBar(
                timestamp=_parse_timestamp(
                    csv_path,
                    row_number=index,
                    value=row["timestamp"],
                ),
                symbol=_parse_text(
                    csv_path,
                    row_number=index,
                    column="symbol",
                    value=row["symbol"],
                ),
                open=_parse_float(
                    csv_path,
                    row_number=index,
                    column="open",
                    value=row["open"],
                ),
                high=_parse_float(
                    csv_path,
                    row_number=index,
                    column="high",
                    value=row["high"],
                ),
                low=_parse_float(
                    csv_path,
                    row_number=index,
                    column="low",
                    value=row["low"],
                ),
                close=_parse_float(
                    csv_path,
                    row_number=index,
                    column="close",
                    value=row["close"],
                ),
                volume=_parse_optional_float(
                    csv_path,
                    row_number=index,
                    column="volume",
                    value=row.get("volume"),
                ),
            )
        )
    return sorted(bars, key=lambda item: (item.timestamp, item.symbol))


def build_contract_intraday_lookup(
    bars: list[ContractIntradayBar],
) -> dict[date, dict[str, list[OhlcBar]]]:
    lookup: dict[date, dict[str, list[OhlcBar]]] = {}
    for bar in sorted(bars, key=lambda item: (item.timestamp, item.symbol)):
        by_symbol = lookup.setdefault(bar.timestamp.date(), {})
        by_symbol.setdefault(bar.symbol, []).append(bar.to_ohlc_bar())
    return lookup


def resolve_contract_intraday_bars(
    lookup: dict[date, dict[str, list[OhlcBar]]],
    *,
    session_date: date,
    symbol: str,
    after_timestamp: datetime | None = None,
) -> list[OhlcBar]:
    bars = list(lookup.get(session_date, {}).get(symbol, []))
    if after_timestamp is not None:
        bars = [bar for bar in bars if bar.timestamp > after_timestamp]
    return bars


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise BacktestCsvError(f"CSV file not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        normalized_fieldnames = {name.strip().lower(): name for name in fieldnames if name}
        missing = [
            column
            for column in CONTRACT_INTRADAY_REQUIRED_COLUMNS
            if column not in normalized_fieldnames
        ]
        if missing:
            raise BacktestCsvError(
                f"Missing required columns in {path}: {', '.join(missing)}"
            )

        rows: list[dict[str, str]] = []
        for raw_row in reader:
            row: dict[str, str] = {}
            for normalized_name, original_name in normalized_fieldnames.items():
                value = raw_row.get(original_name, "")
                row[normalized_name] = value.strip() if isinstance(value, str) else ""
            if any(value != "" for value in row.values()):
                rows.append(row)

    if not rows:
        raise BacktestCsvError(f"CSV contains no data rows: {path}")
    return rows


def _parse_text(path: Path, *, row_number: int, column: str, value: str) -> str:
    if not value:
        raise BacktestCsvError(
            f"Missing value for {column} at row {row_number} in {path}"
        )
    return value


def _parse_timestamp(path: Path, *, row_number: int, value: str) -> datetime:
    if not value:
        raise BacktestCsvError(f"Missing timestamp at row {row_number} in {path}")
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise BacktestCsvError(
            f"Invalid timestamp at row {row_number} in {path}: {value}"
        ) from exc


def _parse_float(path: Path, *, row_number: int, column: str, value: str) -> float:
    if value == "":
        raise BacktestCsvError(
            f"Missing value for {column} at row {row_number} in {path}"
        )
    try:
        return float(value)
    except ValueError as exc:
        raise BacktestCsvError(
            f"Invalid numeric value for {column} at row {row_number} in {path}: {value}"
        ) from exc


def _parse_optional_float(
    path: Path,
    *,
    row_number: int,
    column: str,
    value: str | None,
) -> float | None:
    if value is None or value == "":
        return None
    return _parse_float(path, row_number=row_number, column=column, value=value)
