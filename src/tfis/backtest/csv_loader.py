from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from tfis.market_structure.ohlc import OhlcBar


class BacktestCsvError(ValueError):
    """Raised when a backtest CSV is missing required fields or contains bad values."""


DAILY_REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close")
OPTION_REQUIRED_COLUMNS = (
    "timestamp",
    "opt_prv_2dhh",
    "opt_prv_2dll",
    "opt_prv_3dhh",
    "opt_prv_3dll",
)


def load_daily_bars_csv(path: str | Path) -> list[OhlcBar]:
    csv_path = Path(path)
    rows = _read_rows(csv_path, DAILY_REQUIRED_COLUMNS)
    bars: list[OhlcBar] = []
    for index, row in enumerate(rows, start=2):
        timestamp = _parse_timestamp(csv_path, row_number=index, value=row["timestamp"])
        bars.append(
            OhlcBar(
                timestamp=timestamp,
                open=_parse_float(csv_path, row_number=index, column="open", value=row["open"]),
                high=_parse_float(csv_path, row_number=index, column="high", value=row["high"]),
                low=_parse_float(csv_path, row_number=index, column="low", value=row["low"]),
                close=_parse_float(csv_path, row_number=index, column="close", value=row["close"]),
                volume=_parse_optional_float(
                    csv_path,
                    row_number=index,
                    column="volume",
                    value=row.get("volume"),
                ),
            )
        )
    return bars


def load_option_levels_csv(path: str | Path) -> dict[str, float]:
    csv_path = Path(path)
    rows = _read_rows(csv_path, OPTION_REQUIRED_COLUMNS)
    snapshots: list[tuple[datetime, dict[str, float]]] = []
    for index, row in enumerate(rows, start=2):
        timestamp = _parse_timestamp(csv_path, row_number=index, value=row["timestamp"])
        snapshots.append(
            (
                timestamp,
                {
                    "OPT_PRV_2DHH": _parse_float(
                        csv_path,
                        row_number=index,
                        column="opt_prv_2dhh",
                        value=row["opt_prv_2dhh"],
                    ),
                    "OPT_PRV_2DLL": _parse_float(
                        csv_path,
                        row_number=index,
                        column="opt_prv_2dll",
                        value=row["opt_prv_2dll"],
                    ),
                    "OPT_PRV_3DHH": _parse_float(
                        csv_path,
                        row_number=index,
                        column="opt_prv_3dhh",
                        value=row["opt_prv_3dhh"],
                    ),
                    "OPT_PRV_3DLL": _parse_float(
                        csv_path,
                        row_number=index,
                        column="opt_prv_3dll",
                        value=row["opt_prv_3dll"],
                    ),
                },
            )
        )

    if not snapshots:
        raise BacktestCsvError(f"CSV contains no data rows: {csv_path}")

    snapshots.sort(key=lambda item: item[0])
    return snapshots[-1][1]


def _read_rows(path: Path, required_columns: tuple[str, ...]) -> list[dict[str, str]]:
    if not path.is_file():
        raise BacktestCsvError(f"CSV file not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        normalized_fieldnames = {name.strip().lower(): name for name in fieldnames if name}
        missing = [column for column in required_columns if column not in normalized_fieldnames]
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


def _parse_timestamp(path: Path, *, row_number: int, value: str) -> datetime:
    if not value:
        raise BacktestCsvError(
            f"Missing timestamp at row {row_number} in {path}"
        )
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise BacktestCsvError(
            f"Invalid timestamp at row {row_number} in {path}: {value}"
        ) from exc


def _parse_float(
    path: Path,
    *,
    row_number: int,
    column: str,
    value: str,
) -> float:
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
