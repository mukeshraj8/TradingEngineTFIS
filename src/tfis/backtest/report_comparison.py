from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import time
from typing import Any


DEFAULT_MAX_FILE_BYTES = 5_000_000
DEFAULT_MAX_TRADES = 10_000
DEFAULT_TIMEOUT_SECONDS = 10.0

ENTRY_SL_TARGET_FIELDS = {
    "entry_price",
    "stoploss_price",
    "target_price",
}
PNL_FIELDS = {
    "exit_price",
    "net_pnl_points",
    "net_pnl_rupees",
}
BRANCH_ROW_FIELDS = {
    "source_branch_unique_code",
    "option_type",
    "workbook_row_number",
    "source_rule",
}
CONTRACT_LIFECYCLE_FIELDS = {
    "selected_contract_symbol",
    "lifecycle_price_source",
    "contract_specific_intraday_found",
    "contract_specific_bars_available_count",
    "contract_specific_bars_usable_count",
    "contract_specific_fallback_used",
    "contract_specific_fallback_reason",
    "lifecycle_bars_used_count",
}
REPORT_MODE_ORDER = {
    "base": 0,
    "monthly_status": 1,
    "recalculation": 2,
    "current_day_fsl_trp": 3,
    "option_chain": 4,
    "contract_specific_lifecycle": 5,
}


class BacktestReportComparisonError(RuntimeError):
    """Raised when comparison input is invalid or cannot be processed safely."""


@dataclass(frozen=True, slots=True)
class ComparisonLimits:
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    max_trades: int = DEFAULT_MAX_TRADES
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class PerformanceSummary:
    file_size_bytes: int
    parse_elapsed_ms: int
    normalization_elapsed_ms: int
    extracted_trade_count: int
    truncated_trade_count: int


@dataclass(frozen=True, slots=True)
class InputDatasetSummary:
    name: str
    path: str | None
    provided: bool
    used: bool
    fallback_behavior: str | None
    project_fixture: bool
    synthetic_fixture: bool


@dataclass(frozen=True, slots=True)
class NormalizedTradeSummary:
    trade_key: str
    timestamp: str
    trade_date: str
    strategy_code: str | None
    symbol: str | None
    option_type: str | None
    source_branch_unique_code: str | None
    workbook_row_number: int | None
    source_rule: str | None
    selected_contract_symbol: str | None
    lifecycle_price_source: str | None
    contract_specific_intraday_found: bool
    contract_specific_bars_available_count: int | None
    contract_specific_bars_usable_count: int | None
    contract_specific_fallback_used: bool
    contract_specific_fallback_reason: str | None
    lifecycle_bars_used_count: int | None
    monthly_status: str | None
    monthly_status_trigger: str | None
    accepted: bool
    rejection_reason: str
    start_strike: float | None
    end_strike: float | None
    ideal_premium: float | None
    minimum_premium: float | None
    entry_price: float | None
    stoploss_price: float | None
    target_price: float | None
    exit_price: float | None
    net_pnl_points: float | None
    net_pnl_rupees: float | None
    recalculation_applied: bool
    current_day_fsl_trp_applied: bool
    option_chain_selected: bool
    expiry_day_exit_pending: bool
    warning_flags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BacktestModeSummary:
    label: str
    path: str
    mode: str
    strategy_path: str | None
    strategy_root: str | None
    shared_data_root: str | None
    eod_policy: str | None
    cost_model: tuple[tuple[str, float], ...]
    input_datasets: tuple[InputDatasetSummary, ...]
    project_fixture_data_used: bool
    synthetic_fixture_data_used: bool
    use_monthly_status_engine: bool
    enable_s23_recalculation: bool
    enable_s23_current_day_fsl_trp: bool
    enable_option_chain_selection: bool
    enable_contract_specific_lifecycle: bool
    total_evaluations: int
    accepted_candidates: int
    rejected_candidates: int
    entered_trades: int
    target_hits: int
    stoploss_hits: int
    eod_square_off: int
    no_entry: int
    no_exit: int
    total_net_pnl_points: float | None
    total_net_pnl_rupees: float | None
    average_net_pnl_rupees: float | None
    max_drawdown_rupees: float | None
    win_rate: float | None
    loss_rate: float | None
    monthly_status_skip_count: int
    recalculation_applied_count: int
    option_chain_selected_count: int
    contract_specific_series_count: int
    contract_specific_fallback_count: int
    contract_specific_intraday_found_count: int
    contract_specific_missing_symbol_count: int
    contract_specific_pre_cutoff_only_count: int
    contract_specific_coverage_pct: float | None
    contract_specific_fallback_pct: float | None
    expiry_day_candidates: int
    expiry_day_exit_satisfied: int
    expiry_day_exit_pending: int
    rejection_reason_distribution: tuple[tuple[str, int], ...]
    monthly_status_skip_reason_distribution: tuple[tuple[str, int], ...]
    warnings: tuple[str, ...]
    performance: PerformanceSummary
    normalized_trades: tuple[NormalizedTradeSummary, ...]


@dataclass(frozen=True, slots=True)
class ModeTradeDiff:
    trade_key: str
    timestamp: str
    source_branch_unique_code: str | None
    field_differences: dict[str, dict[str, Any]]


@dataclass(frozen=True, slots=True)
class BacktestModeDiff:
    label: str
    baseline_label: str
    added_trades: tuple[dict[str, Any], ...]
    removed_trades: tuple[dict[str, Any], ...]
    changed_trades: tuple[ModeTradeDiff, ...]
    entry_stoploss_target_diff_count: int
    pnl_diff_count: int
    branch_or_row_diff_count: int


@dataclass(frozen=True, slots=True)
class ComparisonRuntimeSummary:
    elapsed_ms: int
    report_count: int
    max_file_bytes: int
    max_trades: int
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class BacktestModeComparison:
    baseline_label: str
    reports: tuple[BacktestModeSummary, ...]
    comparisons: tuple[BacktestModeDiff, ...]
    best_total_net_pnl_rupees_label: str | None
    best_win_rate_label: str | None
    lowest_max_drawdown_label: str | None
    apples_to_apples: bool
    apples_to_apples_issues: tuple[str, ...]
    notes: tuple[str, ...]
    warnings: tuple[str, ...]
    runtime: ComparisonRuntimeSummary


@dataclass(slots=True)
class _Deadline:
    timeout_seconds: float
    started_at: float

    @classmethod
    def start(cls, timeout_seconds: float) -> _Deadline:
        return cls(timeout_seconds=timeout_seconds, started_at=time.monotonic())

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started_at) * 1000)

    def checkpoint(self, phase: str) -> None:
        if self.timeout_seconds <= 0:
            return
        if (time.monotonic() - self.started_at) > self.timeout_seconds:
            raise BacktestReportComparisonError(
                f"Comparison timed out after {self.timeout_seconds:.2f}s during {phase}."
            )


