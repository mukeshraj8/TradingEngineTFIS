from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import product
from pathlib import Path

import yaml

from tfis.backtest.backtest_runner import BacktestRunner
from tfis.backtest.metrics import build_backtest_metrics
from tfis.backtest.models import BacktestInput, BacktestMetrics, BacktestTradeResult
from tfis.market_structure.ohlc import OhlcBar


PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class ParameterSweepVariantResult:
    variant_id: str
    parameters: dict[str, float]
    success: bool
    error: str | None
    result: BacktestTradeResult | None
    metrics: BacktestMetrics | None
    accepted: bool
    rejection_reason: str | None
    trade_outputs: "ParameterSweepTradeOutputs | None"
    risk_distance: float | None
    reward_distance: float | None
    reward_risk_ratio: float | None


@dataclass(frozen=True, slots=True)
class ParameterSweepSummary:
    total_variants: int
    successful_variants: int
    failed_variants: int
    accepted_trades: int
    rejected_trades: int


@dataclass(frozen=True, slots=True)
class ParameterSweepReport:
    experiment_path: Path
    base_strategy: Path
    variants: list[ParameterSweepVariantResult]
    summary: ParameterSweepSummary
    ranking: list["ParameterSweepRankingEntry"]


@dataclass(frozen=True, slots=True)
class ParameterSweepTradeOutputs:
    start_strike: int
    entry_price: float
    target_price: float
    stoploss_price: float
    ideal_premium: float
    minimum_premium: float


@dataclass(frozen=True, slots=True)
class ParameterSweepRankingEntry:
    rank: int
    variant_id: str
    accepted: bool
    rejection_reason: str | None
    parameters: dict[str, float]
    trade_outputs: ParameterSweepTradeOutputs | None
    risk_distance: float | None
    reward_distance: float | None
    reward_risk_ratio: float | None


def sample_daily_bars() -> list[OhlcBar]:
    return [
        OhlcBar(datetime(2026, 5, 19, 15, 30), 22150.0, 22300.0, 21900.0, 22250.0),
        OhlcBar(datetime(2026, 5, 20, 15, 30), 22250.0, 22400.0, 22000.0, 22350.0),
        OhlcBar(datetime(2026, 5, 21, 15, 30), 22350.0, 22500.0, 22100.0, 22420.0),
        OhlcBar(datetime(2026, 5, 22, 15, 30), 22400.0, 22450.0, 22200.0, 22380.0),
        OhlcBar(datetime(2026, 5, 23, 15, 30), 22320.0, 22400.0, 22100.0, 22310.0),
    ]


def sample_runtime_values(*, parameters: dict[str, float]) -> dict[str, object]:
    return {
        "ENTRY": 200.0,
        "OPT_LEVELS": {
            "OPT_PRV_3DLL": 220.0,
            "OPT_PRV_2DHH": 300.0,
        },
        "PARAMS": dict(parameters),
    }


def generate_parameter_combinations(
    overrides: dict[str, list[float]],
) -> list[dict[str, float]]:
    if not overrides:
        return [{}]

    names = list(overrides.keys())
    values_by_name: list[list[float]] = []
    for name in names:
        values = overrides[name]
        if not isinstance(values, list) or not values:
            raise ValueError(f"Override list for {name} must be a non-empty list")
        values_by_name.append([float(value) for value in values])

    combinations: list[dict[str, float]] = []
    for values in product(*values_by_name):
        combinations.append(
            {name: float(value) for name, value in zip(names, values, strict=True)}
        )
    return combinations


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Experiment YAML must contain a mapping: {path}")
    return data


def _resolve_base_strategy_path(
    experiment_path: Path,
    base_strategy_value: str,
) -> Path:
    base_path = Path(str(base_strategy_value))
    candidates = []
    if base_path.is_absolute():
        candidates.append(base_path)
    else:
        candidates.append(PROJECT_ROOT / base_path)
        candidates.append(experiment_path.parent / base_path)

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    raise ValueError(
        f"Base strategy path does not exist: {base_strategy_value}"
    )


