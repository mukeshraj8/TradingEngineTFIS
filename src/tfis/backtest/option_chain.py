from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from tfis.backtest.csv_loader import BacktestCsvError
from tfis.domain.enums import OptionType


OPTION_CHAIN_REQUIRED_COLUMNS = (
    "timestamp",
    "symbol",
    "option_type",
    "strike",
    "expiry",
    "bid",
    "ask",
    "ltp",
    "oi",
    "volume",
)


@dataclass(frozen=True, slots=True)
class OptionChainContract:
    timestamp: datetime
    symbol: str
    option_type: OptionType
    strike: int
    expiry: date
    bid: float
    ask: float
    ltp: float
    oi: int
    volume: int

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        if self.strike < 0:
            raise ValueError("strike must be non-negative")
        if self.bid < 0 or self.ask < 0 or self.ltp < 0:
            raise ValueError("bid, ask, and ltp must be non-negative")
        if self.ask < self.bid:
            raise ValueError("ask must be greater than or equal to bid")
        if self.oi < 0 or self.volume < 0:
            raise ValueError("oi and volume must be non-negative")

    @property
    def bid_ask_spread(self) -> float:
        return float(self.ask - self.bid)


@dataclass(frozen=True, slots=True)
class OptionSelectionRequest:
    option_type: OptionType
    start_strike: int
    end_strike: int
    ideal_premium: float
    minimum_premium: float
    minimum_oi: int
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class OptionSelectionResult:
    selected: bool
    selected_contract: OptionChainContract | None
    selection_reason: str
    candidate_count: int


class OptionChainSelector:
    def select(
        self,
        request: OptionSelectionRequest,
        contracts: list[OptionChainContract],
    ) -> OptionSelectionResult:
        timestamp_matches = [
            contract for contract in contracts if contract.timestamp == request.timestamp
        ]
        if not timestamp_matches:
            return OptionSelectionResult(
                selected=False,
                selected_contract=None,
                selection_reason=(
                    "No option-chain rows found for timestamp "
                    f"{request.timestamp.isoformat()}"
                ),
                candidate_count=0,
            )

        type_matches = [
            contract
            for contract in timestamp_matches
            if contract.option_type == request.option_type
        ]
        if not type_matches:
            return OptionSelectionResult(
                selected=False,
                selected_contract=None,
                selection_reason=(
                    "No option-chain contracts found for option type "
                    f"{request.option_type.value}"
                ),
                candidate_count=0,
            )

        lower_strike = min(request.start_strike, request.end_strike)
        upper_strike = max(request.start_strike, request.end_strike)
        strike_matches = [
            contract
            for contract in type_matches
            if lower_strike <= contract.strike <= upper_strike
        ]
        if not strike_matches:
            return OptionSelectionResult(
                selected=False,
                selected_contract=None,
                selection_reason=(
                    "No option-chain contracts found within strike range "
                    f"{lower_strike}-{upper_strike}"
                ),
                candidate_count=0,
            )

        oi_matches = [
            contract for contract in strike_matches if contract.oi >= request.minimum_oi
        ]
        if not oi_matches:
            return OptionSelectionResult(
                selected=False,
                selected_contract=None,
                selection_reason=(
                    "No option-chain contracts meet minimum_oi "
                    f"{request.minimum_oi}"
                ),
                candidate_count=0,
            )

        premium_matches = [
            contract
            for contract in oi_matches
            if contract.ltp >= request.minimum_premium
        ]
        if not premium_matches:
            return OptionSelectionResult(
                selected=False,
                selected_contract=None,
                selection_reason=(
                    "No option-chain contracts meet minimum_premium "
                    f"{request.minimum_premium:.2f}"
                ),
                candidate_count=0,
            )

        midpoint = (request.start_strike + request.end_strike) / 2.0
        selected_contract = min(
            premium_matches,
            key=lambda contract: (
                abs(contract.ltp - request.ideal_premium),
                contract.bid_ask_spread,
                -contract.oi,
                abs(contract.strike - midpoint),
            ),
        )
        return OptionSelectionResult(
            selected=True,
            selected_contract=selected_contract,
            selection_reason="Selected contract closest to ideal premium.",
            candidate_count=len(premium_matches),
        )


def load_option_chain_csv(path: str | Path) -> list[OptionChainContract]:
    csv_path = Path(path)
    rows = _read_rows(csv_path)
    contracts: list[OptionChainContract] = []
    for index, row in enumerate(rows, start=2):
        contracts.append(
            OptionChainContract(
                timestamp=_parse_timestamp(csv_path, row_number=index, value=row["timestamp"]),
                symbol=_parse_text(csv_path, row_number=index, column="symbol", value=row["symbol"]),
                option_type=_parse_option_type(
                    csv_path,
                    row_number=index,
                    value=row["option_type"],
                ),
                strike=_parse_int(csv_path, row_number=index, column="strike", value=row["strike"]),
                expiry=_parse_date(csv_path, row_number=index, value=row["expiry"]),
                bid=_parse_float(csv_path, row_number=index, column="bid", value=row["bid"]),
                ask=_parse_float(csv_path, row_number=index, column="ask", value=row["ask"]),
                ltp=_parse_float(csv_path, row_number=index, column="ltp", value=row["ltp"]),
                oi=_parse_int(csv_path, row_number=index, column="oi", value=row["oi"]),
                volume=_parse_int(csv_path, row_number=index, column="volume", value=row["volume"]),
            )
        )
    return sorted(contracts, key=lambda contract: (contract.timestamp, contract.option_type.value, contract.strike))


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise BacktestCsvError(f"CSV file not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        normalized_fieldnames = {name.strip().lower(): name for name in fieldnames if name}
        missing = [
            column for column in OPTION_CHAIN_REQUIRED_COLUMNS if column not in normalized_fieldnames
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


def _parse_date(path: Path, *, row_number: int, value: str) -> date:
    if not value:
        raise BacktestCsvError(f"Missing expiry at row {row_number} in {path}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise BacktestCsvError(
            f"Invalid expiry date at row {row_number} in {path}: {value}"
        ) from exc


def _parse_option_type(path: Path, *, row_number: int, value: str) -> OptionType:
    if not value:
        raise BacktestCsvError(f"Missing option_type at row {row_number} in {path}")
    normalized = value.strip().upper()
    try:
        return OptionType(normalized)
    except ValueError as exc:
        raise BacktestCsvError(
            f"Invalid option_type at row {row_number} in {path}: {value}"
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


def _parse_int(path: Path, *, row_number: int, column: str, value: str) -> int:
    numeric_value = _parse_float(path, row_number=row_number, column=column, value=value)
    if int(numeric_value) != numeric_value:
        raise BacktestCsvError(
            f"Invalid integer value for {column} at row {row_number} in {path}: {value}"
        )
    return int(numeric_value)
