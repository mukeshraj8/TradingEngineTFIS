from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from tfis.backtest.csv_loader import BacktestCsvError
from tfis.market_structure.ohlc import OhlcBar
from tfis.monthly_status import MonthlyStatusEngine, MonthlyStatusReferenceLevels, MonthlyStatusResult
from tfis.strategy import StrategyBranchSelector


MONTHLY_REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close")
WEEKLY_REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close")


@dataclass(frozen=True, slots=True)
class HistoricalMonthlyStatusContext:
    timestamp: datetime
    status_result: MonthlyStatusResult
    selected_branch_unique_codes: list[str]


@dataclass(frozen=True, slots=True)
class HistoricalMonthlyStatusSkip:
    timestamp: datetime
    reason: str


@dataclass(frozen=True, slots=True)
class MonthlyStatusContextComputation:
    timestamp: datetime
    context: HistoricalMonthlyStatusContext | None
    skip: HistoricalMonthlyStatusSkip | None


def load_monthly_bars_csv(path: str | Path) -> list[OhlcBar]:
    return _load_reference_bars_csv(Path(path), MONTHLY_REQUIRED_COLUMNS)


def load_weekly_bars_csv(path: str | Path) -> list[OhlcBar]:
    return _load_reference_bars_csv(Path(path), WEEKLY_REQUIRED_COLUMNS)


def build_monthly_status_context(
    *,
    instrument_group: str,
    current_timestamp: datetime,
    monthly_bars: list[OhlcBar],
    weekly_bars: list[OhlcBar],
    strategy_root: str | Path,
    branch_selector: StrategyBranchSelector | None = None,
    monthly_status_engine: MonthlyStatusEngine | None = None,
) -> MonthlyStatusContextComputation:
    sorted_monthly = sorted(monthly_bars, key=lambda bar: bar.timestamp)
    sorted_weekly = sorted(weekly_bars, key=lambda bar: bar.timestamp)
    eligible_monthly = [
        bar for bar in sorted_monthly if bar.timestamp <= current_timestamp
    ]
    eligible_weekly = [bar for bar in sorted_weekly if bar.timestamp <= current_timestamp]
    previous_month_candidates = [
        bar
        for bar in eligible_monthly
        if (bar.timestamp.year, bar.timestamp.month)
        < (current_timestamp.year, current_timestamp.month)
    ]
    current_month_bars = [
        bar
        for bar in eligible_monthly
        if bar.timestamp.year == current_timestamp.year
        and bar.timestamp.month == current_timestamp.month
    ]
    if not previous_month_candidates:
        return MonthlyStatusContextComputation(
            timestamp=current_timestamp,
            context=None,
            skip=HistoricalMonthlyStatusSkip(
                timestamp=current_timestamp,
                reason="insufficient completed monthly data",
            ),
        )
    if not current_month_bars:
        return MonthlyStatusContextComputation(
            timestamp=current_timestamp,
            context=None,
            skip=HistoricalMonthlyStatusSkip(
                timestamp=current_timestamp,
                reason="missing current month reference bars",
            ),
        )
    previous_month = previous_month_candidates[-1]
    current_year, current_week, _ = current_timestamp.isocalendar()
    previous_week_candidates = [
        bar
        for bar in eligible_weekly
        if (bar.timestamp.isocalendar().year, bar.timestamp.isocalendar().week)
        < (current_year, current_week)
    ]
    current_week_bars = [
        bar
        for bar in eligible_weekly
        if _same_iso_week(bar.timestamp, current_timestamp)
    ]
    if not previous_week_candidates:
        return MonthlyStatusContextComputation(
            timestamp=current_timestamp,
            context=None,
            skip=HistoricalMonthlyStatusSkip(
                timestamp=current_timestamp,
                reason="insufficient completed weekly data",
            ),
        )
    if not current_week_bars:
        return MonthlyStatusContextComputation(
            timestamp=current_timestamp,
            context=None,
            skip=HistoricalMonthlyStatusSkip(
                timestamp=current_timestamp,
                reason="missing current week reference bars",
            ),
        )
    previous_week = previous_week_candidates[-1]

    levels = MonthlyStatusReferenceLevels(
        PMH=previous_month.high,
        PML=previous_month.low,
        CMH=max(bar.high for bar in current_month_bars),
        CML=min(bar.low for bar in current_month_bars),
        PWH=previous_week.high,
        PWL=previous_week.low,
        CWH=max(bar.high for bar in current_week_bars),
        CWL=min(bar.low for bar in current_week_bars),
        current_price=eligible_monthly[-1].close,
    )
    engine = monthly_status_engine or MonthlyStatusEngine()
    selector = branch_selector or StrategyBranchSelector()
    status_result = engine.classify(instrument_group, levels)
    strategy_root_path = Path(strategy_root)
    strategy_paths = [
        path for path in strategy_root_path.iterdir() if path.is_dir()
    ]
    selected_rules = selector.select(strategy_paths, status_result.status)

    return MonthlyStatusContextComputation(
        timestamp=current_timestamp,
        context=HistoricalMonthlyStatusContext(
            timestamp=current_timestamp,
            status_result=status_result,
            selected_branch_unique_codes=[
                rule.unique_code for rule in selected_rules
            ],
        ),
        skip=None,
    )


def _load_reference_bars_csv(
    path: Path,
    required_columns: tuple[str, ...],
) -> list[OhlcBar]:
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

    bars: list[OhlcBar] = []
    for index, row in enumerate(rows, start=2):
        bars.append(
            OhlcBar(
                timestamp=_parse_timestamp(path, row_number=index, value=row["timestamp"]),
                open=_parse_float(path, row_number=index, column="open", value=row["open"]),
                high=_parse_float(path, row_number=index, column="high", value=row["high"]),
                low=_parse_float(path, row_number=index, column="low", value=row["low"]),
                close=_parse_float(path, row_number=index, column="close", value=row["close"]),
            )
        )
    return bars


def _parse_timestamp(path: Path, *, row_number: int, value: str) -> datetime:
    if not value:
        raise BacktestCsvError(f"Missing timestamp at row {row_number} in {path}")
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


def _same_iso_week(timestamp: datetime, current_timestamp: datetime) -> bool:
    left = timestamp.isocalendar()
    right = current_timestamp.isocalendar()
    return left.year == right.year and left.week == right.week