def build_trade_outputs(
    result: BacktestTradeResult | None,
) -> ParameterSweepTradeOutputs | None:
    if result is None:
        return None
    trade_plan = result.trade_plan
    return ParameterSweepTradeOutputs(
        start_strike=trade_plan.start_strike,
        entry_price=trade_plan.entry_price,
        target_price=trade_plan.target_price,
        stoploss_price=trade_plan.stoploss_price,
        ideal_premium=trade_plan.ideal_premium,
        minimum_premium=trade_plan.minimum_premium,
    )


def calculate_risk_reward_metrics(
    trade_outputs: ParameterSweepTradeOutputs | None,
) -> tuple[float | None, float | None, float | None]:
    if trade_outputs is None:
        return None, None, None

    risk_distance = abs(trade_outputs.stoploss_price - trade_outputs.entry_price)
    reward_distance = abs(trade_outputs.entry_price - trade_outputs.target_price)
    reward_risk_ratio = None
    if risk_distance > 0:
        reward_risk_ratio = reward_distance / risk_distance
    return risk_distance, reward_distance, reward_risk_ratio


def build_parameter_sweep_ranking(
    variants: list[ParameterSweepVariantResult],
) -> list[ParameterSweepRankingEntry]:
    def _sort_key(variant: ParameterSweepVariantResult) -> tuple[float, float, float, str]:
        accepted_key = 0.0 if variant.accepted else 1.0
        risk_key = variant.risk_distance if variant.risk_distance is not None else float("inf")
        reward_key = -variant.reward_distance if variant.reward_distance is not None else float("inf")
        return accepted_key, risk_key, reward_key, variant.variant_id

    ranked_variants = sorted(variants, key=_sort_key)
    ranking: list[ParameterSweepRankingEntry] = []
    for index, variant in enumerate(ranked_variants, start=1):
        ranking.append(
            ParameterSweepRankingEntry(
                rank=index,
                variant_id=variant.variant_id,
                accepted=variant.accepted,
                rejection_reason=variant.rejection_reason,
                parameters=variant.parameters,
                trade_outputs=variant.trade_outputs,
                risk_distance=variant.risk_distance,
                reward_distance=variant.reward_distance,
                reward_risk_ratio=variant.reward_risk_ratio,
            )
        )
    return ranking