def load_backtest_report(
    path: str | Path,
    *,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> dict[str, Any]:
    report_path = Path(path)
    if not report_path.is_file():
        raise BacktestReportComparisonError(
            f"Backtest report not found: {report_path}"
        )
    file_size = report_path.stat().st_size
    if file_size > max_file_bytes:
        raise BacktestReportComparisonError(
            f"Backtest report '{report_path}' is {file_size} bytes, above the limit of "
            f"{max_file_bytes} bytes."
        )
    try:
        return json.loads(report_path.read_bytes())
    except json.JSONDecodeError as exc:
        raise BacktestReportComparisonError(
            f"Backtest report '{report_path}' is not valid JSON: {exc.msg} "
            f"(line {exc.lineno}, column {exc.colno})."
        ) from exc


def summarize_backtest_report(
    *,
    label: str,
    path: str | Path,
    report: dict[str, Any],
    limits: ComparisonLimits | None = None,
    deadline: _Deadline | None = None,
    parse_elapsed_ms: int = 0,
    file_size_bytes: int = 0,
) -> BacktestModeSummary:
    active_limits = limits or ComparisonLimits()
    active_deadline = deadline or _Deadline.start(active_limits.timeout_seconds)
    active_deadline.checkpoint(f"normalizing {label}")

    if not isinstance(report, dict):
        raise BacktestReportComparisonError(
            f"Backtest report '{path}' must be a JSON object."
        )

    metrics = report.get("metrics", {})
    if metrics is None:
        metrics = {}
    if not isinstance(metrics, dict):
        raise BacktestReportComparisonError(
            f"Backtest report '{path}' has a non-object 'metrics' payload."
        )

    evaluations = report.get("evaluations", [])
    if evaluations is None:
        evaluations = []
    if not isinstance(evaluations, list):
        raise BacktestReportComparisonError(
            f"Backtest report '{path}' has a non-list 'evaluations' payload."
        )

    monthly_status_skips = report.get("monthly_status_skips", [])
    if monthly_status_skips is None:
        monthly_status_skips = []
    if not isinstance(monthly_status_skips, list):
        raise BacktestReportComparisonError(
            f"Backtest report '{path}' has a non-list 'monthly_status_skips' payload."
        )

    cost_model = _normalize_cost_model(report.get("cost_model"))
    input_datasets, project_fixture_data_used, synthetic_fixture_data_used = (
        _normalize_input_datasets(report.get("input_metadata"))
    )

    warnings: list[str] = []
    normalization_started = time.monotonic()
    normalized_trades = _extract_normalized_trades(
        label=label,
        report=report,
        evaluations=evaluations,
        max_trades=active_limits.max_trades,
        warnings=warnings,
        deadline=active_deadline,
    )
    warnings.extend(_collect_report_level_warnings(evaluations))
    normalization_elapsed_ms = int((time.monotonic() - normalization_started) * 1000)

    recalculation_applied_count = 0
    option_chain_selected_count = 0
    contract_specific_series_count = 0
    contract_specific_fallback_count = 0
    contract_specific_intraday_found_count = 0
    contract_specific_missing_symbol_count = 0
    contract_specific_pre_cutoff_only_count = 0
    for trade in normalized_trades:
        if trade.recalculation_applied:
            recalculation_applied_count += 1
        if trade.option_chain_selected:
            option_chain_selected_count += 1
        if trade.lifecycle_price_source == "contract_specific_series":
            contract_specific_series_count += 1
        elif trade.lifecycle_price_source == "generic_option_series":
            contract_specific_fallback_count += 1
        if trade.contract_specific_intraday_found:
            contract_specific_intraday_found_count += 1
        if trade.contract_specific_fallback_reason == "missing_contract_intraday_for_selected_symbol":
            contract_specific_missing_symbol_count += 1
        elif trade.contract_specific_fallback_reason == "no_contract_intraday_after_lifecycle_cutoff":
            contract_specific_pre_cutoff_only_count += 1

    contract_specific_coverage_pct = _safe_percentage(
        contract_specific_intraday_found_count,
        option_chain_selected_count,
    )
    contract_specific_fallback_pct = _safe_percentage(
        contract_specific_fallback_count,
        option_chain_selected_count,
    )

    total_evaluations = _int_or_default(
        metrics.get("total_evaluations"),
        len(evaluations),
    )
    accepted_candidates = _int_or_default(
        metrics.get("accepted_candidates"),
        sum(1 for trade in normalized_trades if trade.accepted),
    )
    rejected_candidates = _int_or_default(
        metrics.get("rejected_candidates"),
        sum(1 for trade in normalized_trades if not trade.accepted),
    )

    if total_evaluations > len(normalized_trades) and active_limits.max_trades < total_evaluations:
        warnings.append(
            f"Normalized only the first {len(normalized_trades)} of {total_evaluations} evaluations "
            f"because max_trades={active_limits.max_trades}."
        )

    return BacktestModeSummary(
        label=label,
        path=str(Path(path)),
        mode=str(report.get("mode", "unknown")),
        strategy_path=_str_or_none(report.get("strategy_path")),
        strategy_root=_str_or_none(report.get("strategy_root")),
        shared_data_root=_str_or_none(report.get("shared_data_root")),
        eod_policy=_str_or_none(report.get("eod_policy")),
        cost_model=cost_model,
        input_datasets=input_datasets,
        project_fixture_data_used=project_fixture_data_used,
        synthetic_fixture_data_used=synthetic_fixture_data_used,
        use_monthly_status_engine=bool(report.get("use_monthly_status_engine", False)),
        enable_s23_recalculation=bool(report.get("enable_s23_recalculation", False)),
        enable_s23_current_day_fsl_trp=bool(report.get("enable_s23_current_day_fsl_trp", False)),
        enable_option_chain_selection=bool(report.get("enable_option_chain_selection", False)),
        enable_contract_specific_lifecycle=bool(
            report.get("enable_contract_specific_lifecycle", False)
        ),
        total_evaluations=total_evaluations,
        accepted_candidates=accepted_candidates,
        rejected_candidates=rejected_candidates,
        entered_trades=_int_or_default(metrics.get("entered_trades"), 0),
        target_hits=_int_or_default(metrics.get("target_hits"), 0),
        stoploss_hits=_int_or_default(metrics.get("stoploss_hits"), 0),
        eod_square_off=_int_or_default(metrics.get("eod_square_off"), 0),
        no_entry=_int_or_default(metrics.get("no_entry"), 0),
        no_exit=_int_or_default(metrics.get("no_exit"), 0),
        total_net_pnl_points=_float_or_none(metrics.get("total_net_pnl_points")),
        total_net_pnl_rupees=_float_or_none(metrics.get("total_net_pnl_rupees")),
        average_net_pnl_rupees=_float_or_none(metrics.get("average_net_pnl_rupees")),
        max_drawdown_rupees=_float_or_none(metrics.get("max_drawdown_rupees")),
        win_rate=_float_or_none(metrics.get("win_rate")),
        loss_rate=_float_or_none(metrics.get("loss_rate")),
        monthly_status_skip_count=len(monthly_status_skips),
        recalculation_applied_count=recalculation_applied_count,
        option_chain_selected_count=option_chain_selected_count,
        contract_specific_series_count=contract_specific_series_count,
        contract_specific_fallback_count=contract_specific_fallback_count,
        contract_specific_intraday_found_count=contract_specific_intraday_found_count,
        contract_specific_missing_symbol_count=contract_specific_missing_symbol_count,
        contract_specific_pre_cutoff_only_count=contract_specific_pre_cutoff_only_count,
        contract_specific_coverage_pct=contract_specific_coverage_pct,
        contract_specific_fallback_pct=contract_specific_fallback_pct,
        expiry_day_candidates=_int_or_default(metrics.get("expiry_day_candidates"), 0),
        expiry_day_exit_satisfied=_int_or_default(
            metrics.get("expiry_day_exit_satisfied"),
            0,
        ),
        expiry_day_exit_pending=_int_or_default(
            metrics.get("expiry_day_exit_pending"),
            0,
        ),
        rejection_reason_distribution=_sorted_distribution(
            _coerce_count_map(metrics.get("rejection_reason_distribution")),
        ),
        monthly_status_skip_reason_distribution=_sorted_distribution(
            _build_skip_reason_distribution(monthly_status_skips)
        ),
        warnings=tuple(sorted(set(warnings))),
        performance=PerformanceSummary(
            file_size_bytes=file_size_bytes,
            parse_elapsed_ms=parse_elapsed_ms,
            normalization_elapsed_ms=normalization_elapsed_ms,
            extracted_trade_count=len(normalized_trades),
            truncated_trade_count=max(0, total_evaluations - len(normalized_trades)),
        ),
        normalized_trades=tuple(sorted(normalized_trades, key=lambda item: item.trade_key)),
    )


def load_and_summarize_backtest_report(
    *,
    label: str,
    path: str | Path,
    limits: ComparisonLimits | None = None,
    deadline: _Deadline | None = None,
) -> BacktestModeSummary:
    active_limits = limits or ComparisonLimits()
    active_deadline = deadline or _Deadline.start(active_limits.timeout_seconds)
    active_deadline.checkpoint(f"loading {label}")

    report_path = Path(path)
    if not report_path.is_file():
        raise BacktestReportComparisonError(
            f"Backtest report not found: {report_path}"
        )

    file_size_bytes = report_path.stat().st_size
    if file_size_bytes > active_limits.max_file_bytes:
        raise BacktestReportComparisonError(
            f"Backtest report '{report_path}' is {file_size_bytes} bytes, above the limit of "
            f"{active_limits.max_file_bytes} bytes."
        )

    parse_started = time.monotonic()
    report = load_backtest_report(report_path, max_file_bytes=active_limits.max_file_bytes)
    parse_elapsed_ms = int((time.monotonic() - parse_started) * 1000)
    active_deadline.checkpoint(f"loaded {label}")

    return summarize_backtest_report(
        label=label,
        path=report_path,
        report=report,
        limits=active_limits,
        deadline=active_deadline,
        parse_elapsed_ms=parse_elapsed_ms,
        file_size_bytes=file_size_bytes,
    )


def compare_backtest_reports(
    labeled_reports: list[tuple[str, str | Path, dict[str, Any]]],
    *,
    limits: ComparisonLimits | None = None,
) -> BacktestModeComparison:
    if not labeled_reports:
        raise BacktestReportComparisonError("At least one backtest report is required.")

    active_limits = limits or ComparisonLimits()
    deadline = _Deadline.start(active_limits.timeout_seconds)
    summaries = tuple(
        summarize_backtest_report(
            label=label,
            path=path,
            report=report,
            limits=active_limits,
            deadline=deadline,
        )
        for label, path, report in labeled_reports
    )
    deadline.checkpoint("building comparison")
    return _build_comparison(summaries, limits=active_limits, deadline=deadline)


def load_and_compare_backtest_reports(
    report_inputs: list[tuple[str, str | Path]],
    *,
    limits: ComparisonLimits | None = None,
) -> BacktestModeComparison:
    if not report_inputs:
        raise BacktestReportComparisonError("At least one backtest report is required.")

    active_limits = limits or ComparisonLimits()
    deadline = _Deadline.start(active_limits.timeout_seconds)
    summaries = tuple(
        load_and_summarize_backtest_report(
            label=label,
            path=path,
            limits=active_limits,
            deadline=deadline,
        )
        for label, path in report_inputs
    )
    deadline.checkpoint("building comparison")
    return _build_comparison(summaries, limits=active_limits, deadline=deadline)


def comparison_to_dict(comparison: BacktestModeComparison) -> dict[str, Any]:
    return {
        "baseline_label": comparison.baseline_label,
        "reports": [asdict(report) for report in comparison.reports],
        "comparisons": [
            {
                "label": item.label,
                "baseline_label": item.baseline_label,
                "added_trades": list(item.added_trades),
                "removed_trades": list(item.removed_trades),
                "changed_trades": [
                    {
                        "trade_key": diff.trade_key,
                        "timestamp": diff.timestamp,
                        "source_branch_unique_code": diff.source_branch_unique_code,
                        "field_differences": diff.field_differences,
                    }
                    for diff in item.changed_trades
                ],
                "entry_stoploss_target_diff_count": item.entry_stoploss_target_diff_count,
                "pnl_diff_count": item.pnl_diff_count,
                "branch_or_row_diff_count": item.branch_or_row_diff_count,
            }
            for item in comparison.comparisons
        ],
        "best_total_net_pnl_rupees_label": comparison.best_total_net_pnl_rupees_label,
        "best_win_rate_label": comparison.best_win_rate_label,
        "lowest_max_drawdown_label": comparison.lowest_max_drawdown_label,
        "apples_to_apples": comparison.apples_to_apples,
        "apples_to_apples_issues": list(comparison.apples_to_apples_issues),
        "notes": list(comparison.notes),
        "warnings": list(comparison.warnings),
        "runtime": asdict(comparison.runtime),
    }


def render_comparison_markdown(comparison: BacktestModeComparison) -> str:
    lines = [
        "# S23 Backtest Mode Comparison",
        "",
        "This report compares existing TFIS S23 historical outputs. It is read-only and does not rerun strategy logic.",
        "",
        "## Compared Files And Modes",
        "",
        "| Label | File | Mode | Monthly Status | ORPT Recalc | Current-Day FSL/TRP | Chain | Contract Lifecycle |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for report in comparison.reports:
        lines.append(
            "| "
            f"{report.label} | "
            f"`{Path(report.path).name}` | "
            f"{report.mode} | "
            f"{_yes_no(report.use_monthly_status_engine)} | "
            f"{_yes_no(report.enable_s23_recalculation)} | "
            f"{_yes_no(report.enable_s23_current_day_fsl_trp)} | "
            f"{_yes_no(report.enable_option_chain_selection)} | "
            f"{_yes_no(report.enable_contract_specific_lifecycle)} |"
        )

    lines.extend(
        [
            "",
            "## Input Integrity",
            "",
            f"- apples_to_apples: `{'yes' if comparison.apples_to_apples else 'no'}`",
        ]
    )
    if comparison.apples_to_apples_issues:
        lines.append("")
        lines.append("### Apples-To-Apples Issues")
        lines.append("")
        for issue in comparison.apples_to_apples_issues:
            lines.append(f"- {issue}")
    lines.extend(
        [
            "",
            "| Label | Synthetic Fixture Data | Cost Model | Daily | Option Levels | Spot Intraday | Option Intraday | Monthly | Weekly | Option Chain | Contract Intraday |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for report in comparison.reports:
        dataset_map = {item.name: item for item in report.input_datasets}
        lines.append(
            "| "
            f"{report.label} | "
            f"{_yes_no(report.synthetic_fixture_data_used)} | "
            f"`{_format_cost_model(report.cost_model)}` | "
            f"{_markdown_dataset_cell(dataset_map.get('daily'))} | "
            f"{_markdown_dataset_cell(dataset_map.get('option_levels'))} | "
            f"{_markdown_dataset_cell(dataset_map.get('spot_intraday'))} | "
            f"{_markdown_dataset_cell(dataset_map.get('option_intraday'))} | "
            f"{_markdown_dataset_cell(dataset_map.get('monthly'))} | "
            f"{_markdown_dataset_cell(dataset_map.get('weekly'))} | "
            f"{_markdown_dataset_cell(dataset_map.get('option_chain'))} | "
            f"{_markdown_dataset_cell(dataset_map.get('contract_intraday'))} |"
        )

    lines.extend(
        [
            "",
            "## Total Trades Per Mode",
            "",
            "| Label | Total Evaluations | Extracted Trades | Accepted | Rejected | Entered | Net P&L Rs | Max DD Rs |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for report in comparison.reports:
        lines.append(
            "| "
            f"{report.label} | "
            f"{report.total_evaluations} | "
            f"{report.performance.extracted_trade_count} | "
            f"{report.accepted_candidates} | "
            f"{report.rejected_candidates} | "
            f"{report.entered_trades} | "
            f"{_format_number(report.total_net_pnl_rupees, digits=2)} | "
            f"{_format_number(report.max_drawdown_rupees, digits=2)} |"
        )

    lines.extend(
        [
            "",
            "## Contract-Specific Lifecycle Provenance",
            "",
            "| Label | Selected Contracts | Contract Bars Found | Coverage % | Real Selected-Contract Bars Used | Generic Fallback Used | Fallback % | Missing Symbol Bars | Pre-Cutoff Fallbacks |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for report in comparison.reports:
        lines.append(
            "| "
            f"{report.label} | "
            f"{report.option_chain_selected_count} | "
            f"{report.contract_specific_intraday_found_count} | "
            f"{_format_number(report.contract_specific_coverage_pct, digits=1)}% | "
            f"{report.contract_specific_series_count} | "
            f"{report.contract_specific_fallback_count} | "
            f"{_format_number(report.contract_specific_fallback_pct, digits=1)}% | "
            f"{report.contract_specific_missing_symbol_count} | "
            f"{report.contract_specific_pre_cutoff_only_count} |"
        )

    report_by_label = {report.label: report for report in comparison.reports}
    for diff in comparison.comparisons:
        lines.extend(
            [
                "",
                f"## Differences Vs {diff.baseline_label}: {diff.label}",
                "",
                f"- added trades: `{len(diff.added_trades)}`",
                f"- removed trades: `{len(diff.removed_trades)}`",
                f"- entry/SL/target differences: `{diff.entry_stoploss_target_diff_count}`",
                f"- P&L differences: `{diff.pnl_diff_count}`",
                f"- branch/workbook-row differences: `{diff.branch_or_row_diff_count}`",
            ]
        )

        lines.extend(["", "### Trades Added/Removed", ""])
        if diff.added_trades:
            lines.append("| Added Trade Key | Timestamp | Branch | Option Type | Reason |")
            lines.append("| --- | --- | --- | --- | --- |")
            for item in diff.added_trades:
                lines.append(
                    "| "
                    f"`{item['trade_key']}` | "
                    f"{item['timestamp']} | "
                    f"{item.get('source_branch_unique_code') or '-'} | "
                    f"{item.get('option_type') or '-'} | "
                    f"{item.get('rejection_reason') or '-'} |"
                )
        else:
            lines.append("- No added trades.")

        if diff.removed_trades:
            lines.append("")
            lines.append("| Removed Trade Key | Timestamp | Branch | Option Type | Reason |")
            lines.append("| --- | --- | --- | --- | --- |")
            for item in diff.removed_trades:
                lines.append(
                    "| "
                    f"`{item['trade_key']}` | "
                    f"{item['timestamp']} | "
                    f"{item.get('source_branch_unique_code') or '-'} | "
                    f"{item.get('option_type') or '-'} | "
                    f"{item.get('rejection_reason') or '-'} |"
                )
        else:
            lines.append("- No removed trades.")

        lines.extend(["", "### Entry / SL / Target Differences", ""])
        entry_rows = [
            change
            for change in diff.changed_trades
            if any(field in ENTRY_SL_TARGET_FIELDS for field in change.field_differences)
        ]
        if entry_rows:
            lines.append("| Trade Key | Entry | Stoploss | Target |")
            lines.append("| --- | --- | --- | --- |")
            for change in entry_rows:
                lines.append(
                    "| "
                    f"`{change.trade_key}` | "
                    f"{_markdown_field_delta(change.field_differences.get('entry_price'))} | "
                    f"{_markdown_field_delta(change.field_differences.get('stoploss_price'))} | "
                    f"{_markdown_field_delta(change.field_differences.get('target_price'))} |"
                )
        else:
            lines.append("- No entry/SL/target differences.")

        lines.extend(["", "### P&L Deltas", ""])
        pnl_rows = [
            change
            for change in diff.changed_trades
            if any(field in PNL_FIELDS for field in change.field_differences)
        ]
        if pnl_rows:
            lines.append("| Trade Key | Exit Price | Net P&L Points | Net P&L Rs |")
            lines.append("| --- | --- | --- | --- |")
            for change in pnl_rows:
                lines.append(
                    "| "
                    f"`{change.trade_key}` | "
                    f"{_markdown_field_delta(change.field_differences.get('exit_price'))} | "
                    f"{_markdown_field_delta(change.field_differences.get('net_pnl_points'))} | "
                    f"{_markdown_field_delta(change.field_differences.get('net_pnl_rupees'))} |"
                )
        else:
            lines.append("- No P&L deltas.")

        lines.extend(["", "### Branch / Workbook Row Differences", ""])
        branch_rows = [
            change
            for change in diff.changed_trades
            if any(field in BRANCH_ROW_FIELDS for field in change.field_differences)
        ]
        if branch_rows:
            lines.append("| Trade Key | Branch | Option Type | Workbook Row | Source Rule |")
            lines.append("| --- | --- | --- | --- | --- |")
            for change in branch_rows:
                lines.append(
                    "| "
                    f"`{change.trade_key}` | "
                    f"{_markdown_field_delta(change.field_differences.get('source_branch_unique_code'))} | "
                    f"{_markdown_field_delta(change.field_differences.get('option_type'))} | "
                    f"{_markdown_field_delta(change.field_differences.get('workbook_row_number'))} | "
                    f"{_markdown_field_delta(change.field_differences.get('source_rule'))} |"
                )
        else:
            lines.append("- No branch or workbook-row differences.")

        candidate_report = report_by_label.get(diff.label)
        if candidate_report is not None and candidate_report.enable_contract_specific_lifecycle:
            diff_by_trade_key = {
                change.trade_key: change for change in diff.changed_trades
            }
            contract_series_trades = [
                trade
                for trade in candidate_report.normalized_trades
                if trade.lifecycle_price_source == "contract_specific_series"
            ]
            fallback_trades = [
                trade
                for trade in candidate_report.normalized_trades
                if trade.contract_specific_fallback_used
            ]
            lines.extend(["", "### Contract-Specific Lifecycle Details", ""])
            if contract_series_trades:
                lines.append("| Trade Key | Selected Contract | Bars Available | Usable Bars | Bars Used | Net P&L Rs | Vs Baseline P&L |")
                lines.append("| --- | --- | ---: | ---: | ---: | ---: | --- |")
                for trade in contract_series_trades:
                    diff_entry = diff_by_trade_key.get(trade.trade_key)
                    pnl_delta = (
                        diff_entry.field_differences.get("net_pnl_rupees")
                        if diff_entry is not None
                        else None
                    )
                    lines.append(
                        "| "
                        f"`{trade.trade_key}` | "
                        f"{trade.selected_contract_symbol or '-'} | "
                        f"{_format_number(trade.contract_specific_bars_available_count, digits=0)} | "
                        f"{_format_number(trade.contract_specific_bars_usable_count, digits=0)} | "
                        f"{_format_number(trade.lifecycle_bars_used_count, digits=0)} | "
                        f"{_format_number(trade.net_pnl_rupees, digits=2)} | "
                        f"{_markdown_field_delta(pnl_delta)} |"
                    )
            else:
                lines.append("- No trades used real selected-contract bars.")

            if fallback_trades:
                lines.append("")
                lines.append("| Trade Key | Selected Contract | Bars Available | Usable Bars | Fallback Reason |")
                lines.append("| --- | --- | ---: | ---: | --- |")
                for trade in fallback_trades:
                    lines.append(
                        "| "
                        f"`{trade.trade_key}` | "
                        f"{trade.selected_contract_symbol or '-'} | "
                        f"{_format_number(trade.contract_specific_bars_available_count, digits=0)} | "
                        f"{_format_number(trade.contract_specific_bars_usable_count, digits=0)} | "
                        f"{trade.contract_specific_fallback_reason or '-'} |"
                    )
            else:
                lines.append("- No generic fallback trades.")

    lines.extend(["", "## Rejection And Skip Summary", ""])
    for report in comparison.reports:
        lines.append("")
        lines.append(f"### {report.label}")
        if report.rejection_reason_distribution:
            lines.append("- rejection reasons:")
            for reason, count in report.rejection_reason_distribution:
                lines.append(f"  - `{reason}`: `{count}`")
        else:
            lines.append("- rejection reasons: none")
        if report.monthly_status_skip_reason_distribution:
            lines.append("- monthly-status skips:")
            for reason, count in report.monthly_status_skip_reason_distribution:
                lines.append(f"  - `{reason}`: `{count}`")
        else:
            lines.append("- monthly-status skips: none")

    lines.extend(["", "## Warnings", ""])
    if comparison.warnings:
        for warning in comparison.warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Runtime And Performance Summary",
            "",
            f"- baseline label: `{comparison.baseline_label}`",
            f"- report count: `{comparison.runtime.report_count}`",
            f"- elapsed_ms: `{comparison.runtime.elapsed_ms}`",
            f"- max_file_bytes: `{comparison.runtime.max_file_bytes}`",
            f"- max_trades: `{comparison.runtime.max_trades}`",
            f"- timeout_seconds: `{comparison.runtime.timeout_seconds}`",
            "",
            "| Label | File Bytes | Parse ms | Normalize ms | Extracted Trades | Truncated Trades |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for report in comparison.reports:
        lines.append(
            "| "
            f"{report.label} | "
            f"{report.performance.file_size_bytes} | "
            f"{report.performance.parse_elapsed_ms} | "
            f"{report.performance.normalization_elapsed_ms} | "
            f"{report.performance.extracted_trade_count} | "
            f"{report.performance.truncated_trade_count} |"
        )

    return "\n".join(lines) + "\n"


def _build_comparison(
    reports: tuple[BacktestModeSummary, ...],
    *,
    limits: ComparisonLimits,
    deadline: _Deadline,
) -> BacktestModeComparison:
    ordered_reports = tuple(_sort_reports(reports))
    baseline = ordered_reports[0]
    comparisons = tuple(
        _compare_mode_summaries(baseline, candidate)
        for candidate in ordered_reports[1:]
    )

    notes: list[str] = []
    warnings: list[str] = []
    if any(report.mode != "historical" for report in ordered_reports):
        notes.append(
            "One or more inputs are not historical reports; some metrics may not be directly comparable."
        )
    if any(report.total_evaluations != baseline.total_evaluations for report in ordered_reports[1:]):
        notes.append("Reports have different evaluation counts; compare totals with care.")

    for report in ordered_reports:
        warnings.extend(report.warnings)
        if report.monthly_status_skip_count:
            notes.append(
                f"{report.label} has {report.monthly_status_skip_count} monthly-status skips."
            )

    apples_to_apples_issues = _find_apples_to_apples_issues(ordered_reports)
    if apples_to_apples_issues:
        warnings.extend(apples_to_apples_issues)
    else:
        notes.append(
            "Reports are apples-to-apples for recorded input datasets and cost settings."
        )

    return BacktestModeComparison(
        baseline_label=baseline.label,
        reports=ordered_reports,
        comparisons=comparisons,
        best_total_net_pnl_rupees_label=_best_label(
            list(ordered_reports),
            key=lambda item: item.total_net_pnl_rupees,
            prefer_high=True,
        ),
        best_win_rate_label=_best_label(
            list(ordered_reports),
            key=lambda item: item.win_rate,
            prefer_high=True,
        ),
        lowest_max_drawdown_label=_best_label(
            list(ordered_reports),
            key=lambda item: item.max_drawdown_rupees,
            prefer_high=False,
        ),
        apples_to_apples=not apples_to_apples_issues,
        apples_to_apples_issues=tuple(apples_to_apples_issues),
        notes=tuple(dict.fromkeys(notes)),
        warnings=tuple(sorted(set(warnings))),
        runtime=ComparisonRuntimeSummary(
            elapsed_ms=deadline.elapsed_ms(),
            report_count=len(ordered_reports),
            max_file_bytes=limits.max_file_bytes,
            max_trades=limits.max_trades,
            timeout_seconds=limits.timeout_seconds,
        ),
    )


def _sort_reports(reports: tuple[BacktestModeSummary, ...]) -> list[BacktestModeSummary]:
    def sort_key(item: BacktestModeSummary) -> tuple[int, str]:
        normalized = item.label.strip().lower().replace("-", "_").replace(" ", "_")
        return (REPORT_MODE_ORDER.get(normalized, 100), normalized)

    return sorted(reports, key=sort_key)


def _find_apples_to_apples_issues(
    reports: tuple[BacktestModeSummary, ...],
) -> list[str]:
    if not reports:
        return []
    baseline = reports[0]
    issues: list[str] = []
    baseline_costs = dict(baseline.cost_model)
    baseline_datasets = {item.name: item for item in baseline.input_datasets}

    for report in reports[1:]:
        if dict(report.cost_model) != baseline_costs:
            issues.append(
                f"Cost model mismatch: {report.label} differs from baseline {baseline.label}."
            )

        report_datasets = {item.name: item for item in report.input_datasets}
        for dataset_name in sorted(set(baseline_datasets) | set(report_datasets)):
            baseline_dataset = baseline_datasets.get(dataset_name)
            report_dataset = report_datasets.get(dataset_name)
            if baseline_dataset is None or report_dataset is None:
                issues.append(
                    f"Dataset metadata mismatch: {dataset_name} is missing from "
                    f"{baseline.label if report_dataset is not None else report.label}."
                )
                continue
            if baseline_dataset.path != report_dataset.path:
                issues.append(
                    f"Dataset path mismatch for {dataset_name}: "
                    f"{baseline.label}={baseline_dataset.path or '-'} vs "
                    f"{report.label}={report_dataset.path or '-'}."
                )
            if baseline_dataset.fallback_behavior != report_dataset.fallback_behavior:
                issues.append(
                    f"Fallback mismatch for {dataset_name}: "
                    f"{baseline.label}={baseline_dataset.fallback_behavior or '-'} vs "
                    f"{report.label}={report_dataset.fallback_behavior or '-'}."
                )
            if baseline_dataset.synthetic_fixture != report_dataset.synthetic_fixture:
                issues.append(
                    f"Synthetic-fixture mismatch for {dataset_name}: "
                    f"{baseline.label}={baseline_dataset.synthetic_fixture} vs "
                    f"{report.label}={report_dataset.synthetic_fixture}."
                )
    return issues


def _compare_mode_summaries(
    baseline: BacktestModeSummary,
    candidate: BacktestModeSummary,
) -> BacktestModeDiff:
    baseline_trades = {trade.trade_key: trade for trade in baseline.normalized_trades}
    candidate_trades = {trade.trade_key: trade for trade in candidate.normalized_trades}
    baseline_keys = set(baseline_trades)
    candidate_keys = set(candidate_trades)

    added_keys = sorted(candidate_keys - baseline_keys)
    removed_keys = sorted(baseline_keys - candidate_keys)
    shared_keys = sorted(baseline_keys & candidate_keys)

    changed: list[ModeTradeDiff] = []
    entry_stoploss_target_diff_count = 0
    pnl_diff_count = 0
    branch_or_row_diff_count = 0
    for trade_key in shared_keys:
        baseline_trade = baseline_trades[trade_key]
        candidate_trade = candidate_trades[trade_key]
        field_differences = _diff_trade_fields(baseline_trade, candidate_trade)
        if not field_differences:
            continue
        if any(field in ENTRY_SL_TARGET_FIELDS for field in field_differences):
            entry_stoploss_target_diff_count += 1
        if any(field in PNL_FIELDS for field in field_differences):
            pnl_diff_count += 1
        if any(field in BRANCH_ROW_FIELDS for field in field_differences):
            branch_or_row_diff_count += 1
        changed.append(
            ModeTradeDiff(
                trade_key=trade_key,
                timestamp=candidate_trade.timestamp,
                source_branch_unique_code=candidate_trade.source_branch_unique_code,
                field_differences=field_differences,
            )
        )

    return BacktestModeDiff(
        label=candidate.label,
        baseline_label=baseline.label,
        added_trades=tuple(
            _trade_snapshot_dict(candidate_trades[trade_key]) for trade_key in added_keys
        ),
        removed_trades=tuple(
            _trade_snapshot_dict(baseline_trades[trade_key]) for trade_key in removed_keys
        ),
        changed_trades=tuple(changed),
        entry_stoploss_target_diff_count=entry_stoploss_target_diff_count,
        pnl_diff_count=pnl_diff_count,
        branch_or_row_diff_count=branch_or_row_diff_count,
    )


def _extract_normalized_trades(
    *,
    label: str,
    report: dict[str, Any],
    evaluations: list[Any],
    max_trades: int,
    warnings: list[str],
    deadline: _Deadline,
) -> list[NormalizedTradeSummary]:
    normalized: list[NormalizedTradeSummary] = []
    timestamp_positions: dict[str, int] = {}
    for index, evaluation in enumerate(evaluations):
        if index >= max_trades:
            break
        if index and index % 100 == 0:
            deadline.checkpoint(f"normalizing trade summaries for {label}")
        if not isinstance(evaluation, dict):
            raise BacktestReportComparisonError(
                f"Backtest report '{label}' contains a non-object evaluation at index {index}."
            )
        timestamp = str(evaluation.get("timestamp", ""))
        timestamp_position = timestamp_positions.get(timestamp, 0)
        timestamp_positions[timestamp] = timestamp_position + 1
        normalized.append(
            _normalize_trade_summary(
                report=report,
                evaluation=evaluation,
                timestamp_position=timestamp_position,
                warnings=warnings,
            )
        )
    return normalized


def _normalize_trade_summary(
    *,
    report: dict[str, Any],
    evaluation: dict[str, Any],
    timestamp_position: int,
    warnings: list[str],
) -> NormalizedTradeSummary:
    validation = evaluation.get("validation", {})
    validation = validation if isinstance(validation, dict) else {}
    trade_outputs = evaluation.get("trade_outputs", {})
    trade_outputs = trade_outputs if isinstance(trade_outputs, dict) else {}
    lifecycle_result = evaluation.get("lifecycle_result", {})
    lifecycle_result = lifecycle_result if isinstance(lifecycle_result, dict) else {}

    current_day = validation.get("s23_current_day_fsl_trp")
    current_day = current_day if isinstance(current_day, dict) else {}
    current_day_result = current_day.get("result")
    current_day_result = current_day_result if isinstance(current_day_result, dict) else {}
    recalculation = validation.get("s23_recalculation")
    recalculation = recalculation if isinstance(recalculation, dict) else {}
    option_chain = validation.get("option_chain_selection")
    option_chain = option_chain if isinstance(option_chain, dict) else {}
    selected_contract = option_chain.get("selected_contract")
    selected_contract = selected_contract if isinstance(selected_contract, dict) else {}
    contract_specific = validation.get("contract_specific_lifecycle")
    contract_specific = contract_specific if isinstance(contract_specific, dict) else {}
    expiry_day_review = validation.get("expiry_day_review")
    expiry_day_review = expiry_day_review if isinstance(expiry_day_review, dict) else {}
    recalculation_result = recalculation.get("recalculation_result")
    recalculation_result = (
        recalculation_result if isinstance(recalculation_result, dict) else {}
    )

    timestamp = str(evaluation.get("timestamp", ""))
    trade_date = timestamp.split("T", 1)[0] if "T" in timestamp else timestamp
    source_branch = _resolve_source_branch_unique_code(
        report=report,
        evaluation=evaluation,
        timestamp_position=timestamp_position,
        option_type=None,
    )
    option_type = _resolve_option_type(
        report=report,
        evaluation=evaluation,
        recalculation=recalculation,
        current_day=current_day,
        selected_contract=selected_contract,
        trade_outputs=trade_outputs,
        source_branch=source_branch,
        warnings=warnings,
    )
    if source_branch is None:
        source_branch = _resolve_source_branch_unique_code(
            report=report,
            evaluation=evaluation,
            timestamp_position=timestamp_position,
            option_type=option_type,
        )
    elif option_type is None:
        option_type = _branch_option_type(source_branch)

    if source_branch is None:
        source_branch = _resolve_source_branch_unique_code(
            report=report,
            evaluation=evaluation,
            timestamp_position=timestamp_position,
            option_type=option_type,
        )
    if option_type is None and source_branch is not None:
        option_type = _branch_option_type(source_branch)

    if option_type is None:
        option_type = _resolve_option_type(
            report=report,
            evaluation=evaluation,
            recalculation=recalculation,
            current_day=current_day,
            selected_contract=selected_contract,
            trade_outputs=trade_outputs,
            source_branch=source_branch,
            warnings=warnings,
        )
    selected_contract_symbol = _str_or_none(selected_contract.get("symbol"))
    lifecycle_price_source = _str_or_none(contract_specific.get("lifecycle_price_source"))
    contract_specific_intraday_found = bool(
        contract_specific.get("contract_specific_intraday_found", False)
    )
    contract_specific_bars_available_count = _int_or_none(
        contract_specific.get("contract_specific_bars_available_count")
    )
    contract_specific_bars_usable_count = _int_or_none(
        contract_specific.get("contract_specific_bars_usable_count")
    )
    contract_specific_fallback_used = bool(
        contract_specific.get("generic_fallback_used", False)
    )
    contract_specific_fallback_reason = _str_or_none(
        contract_specific.get("fallback_reason")
    )
    lifecycle_bars_used_count = _int_or_none(
        contract_specific.get("lifecycle_bars_used_count")
    )
    warning_flags = set()
    if contract_specific.get("warning"):
        warning_flags.add("contract_specific_fallback_warning")
    if contract_specific_fallback_used:
        warning_flags.add("contract_specific_generic_fallback")
    if not source_branch:
        warning_flags.add("missing_source_branch")
        warnings.append(
            f"Could not determine source branch for evaluation at {timestamp}; trade key uses fallback identity."
        )
    if not option_type:
        warning_flags.add("missing_option_type")
        warnings.append(
            f"Could not determine option type for evaluation at {timestamp}; trade key uses fallback identity."
        )

    trade_key = "|".join(
        [
            timestamp or "unknown_timestamp",
            source_branch or "unknown_branch",
            option_type or "UNKNOWN",
        ]
    )

    return NormalizedTradeSummary(
        trade_key=trade_key,
        timestamp=timestamp,
        trade_date=trade_date,
        strategy_code=_str_or_none(evaluation.get("strategy_code")),
        symbol=(
            _extract_plan_value(current_day, "effective_trade_plan", "symbol")
            or _extract_plan_value(current_day, "base_trade_plan", "symbol")
            or _extract_plan_value(recalculation, "recalculated_trade_plan", "symbol")
            or _extract_plan_value(recalculation, "base_trade_plan", "symbol")
            or _str_or_none(report.get("symbol"))
        ),
        option_type=option_type,
        source_branch_unique_code=source_branch,
        workbook_row_number=_int_or_none(current_day_result.get("row_number")),
        source_rule=(
            _str_or_none(current_day_result.get("source_rule"))
            or _str_or_none(recalculation_result.get("source_rule"))
        ),
        selected_contract_symbol=selected_contract_symbol,
        lifecycle_price_source=lifecycle_price_source,
        contract_specific_intraday_found=contract_specific_intraday_found,
        contract_specific_bars_available_count=contract_specific_bars_available_count,
        contract_specific_bars_usable_count=contract_specific_bars_usable_count,
        contract_specific_fallback_used=contract_specific_fallback_used,
        contract_specific_fallback_reason=contract_specific_fallback_reason,
        lifecycle_bars_used_count=lifecycle_bars_used_count,
        monthly_status=_str_or_none(evaluation.get("monthly_status")),
        monthly_status_trigger=_str_or_none(evaluation.get("monthly_status_trigger")),
        accepted=bool(evaluation.get("accepted", False)),
        rejection_reason=str(evaluation.get("rejection_reason", "")),
        start_strike=_float_or_none(trade_outputs.get("start_strike")),
        end_strike=_float_or_none(trade_outputs.get("end_strike")),
        ideal_premium=_float_or_none(trade_outputs.get("ideal_premium")),
        minimum_premium=_float_or_none(trade_outputs.get("minimum_premium")),
        entry_price=_float_or_none(trade_outputs.get("entry_price")),
        stoploss_price=_float_or_none(trade_outputs.get("stoploss_price")),
        target_price=_float_or_none(trade_outputs.get("target_price")),
        exit_price=_float_or_none(lifecycle_result.get("exit_price")),
        net_pnl_points=_float_or_none(lifecycle_result.get("net_pnl_points")),
        net_pnl_rupees=_float_or_none(lifecycle_result.get("net_pnl_rupees")),
        recalculation_applied=bool(recalculation.get("recalculation_applied", False)),
        current_day_fsl_trp_applied=bool(current_day.get("applied", False)),
        option_chain_selected=bool(option_chain.get("selected", False)),
        expiry_day_exit_pending=(
            bool(expiry_day_review.get("applicable"))
            and bool(expiry_day_review.get("is_expiry_day"))
            and not bool(expiry_day_review.get("exit_satisfied"))
        ),
        warning_flags=tuple(sorted(warning_flags)),
    )


def _resolve_option_type(
    *,
    report: dict[str, Any],
    evaluation: dict[str, Any],
    recalculation: dict[str, Any],
    current_day: dict[str, Any],
    selected_contract: dict[str, Any],
    trade_outputs: dict[str, Any],
    source_branch: str | None,
    warnings: list[str],
) -> str | None:
    branch_option_type = _branch_option_type(source_branch) if source_branch is not None else None
    option_type = (
        _extract_plan_value(current_day, "effective_trade_plan", "option_type")
        or _extract_plan_value(current_day, "base_trade_plan", "option_type")
        or _extract_plan_value(recalculation, "recalculated_trade_plan", "option_type")
        or _extract_plan_value(recalculation, "base_trade_plan", "option_type")
        or _str_or_none(selected_contract.get("option_type"))
        or branch_option_type
        or _infer_option_type_from_strategy_path(report.get("strategy_path"))
        or _infer_option_type_from_trade_outputs(trade_outputs)
    )
    if option_type is None and evaluation.get("selected_branch_unique_codes"):
        warnings.append(
            f"Option type inference fell back to unknown for {evaluation.get('timestamp')}; "
            "selected_branch_unique_codes were present but not enough to infer the branch."
        )
    return option_type


def _resolve_source_branch_unique_code(
    *,
    report: dict[str, Any],
    evaluation: dict[str, Any],
    timestamp_position: int,
    option_type: str | None,
) -> str | None:
    validation = evaluation.get("validation", {})
    validation = validation if isinstance(validation, dict) else {}
    current_day = validation.get("s23_current_day_fsl_trp")
    current_day = current_day if isinstance(current_day, dict) else {}
    recalculation = validation.get("s23_recalculation")
    recalculation = recalculation if isinstance(recalculation, dict) else {}

    return (
        _str_or_none(current_day.get("branch_unique_code"))
        or _str_or_none(recalculation.get("branch_unique_code"))
        or _infer_branch_from_selected_branches(
            evaluation.get("selected_branch_unique_codes"),
            timestamp_position=timestamp_position,
            option_type=option_type,
        )
        or _infer_branch_from_strategy_path(report.get("strategy_path"))
    )


def _infer_branch_from_selected_branches(
    value: Any,
    *,
    timestamp_position: int,
    option_type: str | None,
) -> str | None:
    if not isinstance(value, list):
        return None
    branches = [str(item) for item in value if item]
    if not branches:
        return None
    if len(branches) == 1:
        return _normalize_branch_identifier(branches[0])
    if option_type is None:
        if timestamp_position < len(branches):
            return _normalize_branch_identifier(branches[timestamp_position])
        return None
    matching = [
        branch
        for branch in branches
        if _branch_option_type(branch) == option_type
    ]
    if len(matching) == 1:
        return _normalize_branch_identifier(matching[0])
    return None


def _branch_option_type(branch_unique_code: str) -> str:
    normalized = branch_unique_code.upper()
    if normalized.endswith("_PUT"):
        return "PUT"
    return "CALL"


def _infer_branch_from_strategy_path(value: Any) -> str | None:
    raw_value = _str_or_none(value)
    if raw_value is None:
        return None
    name = Path(raw_value).name
    if not name:
        return None
    branch = Path(name).stem if name.endswith(".yaml") else name
    return _normalize_branch_identifier(branch)


def _normalize_branch_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    if value.startswith("S23_") and "_OP_SELL_" in value:
        return value[4:]
    return value


def _infer_option_type_from_strategy_path(value: Any) -> str | None:
    branch = _infer_branch_from_strategy_path(value)
    if branch is None:
        return None
    return _branch_option_type(branch)


def _infer_option_type_from_trade_outputs(trade_outputs: dict[str, Any]) -> str | None:
    start_strike = _float_or_none(trade_outputs.get("start_strike"))
    end_strike = _float_or_none(trade_outputs.get("end_strike"))
    if start_strike is None or end_strike is None:
        return None
    if start_strike < end_strike:
        return "PUT"
    if start_strike > end_strike:
        return "CALL"
    return None


def _extract_plan_value(container: dict[str, Any], key: str, field: str) -> str | None:
    plan = container.get(key)
    if not isinstance(plan, dict):
        return None
    return _str_or_none(plan.get(field))


def _diff_trade_fields(
    baseline: NormalizedTradeSummary,
    candidate: NormalizedTradeSummary,
) -> dict[str, dict[str, Any]]:
    baseline_dict = asdict(baseline)
    candidate_dict = asdict(candidate)
    differences: dict[str, dict[str, Any]] = {}
    ignored_fields = {"trade_key", "timestamp", "trade_date", "warning_flags"}
    for field in sorted(set(baseline_dict) | set(candidate_dict)):
        if field in ignored_fields:
            continue
        left = baseline_dict.get(field)
        right = candidate_dict.get(field)
        if left == right:
            continue
        differences[field] = {
            "baseline": left,
            "candidate": right,
        }
    return differences


def _trade_snapshot_dict(trade: NormalizedTradeSummary) -> dict[str, Any]:
    return {
        "trade_key": trade.trade_key,
        "timestamp": trade.timestamp,
        "source_branch_unique_code": trade.source_branch_unique_code,
        "option_type": trade.option_type,
        "entry_price": trade.entry_price,
        "stoploss_price": trade.stoploss_price,
        "target_price": trade.target_price,
        "rejection_reason": trade.rejection_reason,
    }


def _build_skip_reason_distribution(monthly_status_skips: list[Any]) -> dict[str, int]:
    distribution: dict[str, int] = {}
    for item in monthly_status_skips:
        if not isinstance(item, dict):
            continue
        reason = str(item.get("reason", "unknown"))
        distribution[reason] = distribution.get(reason, 0) + 1
    return distribution


def _collect_report_level_warnings(evaluations: list[Any]) -> list[str]:
    aggregated: dict[str, int] = {}
    for evaluation in evaluations:
        if not isinstance(evaluation, dict):
            continue
        validation = evaluation.get("validation", {})
        if not isinstance(validation, dict):
            continue
        for key in (
            "s23_current_day_fsl_trp",
            "s23_recalculation",
            "contract_specific_lifecycle",
            "option_chain_selection",
            "expiry_day_review",
        ):
            payload = validation.get(key)
            if not isinstance(payload, dict):
                continue
            warning = _str_or_none(payload.get("warning"))
            if warning is None:
                continue
            warning_key = f"{key}: {warning}"
            aggregated[warning_key] = aggregated.get(warning_key, 0) + 1
    return [
        f"{warning_text} ({count} evaluation(s))"
        for warning_text, count in sorted(aggregated.items(), key=lambda item: item[0])
    ]


def _normalize_cost_model(value: Any) -> tuple[tuple[str, float], ...]:
    if not isinstance(value, dict):
        return ()
    normalized: list[tuple[str, float]] = []
    for key in (
        "slippage_points_per_side",
        "brokerage_points_per_trade",
        "other_cost_points_per_trade",
    ):
        raw = value.get(key)
        if raw is None:
            continue
        normalized.append((key, float(raw)))
    return tuple(normalized)


def _normalize_input_datasets(
    value: Any,
) -> tuple[tuple[InputDatasetSummary, ...], bool, bool]:
    if not isinstance(value, dict):
        return (), False, False
    datasets = value.get("datasets", {})
    if not isinstance(datasets, dict):
        datasets = {}

    normalized: list[InputDatasetSummary] = []
    for name in sorted(datasets):
        raw_dataset = datasets.get(name)
        if not isinstance(raw_dataset, dict):
            continue
        path = _str_or_none(raw_dataset.get("path"))
        project_fixture = bool(raw_dataset.get("project_fixture"))
        synthetic_fixture = bool(raw_dataset.get("synthetic_fixture"))
        normalized.append(
            InputDatasetSummary(
                name=str(name),
                path=path,
                provided=bool(raw_dataset.get("provided", False)),
                used=bool(raw_dataset.get("used", False)),
                fallback_behavior=_str_or_none(raw_dataset.get("fallback_behavior")),
                project_fixture=project_fixture,
                synthetic_fixture=synthetic_fixture,
            )
        )

    return (
        tuple(normalized),
        bool(value.get("project_fixture_data_used", False)),
        bool(value.get("synthetic_fixture_data_used", False)),
    )


def _coerce_count_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    distribution: dict[str, int] = {}
    for key, raw_count in value.items():
        try:
            distribution[str(key)] = int(raw_count)
        except (TypeError, ValueError):
            continue
    return distribution


def _sorted_distribution(distribution: dict[str, int]) -> tuple[tuple[str, int], ...]:
    return tuple(sorted(distribution.items(), key=lambda item: (item[0], item[1])))


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _str_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _int_or_default(value: Any, default: int) -> int:
    if value is None:
        return int(default)
    return int(value)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _safe_percentage(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return (float(numerator) / float(denominator)) * 100.0


def _best_label(
    reports: list[BacktestModeSummary],
    *,
    key,
    prefer_high: bool,
) -> str | None:
    comparable = [report for report in reports if key(report) is not None]
    if not comparable:
        return None
    if prefer_high:
        return max(comparable, key=key).label
    return min(comparable, key=key).label


def _format_number(value: float | None, *, digits: int) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


def _format_cost_model(value: tuple[tuple[str, float], ...]) -> str:
    if not value:
        return "-"
    return ", ".join(f"{key}={amount:.2f}" for key, amount in value)


def _markdown_dataset_cell(dataset: InputDatasetSummary | None) -> str:
    if dataset is None or dataset.path is None:
        if dataset is not None and dataset.fallback_behavior:
            return f"`fallback:{dataset.fallback_behavior}`"
        return "-"
    parts = [Path(dataset.path).name]
    if dataset.used:
        parts.append("used")
    else:
        parts.append("provided")
    if dataset.fallback_behavior:
        parts.append(f"fallback:{dataset.fallback_behavior}")
    if dataset.synthetic_fixture:
        parts.append("synthetic")
    elif dataset.project_fixture:
        parts.append("fixture")
    return "`" + "; ".join(parts) + "`"


def _markdown_field_delta(value: dict[str, Any] | None) -> str:
    if value is None:
        return "-"
    return f"`{value.get('baseline')}` -> `{value.get('candidate')}`"
