from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class BacktestModeSummary:
    label: str
    path: str
    mode: str
    strategy_path: str | None
    strategy_root: str | None
    shared_data_root: str | None
    eod_policy: str | None
    use_monthly_status_engine: bool
    enable_s23_recalculation: bool
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
    expiry_day_candidates: int
    expiry_day_exit_satisfied: int
    expiry_day_exit_pending: int


@dataclass(frozen=True, slots=True)
class BacktestModeComparison:
    reports: list[BacktestModeSummary]
    best_total_net_pnl_rupees_label: str | None
    best_win_rate_label: str | None
    lowest_max_drawdown_label: str | None
    notes: tuple[str, ...]


def load_backtest_report(path: str | Path) -> dict[str, Any]:
    report_path = Path(path)
    return json.loads(report_path.read_text(encoding="utf-8"))


def summarize_backtest_report(
    *,
    label: str,
    path: str | Path,
    report: dict[str, Any],
) -> BacktestModeSummary:
    metrics = report.get("metrics", {})
    evaluations = report.get("evaluations", [])
    monthly_status_skips = report.get("monthly_status_skips", [])

    recalculation_applied_count = 0
    option_chain_selected_count = 0
    contract_specific_series_count = 0
    contract_specific_fallback_count = 0
    for evaluation in evaluations:
        validation = evaluation.get("validation", {})
        recalculation = validation.get("s23_recalculation")
        if isinstance(recalculation, dict) and recalculation.get("recalculation_applied"):
            recalculation_applied_count += 1

        option_chain = validation.get("option_chain_selection")
        if isinstance(option_chain, dict) and option_chain.get("selected"):
            option_chain_selected_count += 1

        contract_specific = validation.get("contract_specific_lifecycle")
        if not isinstance(contract_specific, dict):
            continue
        source = contract_specific.get("lifecycle_price_source")
        if source == "contract_specific_series":
            contract_specific_series_count += 1
        elif source == "generic_option_series":
            contract_specific_fallback_count += 1

    total_evaluations = _int_or_default(
        metrics.get("total_evaluations"),
        len(evaluations) if evaluations else 1,
    )
    accepted_candidates = _int_or_default(
        metrics.get("accepted_candidates"),
        sum(1 for evaluation in evaluations if evaluation.get("accepted")) if evaluations else 0,
    )
    rejected_candidates = _int_or_default(
        metrics.get("rejected_candidates"),
        sum(1 for evaluation in evaluations if not evaluation.get("accepted")) if evaluations else 0,
    )

    return BacktestModeSummary(
        label=label,
        path=str(Path(path)),
        mode=str(report.get("mode", "unknown")),
        strategy_path=_str_or_none(report.get("strategy_path")),
        strategy_root=_str_or_none(report.get("strategy_root")),
        shared_data_root=_str_or_none(report.get("shared_data_root")),
        eod_policy=_str_or_none(report.get("eod_policy")),
        use_monthly_status_engine=bool(report.get("use_monthly_status_engine", False)),
        enable_s23_recalculation=bool(report.get("enable_s23_recalculation", False)),
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
        expiry_day_candidates=_int_or_default(metrics.get("expiry_day_candidates"), 0),
        expiry_day_exit_satisfied=_int_or_default(
            metrics.get("expiry_day_exit_satisfied"),
            0,
        ),
        expiry_day_exit_pending=_int_or_default(
            metrics.get("expiry_day_exit_pending"),
            0,
        ),
    )


def compare_backtest_reports(
    labeled_reports: list[tuple[str, str | Path, dict[str, Any]]],
) -> BacktestModeComparison:
    summaries = [
        summarize_backtest_report(label=label, path=path, report=report)
        for label, path, report in labeled_reports
    ]
    notes: list[str] = []
    if any(summary.mode != "historical" for summary in summaries):
        notes.append(
            "One or more inputs are not historical reports; some metrics may not be directly comparable."
        )
    if any(summary.total_evaluations != summaries[0].total_evaluations for summary in summaries[1:]):
        notes.append(
            "Reports have different evaluation counts; compare totals with care."
        )
    if any(summary.monthly_status_skip_count for summary in summaries):
        notes.append(
            "Monthly-status skip counts differ across reports and can affect aggregate performance comparisons."
        )

    return BacktestModeComparison(
        reports=summaries,
        best_total_net_pnl_rupees_label=_best_label(
            summaries,
            key=lambda item: item.total_net_pnl_rupees,
            prefer_high=True,
        ),
        best_win_rate_label=_best_label(
            summaries,
            key=lambda item: item.win_rate,
            prefer_high=True,
        ),
        lowest_max_drawdown_label=_best_label(
            summaries,
            key=lambda item: item.max_drawdown_rupees,
            prefer_high=False,
        ),
        notes=tuple(notes),
    )


def comparison_to_dict(comparison: BacktestModeComparison) -> dict[str, Any]:
    return {
        "reports": [asdict(report) for report in comparison.reports],
        "best_total_net_pnl_rupees_label": comparison.best_total_net_pnl_rupees_label,
        "best_win_rate_label": comparison.best_win_rate_label,
        "lowest_max_drawdown_label": comparison.lowest_max_drawdown_label,
        "notes": list(comparison.notes),
    }


def render_comparison_markdown(comparison: BacktestModeComparison) -> str:
    lines = [
        "# Backtest Mode Comparison",
        "",
        "This report compares existing TFIS backtest outputs. It is a reporting aid only and does not rerun any strategy logic.",
        "",
        "## Leaders",
        "",
        f"- best_total_net_pnl_rupees: `{comparison.best_total_net_pnl_rupees_label or '-'}`",
        f"- best_win_rate: `{comparison.best_win_rate_label or '-'}`",
        f"- lowest_max_drawdown: `{comparison.lowest_max_drawdown_label or '-'}`",
        "",
        "## Summary Table",
        "",
        "| Label | Mode | Monthly Status | Recalc | Chain | Contract Series | Evaluations | Accepted | Net P&L Rs | Win Rate | Max DD Rs |",
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for report in comparison.reports:
        lines.append(
            "| "
            f"{report.label} | "
            f"{report.mode} | "
            f"{_yes_no(report.use_monthly_status_engine)} | "
            f"{_yes_no(report.enable_s23_recalculation)} | "
            f"{_yes_no(report.enable_option_chain_selection)} | "
            f"{_yes_no(report.enable_contract_specific_lifecycle)} | "
            f"{report.total_evaluations} | "
            f"{report.accepted_candidates} | "
            f"{_format_number(report.total_net_pnl_rupees, digits=2)} | "
            f"{_format_percent(report.win_rate)} | "
            f"{_format_number(report.max_drawdown_rupees, digits=2)} |"
        )

    lines.extend(
        [
            "",
            "## Audit Coverage",
            "",
            "| Label | Recalc Applied | Chain Selected | Contract Series Used | Generic Fallback | Monthly Status Skips | Expiry-Day Pending |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for report in comparison.reports:
        lines.append(
            "| "
            f"{report.label} | "
            f"{report.recalculation_applied_count} | "
            f"{report.option_chain_selected_count} | "
            f"{report.contract_specific_series_count} | "
            f"{report.contract_specific_fallback_count} | "
            f"{report.monthly_status_skip_count} | "
            f"{report.expiry_day_exit_pending} |"
        )

    if comparison.notes:
        lines.extend(["", "## Notes", ""])
        for note in comparison.notes:
            lines.append(f"- {note}")

    return "\n".join(lines) + "\n"


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


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


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


def _format_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.2f}%"
