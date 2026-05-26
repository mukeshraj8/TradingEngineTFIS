from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tfis.backtest.csv_loader import BacktestCsvError


SHARED_DATA_FILE_NAMES = {
    "daily_csv": "daily.csv",
    "weekly_csv": "weekly.csv",
    "monthly_csv": "monthly.csv",
    "option_levels_csv": "option_levels.csv",
    "option_chain_csv": "option_chain.csv",
    "option_intraday_csv": "option_intraday.csv",
}


@dataclass(frozen=True, slots=True)
class SharedBacktestDataset:
    daily_csv: Path | None
    weekly_csv: Path | None
    monthly_csv: Path | None
    option_levels_csv: Path | None
    option_chain_csv: Path | None
    option_intraday_csv: Path | None
    missing_files: tuple[str, ...]
    is_complete: bool


def discover_shared_data_roots(root: str | Path) -> list[Path]:
    base_root = Path(root)
    if not base_root.exists() or not base_root.is_dir():
        return []

    discovered: list[Path] = []
    if _looks_like_dataset_root(base_root):
        discovered.append(base_root)

    for child in sorted(base_root.iterdir()):
        if child.is_dir() and _looks_like_dataset_root(child):
            discovered.append(child)
    return discovered


def resolve_shared_backtest_dataset(
    shared_root: str | Path,
    *,
    strategy_path: str | Path | None = None,
    strategy_root: str | Path | None = None,
    allow_partial: bool = False,
) -> SharedBacktestDataset:
    base_root = Path(shared_root)
    if not base_root.exists() or not base_root.is_dir():
        raise BacktestCsvError(f"Shared data root not found or not a directory: {base_root}")

    dataset_root = _select_dataset_root(
        base_root,
        strategy_path=Path(strategy_path) if strategy_path is not None else None,
        strategy_root=Path(strategy_root) if strategy_root is not None else None,
    )

    dataset = _build_dataset(dataset_root)
    if not allow_partial and not dataset.is_complete:
        raise BacktestCsvError(
            "Shared data root is missing required normalized files in "
            f"{dataset_root}: {', '.join(dataset.missing_files)}"
        )
    return dataset


def _select_dataset_root(
    base_root: Path,
    *,
    strategy_path: Path | None,
    strategy_root: Path | None,
) -> Path:
    if _looks_like_dataset_root(base_root):
        return base_root

    candidates = discover_shared_data_roots(base_root)
    if not candidates:
        raise BacktestCsvError(
            f"Shared data root contains no normalized dataset folders: {base_root}"
        )

    hints = _collect_instrument_hints(strategy_path=strategy_path, strategy_root=strategy_root)
    for hint in hints:
        hinted_root = base_root / hint
        if hinted_root in candidates:
            return hinted_root

    if len(candidates) == 1:
        return candidates[0]

    available = ", ".join(path.name for path in candidates)
    raise BacktestCsvError(
        "Shared data root is ambiguous. Pass an instrument-scoped folder such as "
        f"shared_root/nifty or provide a strategy path/root that identifies the "
        f"instrument. Available dataset roots: {available}"
    )


def _collect_instrument_hints(
    *,
    strategy_path: Path | None,
    strategy_root: Path | None,
) -> list[str]:
    hints: list[str] = []
    for path in (strategy_path, strategy_root):
        if path is None:
            continue
        for part in path.parts:
            normalized = part.strip().lower()
            if normalized and normalized not in hints:
                hints.append(normalized)
    return hints


def _build_dataset(dataset_root: Path) -> SharedBacktestDataset:
    resolved_paths = {
        field_name: _resolve_optional_file(dataset_root / file_name)
        for field_name, file_name in SHARED_DATA_FILE_NAMES.items()
    }
    missing = tuple(
        file_name
        for field_name, file_name in SHARED_DATA_FILE_NAMES.items()
        if resolved_paths[field_name] is None
    )
    return SharedBacktestDataset(
        daily_csv=resolved_paths["daily_csv"],
        weekly_csv=resolved_paths["weekly_csv"],
        monthly_csv=resolved_paths["monthly_csv"],
        option_levels_csv=resolved_paths["option_levels_csv"],
        option_chain_csv=resolved_paths["option_chain_csv"],
        option_intraday_csv=resolved_paths["option_intraday_csv"],
        missing_files=missing,
        is_complete=not missing,
    )


def _resolve_optional_file(path: Path) -> Path | None:
    return path if path.is_file() else None


def _looks_like_dataset_root(path: Path) -> bool:
    return any((path / file_name).is_file() for file_name in SHARED_DATA_FILE_NAMES.values())
