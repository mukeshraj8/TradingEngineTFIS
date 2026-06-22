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
    expiry_dates: tuple[date, ...] = ()


@dataclass(frozen=True, slots=True)
class OptionSelectionResult:
    selected: bool
    selected_contract: OptionChainContract | None
    selection_reason: str
    candidate_count: int
    attempted_expiries: tuple[date, ...] = ()


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

        expiry_dates = request.expiry_dates or tuple(
            sorted({contract.expiry for contract in type_matches})[:2]
        )
        if not expiry_dates:
            return OptionSelectionResult(
                selected=False,
                selected_contract=None,
                selection_reason="No option-chain expiries found for selection.",
                candidate_count=0,
            )

        failed_results: list[OptionSelectionResult] = []
        for expiry_date in expiry_dates:
            expiry_matches = [
                contract for contract in type_matches if contract.expiry == expiry_date
            ]
            if not expiry_matches:
                failed_results.append(
                    OptionSelectionResult(
                        selected=False,
                        selected_contract=None,
                        selection_reason=(
                            "No option-chain contracts found for expiry "
                            f"{expiry_date.isoformat()}"
                        ),
                        candidate_count=0,
                        attempted_expiries=(expiry_date,),
                    )
                )
                continue

            result = self._select_within_expiry(request, expiry_matches)
            if result.selected:
                if expiry_date != expiry_dates[0]:
                    return OptionSelectionResult(
                        selected=True,
                        selected_contract=result.selected_contract,
                        selection_reason=(
                            result.selection_reason
                            + f" Near expiry {expiry_dates[0].isoformat()} failed; "
                            + f"selected fallback expiry {expiry_date.isoformat()}."
                        ),
                        candidate_count=result.candidate_count,
                        attempted_expiries=expiry_dates,
                    )
                return OptionSelectionResult(
                    selected=True,
                    selected_contract=result.selected_contract,
                    selection_reason=result.selection_reason,
                    candidate_count=result.candidate_count,
                    attempted_expiries=expiry_dates,
                )
            failed_results.append(result)

        primary_failure = failed_results[0]
        if len(failed_results) == 1:
            return primary_failure
        return OptionSelectionResult(
            selected=False,
            selected_contract=None,
            selection_reason="; ".join(
                f"Expiry {expiry_date.isoformat()}: {result.selection_reason}"
                for expiry_date, result in zip(expiry_dates, failed_results)
            ),
            candidate_count=sum(result.candidate_count for result in failed_results),
            attempted_expiries=expiry_dates,
        )

    def _select_within_expiry(
        self,
        request: OptionSelectionRequest,
        type_matches: list[OptionChainContract],
    ) -> OptionSelectionResult:

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

        ideal_search_order = self._ordered_by_search_direction(
            premium_matches,
            start_strike=request.start_strike,
            end_strike=request.end_strike,
        )
        for contract in ideal_search_order:
            if contract.ltp >= request.ideal_premium:
                return OptionSelectionResult(
                    selected=True,
                    selected_contract=contract,
                    selection_reason="Selected first strike meeting ideal premium in rule-sheet search order.",
                    candidate_count=len(premium_matches),
                )

        selected_contract = next(
            contract
            for contract in reversed(ideal_search_order)
            if contract.ltp >= request.minimum_premium
        )
        return OptionSelectionResult(
            selected=True,
            selected_contract=selected_contract,
            selection_reason="Selected first strike meeting minimum premium in reverse rule-sheet search order.",
            candidate_count=len(premium_matches),
        )

    @staticmethod
    def _ordered_by_search_direction(
        contracts: list[OptionChainContract],
        *,
        start_strike: int,
        end_strike: int,
    ) -> list[OptionChainContract]:
        return sorted(
            contracts,
            key=lambda contract: contract.strike,
            reverse=start_strike > end_strike,
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