def render_parameter_sweep_markdown(report: ParameterSweepReport) -> str:
    lines = [
        "# Parameter Sweep Summary",
        "",
        f"- Experiment: `{report.experiment_path}`",
        f"- Base strategy: `{report.base_strategy}`",
        f"- Total variants: `{report.summary.total_variants}`",
        f"- Successful variants: `{report.summary.successful_variants}`",
        f"- Failed variants: `{report.summary.failed_variants}`",
        f"- Accepted trades: `{report.summary.accepted_trades}`",
        f"- Rejected trades: `{report.summary.rejected_trades}`",
        "",
        "This ranking is provisional and based on sample-mode distances only. It is not real P&L.",
        "",
        "## Top 10 Ranked Variants",
        "",
        "| Rank | Variant | Accepted | Risk Distance | Reward Distance | Reward/Risk | Parameters |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]

    for entry in report.ranking[:10]:
        risk = f"{entry.risk_distance:.2f}" if entry.risk_distance is not None else "-"
        reward = f"{entry.reward_distance:.2f}" if entry.reward_distance is not None else "-"
        ratio = f"{entry.reward_risk_ratio:.4f}" if entry.reward_risk_ratio is not None else "-"
        params = ", ".join(f"{key}={value}" for key, value in entry.parameters.items())
        lines.append(
            f"| {entry.rank} | {entry.variant_id} | {entry.accepted} | {risk} | {reward} | {ratio} | {params} |"
        )

    rejected_entries = [
        entry for entry in report.ranking if not entry.accepted or entry.rejection_reason
    ]
    if rejected_entries:
        lines.extend(
            [
                "",
                "## Rejected Variants",
                "",
                "| Variant | Reason | Parameters |",
                "| --- | --- | --- |",
            ]
        )
        for entry in rejected_entries:
            params = ", ".join(f"{key}={value}" for key, value in entry.parameters.items())
            reason = entry.rejection_reason or "Not accepted"
            lines.append(f"| {entry.variant_id} | {reason} | {params} |")

    return "\n".join(lines) + "\n"


class ParameterSweepRunner:
    def __init__(self, backtest_runner: BacktestRunner) -> None:
        self._backtest_runner = backtest_runner

    def run_experiment(self, experiment_path: str | Path) -> ParameterSweepReport:
        experiment_file = Path(experiment_path)
        config = _load_yaml(experiment_file)

        base_strategy_raw = config.get("base_strategy")
        if not isinstance(base_strategy_raw, str) or not base_strategy_raw.strip():
            raise ValueError("Experiment config must define a non-empty base_strategy")

        base_strategy_path = _resolve_base_strategy_path(
            experiment_file,
            base_strategy_raw.strip(),
        )
        if base_strategy_path.is_file():
            raise ValueError(
                "Parameter sweep requires a folder-based strategy path, not a YAML file"
            )
        if not base_strategy_path.is_dir():
            raise ValueError(
                f"Base strategy path must be a strategy folder: {base_strategy_path}"
            )

        overrides = config.get("overrides") or {}
        if not isinstance(overrides, dict):
            raise ValueError("Experiment config overrides must be a mapping")

        variants: list[ParameterSweepVariantResult] = []
        for index, parameters in enumerate(generate_parameter_combinations(overrides), start=1):
            variant_id = f"variant_{index:03d}"
            try:
                result = self._backtest_runner.run(
                    BacktestInput(
                        strategy_path=base_strategy_path,
                        daily_bars=sample_daily_bars(),
                        intraday_bars=None,
                        runtime_values=sample_runtime_values(parameters=parameters),
                        lot_size=50,
                        trades_taken_today=1,
                    )
                )
            except Exception as exc:
                variants.append(
                    ParameterSweepVariantResult(
                        variant_id=variant_id,
                        parameters=parameters,
                        success=False,
                        error=str(exc),
                        result=None,
                        metrics=None,
                        accepted=False,
                        rejection_reason=str(exc),
                        trade_outputs=None,
                        risk_distance=None,
                        reward_distance=None,
                        reward_risk_ratio=None,
                    )
                )
                continue

            trade_outputs = build_trade_outputs(result)
            risk_distance, reward_distance, reward_risk_ratio = calculate_risk_reward_metrics(
                trade_outputs
            )
            variants.append(
                ParameterSweepVariantResult(
                    variant_id=variant_id,
                    parameters=parameters,
                    success=True,
                    error=None,
                    result=result,
                    metrics=build_backtest_metrics([result]),
                    accepted=result.accepted,
                    rejection_reason=None if result.accepted else result.reason,
                    trade_outputs=trade_outputs,
                    risk_distance=risk_distance,
                    reward_distance=reward_distance,
                    reward_risk_ratio=reward_risk_ratio,
                )
            )

        successful_results = [variant for variant in variants if variant.success and variant.result]
        accepted_trades = sum(1 for variant in successful_results if variant.result and variant.result.accepted)
        rejected_trades = sum(1 for variant in successful_results if variant.result and not variant.result.accepted)

        summary = ParameterSweepSummary(
            total_variants=len(variants),
            successful_variants=sum(1 for variant in variants if variant.success),
            failed_variants=sum(1 for variant in variants if not variant.success),
            accepted_trades=accepted_trades,
            rejected_trades=rejected_trades,
        )
        ranking = build_parameter_sweep_ranking(variants)
        return ParameterSweepReport(
            experiment_path=experiment_file.resolve(),
            base_strategy=base_strategy_path,
            variants=variants,
            summary=summary,
            ranking=ranking,
        )
