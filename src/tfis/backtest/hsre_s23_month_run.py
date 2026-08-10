from __future__ import annotations

import csv
import hashlib
import json
import math
import time as time_module
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path
from typing import Any

from tfis.backtest.hsre_s23_trade_lifecycle import (
    HsreS23TradeLifecycleBuilder,
    HsreS23TradeLifecyclePacket,
    hsre_s23_trade_lifecycle_packet_to_dict,
)
from tfis.backtest.nifty_hsre_data_adapter import NiftyHsreHistoricalMarketDataProvider


DAILY_DECISION_FIELDS = (
    "date",
    "monthly_status",
    "monthly_trigger",
    "branch",
    "strategy_code",
    "selected_contract",
    "expiry",
    "strike",
    "option_type",
    "premium_0916",
    "oi_0916",
    "volume_0916",
    "historical_lot_size",
    "minimum_oi_lots",
    "minimum_oi_units",
    "OPT_PRV_2DHH",
    "OPT_PRV_2DLL",
    "OPT_PRV_3DHH",
    "OPT_PRV_3DLL",
    "base_entry",
    "base_target",
    "base_stoploss",
    "orpt_low",
    "orpt_high",
    "entry_missed",
    "recalculation_required",
    "recalculated_contract",
    "rc_required",
    "rc_result",
    "final_contract",
    "final_entry",
    "final_target",
    "final_stoploss",
    "final_order_verdict",
    "entry_triggered",
    "trigger_time",
    "fill_price",
    "exit_time",
    "exit_price",
    "exit_reason",
    "gross_points",
    "cost_points",
    "net_points",
    "rupee_pnl",
    "rupee_pnl_status",
    "evidence_status",
)

TRADE_FIELDS = (
    "date",
    "contract",
    "branch",
    "option_type",
    "entry",
    "target",
    "stoploss",
    "trigger_time",
    "fill_price",
    "exit_time",
    "exit_price",
    "exit_reason",
    "gross_points",
    "cost_points",
    "net_points",
    "rupee_pnl",
    "rupee_pnl_status",
)

NON_TRADE_FIELDS = (
    "date",
    "status",
    "reason_code",
    "reason",
    "branch",
    "contract",
    "final_order_verdict",
)

CANDIDATE_FIELDS = (
    "date",
    "branch",
    "candidate_count",
    "expiry_rejected",
    "oi_rejected",
    "premium_rejected",
    "qualified_count",
    "historical_lot_size",
    "minimum_oi_lots",
    "minimum_oi_units",
    "selected",
    "selected_symbol",
    "selection_reason",
)

ENTRY_DISTANCE_FIELDS = (
    "date",
    "contract",
    "branch",
    "option_type",
    "entry",
    "post_order_session_low",
    "post_order_session_high",
    "entry_minus_low",
    "low_minus_entry",
    "entry_touched",
    "min_distance_abs_points",
    "min_distance_pct_of_entry",
)


@dataclass(frozen=True, slots=True)
class HsreS23MonthRunResult:
    month: str
    output_dir: Path
    sessions: tuple[str, ...]
    packets: tuple[HsreS23TradeLifecyclePacket, ...]
    summary: dict[str, Any]
    hashes: dict[str, str]
    runtime_seconds: float


class HsreS23January2024Runner:
    """Run the accepted S23 historical pipeline across observed historical sessions."""

    MONTH = "2024-01"

    def __init__(
        self,
        provider: NiftyHsreHistoricalMarketDataProvider | None = None,
        *,
        data_root: str | Path = r"D:\HistoricalData\Nifty",
        lifecycle_builder: HsreS23TradeLifecycleBuilder | None = None,
        start_date: date = date(2024, 1, 1),
        end_date: date = date(2024, 1, 31),
        period_label: str = "2024-01",
    ) -> None:
        self.provider = provider or NiftyHsreHistoricalMarketDataProvider(
            data_root,
            max_cached_sessions=128,
        )
        self.data_root = Path(data_root)
        self.lifecycle_builder = lifecycle_builder or HsreS23TradeLifecycleBuilder(self.provider)
        if end_date < start_date:
            raise ValueError("end_date must be greater than or equal to start_date")
        self.start_date = start_date
        self.end_date = end_date
        self.period_label = period_label

    def run(
        self,
        *,
        output_dir: str | Path = Path("reports") / "hsre" / "S23" / "2024-01",
    ) -> HsreS23MonthRunResult:
        started = time_module.perf_counter()
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        sessions = self._sessions()

        packets = tuple(
            self.lifecycle_builder.build_for_session(
                session_date=session,
                planning_time=time(9, 16),
            )
            for session in sessions
        )
        daily_rows = [self._daily_row(packet) for packet in packets]
        trade_rows = [row for packet in packets for row in self._trade_rows(packet)]
        non_trade_rows = [row for packet in packets for row in self._non_trade_rows(packet)]
        candidate_rows = [row for packet in packets for row in self._candidate_rows(packet)]
        entry_distance_rows = [row for packet in packets for row in self._entry_distance_rows(packet)]

        self._write_csv(output_path / "daily_decisions.csv", DAILY_DECISION_FIELDS, daily_rows)
        self._write_csv(output_path / "trades.csv", TRADE_FIELDS, trade_rows)
        self._write_csv(output_path / "non_trades.csv", NON_TRADE_FIELDS, non_trade_rows)
        self._write_csv(
            output_path / "rejected_candidates_summary.csv",
            CANDIDATE_FIELDS,
            candidate_rows,
        )
        self._write_csv(output_path / "entry_distance.csv", ENTRY_DISTANCE_FIELDS, entry_distance_rows)

        hashes = self._hashes(output_path)
        runtime = time_module.perf_counter() - started
        summary = self._summary(
            sessions=sessions,
            packets=packets,
            daily_rows=daily_rows,
            trade_rows=trade_rows,
            non_trade_rows=non_trade_rows,
            candidate_rows=candidate_rows,
            entry_distance_rows=entry_distance_rows,
            output_path=output_path,
            data_root=self.data_root,
            hashes=hashes,
            runtime_seconds=runtime,
        )
        self._write_json(output_path / "summary.json", summary)
        self._write_text(output_path / "summary.md", self._summary_markdown(summary))
        hashes = self._hashes(output_path)
        summary["hashes"] = hashes
        self._write_json(output_path / "summary.json", summary)
        self._write_text(output_path / "summary.md", self._summary_markdown(summary))
        return HsreS23MonthRunResult(
            month=self.period_label,
            output_dir=output_path,
            sessions=tuple(session.isoformat() for session in sessions),
            packets=packets,
            summary=summary,
            hashes=hashes,
            runtime_seconds=runtime,
        )

    def _sessions(self) -> tuple[date, ...]:
        return tuple(
            session
            for session in self.provider.available_spot_sessions()
            if self.start_date <= session <= self.end_date
        )

    def _january_sessions(self) -> tuple[date, ...]:
        return self._sessions()

    @staticmethod
    def _daily_row(packet: HsreS23TradeLifecyclePacket) -> dict[str, Any]:
        final_order = packet.data_provenance.get("final_order", {})
        base_packet = final_order.get("provenance", {}).get("base_packet", {})
        option_ref = base_packet.get("option_reference_packet", {}) or {}
        selected = option_ref.get("contract", {}) or {}
        levels = base_packet.get("strategy_evaluator_inputs", {}).get("runtime_values", {}).get("OPT_LEVELS", {}) or {}
        orpt = final_order.get("orpt_evidence") or {}
        entry_missed = final_order.get("entry_missed_result") or {}
        rc_evidence = final_order.get("rc_evidence") or {}
        return {
            "date": packet.session_date,
            "monthly_status": packet.monthly_status,
            "monthly_trigger": base_packet.get("monthly_status_trigger"),
            "branch": packet.branch,
            "strategy_code": "S23",
            "selected_contract": final_order.get("base_contract") or packet.contract,
            "expiry": base_packet.get("selected_expiry") or selected.get("expiry"),
            "strike": base_packet.get("selected_strike") or selected.get("strike"),
            "option_type": base_packet.get("selected_option_type") or selected.get("option_type"),
            "premium_0916": base_packet.get("selected_premium_0916"),
            "oi_0916": base_packet.get("selected_oi_0916"),
            "volume_0916": base_packet.get("selected_volume_0916"),
            "historical_lot_size": base_packet.get("historical_lot_size"),
            "minimum_oi_lots": base_packet.get("minimum_oi_lots"),
            "minimum_oi_units": base_packet.get("minimum_oi_units"),
            "OPT_PRV_2DHH": levels.get("OPT_PRV_2DHH"),
            "OPT_PRV_2DLL": levels.get("OPT_PRV_2DLL"),
            "OPT_PRV_3DHH": levels.get("OPT_PRV_3DHH"),
            "OPT_PRV_3DLL": levels.get("OPT_PRV_3DLL"),
            "base_entry": final_order.get("base_entry"),
            "base_target": final_order.get("base_target"),
            "base_stoploss": final_order.get("base_stoploss"),
            "orpt_low": entry_missed.get("compared_orpt_option_low")
            or orpt.get("option_low_through_cutoff"),
            "orpt_high": orpt.get("option_high_through_cutoff"),
            "entry_missed": entry_missed.get("entry_missed"),
            "recalculation_required": final_order.get("recalculation_required"),
            "recalculated_contract": final_order.get("recalculated_contract"),
            "rc_required": final_order.get("rc_required"),
            "rc_result": rc_evidence.get("rc_result"),
            "final_contract": packet.contract,
            "final_entry": packet.entry_threshold,
            "final_target": packet.initial_target,
            "final_stoploss": packet.initial_stoploss,
            "final_order_verdict": final_order.get("final_decision_verdict"),
            "entry_triggered": packet.entry_triggered,
            "trigger_time": packet.trigger_time,
            "fill_price": packet.fill_price,
            "exit_time": packet.exit_time,
            "exit_price": packet.exit_price,
            "exit_reason": packet.exit_reason,
            "gross_points": packet.pnl.gross_points,
            "cost_points": packet.pnl.total_cost_points,
            "net_points": packet.pnl.net_points,
            "rupee_pnl": packet.pnl.rupee_pnl,
            "rupee_pnl_status": packet.pnl.rupee_pnl_status,
            "evidence_status": packet.evidence_completeness,
        }

    @classmethod
    def _trade_rows(cls, packet: HsreS23TradeLifecyclePacket) -> list[dict[str, Any]]:
        if not packet.entry_triggered:
            return []
        row = cls._daily_row(packet)
        return [
            {
                "date": packet.session_date,
                "contract": packet.contract,
                "branch": packet.branch,
                "option_type": row["option_type"],
                "entry": packet.entry_threshold,
                "target": packet.initial_target,
                "stoploss": packet.initial_stoploss,
                "trigger_time": packet.trigger_time,
                "fill_price": packet.fill_price,
                "exit_time": packet.exit_time,
                "exit_price": packet.exit_price,
                "exit_reason": packet.exit_reason,
                "gross_points": packet.pnl.gross_points,
                "cost_points": packet.pnl.total_cost_points,
                "net_points": packet.pnl.net_points,
                "rupee_pnl": packet.pnl.rupee_pnl,
                "rupee_pnl_status": packet.pnl.rupee_pnl_status,
            }
        ]

    @classmethod
    def _non_trade_rows(cls, packet: HsreS23TradeLifecyclePacket) -> list[dict[str, Any]]:
        if packet.entry_triggered:
            return []
        final_order = packet.data_provenance.get("final_order", {})
        return [
            {
                "date": packet.session_date,
                "status": packet.status,
                "reason_code": cls._non_trade_reason_code(packet, final_order),
                "reason": packet.status_reason,
                "branch": packet.branch,
                "contract": packet.contract,
                "final_order_verdict": final_order.get("final_decision_verdict"),
            }
        ]

    @staticmethod
    def _candidate_rows(packet: HsreS23TradeLifecyclePacket) -> list[dict[str, Any]]:
        final_order = packet.data_provenance.get("final_order", {})
        base_packet = final_order.get("provenance", {}).get("base_packet", {})
        rows = []
        for audit in base_packet.get("branch_attempts", []) or []:
            rows.append(
                {
                    "date": packet.session_date,
                    "branch": audit.get("strategy_unique_code"),
                    "candidate_count": audit.get("candidate_count"),
                    "expiry_rejected": audit.get("expiry_rejection_count"),
                    "oi_rejected": audit.get("oi_rejection_count"),
                    "premium_rejected": audit.get("premium_rejection_count"),
                    "qualified_count": audit.get("qualified_count"),
                    "historical_lot_size": audit.get("historical_lot_size"),
                    "minimum_oi_lots": audit.get("minimum_oi_lots"),
                    "minimum_oi_units": audit.get("minimum_oi_units"),
                    "selected": audit.get("selection_selected"),
                    "selected_symbol": audit.get("selected_symbol"),
                    "selection_reason": audit.get("selection_reason"),
                }
            )
        return rows

    @classmethod
    def _entry_distance_rows(cls, packet: HsreS23TradeLifecyclePacket) -> list[dict[str, Any]]:
        if packet.entry_threshold is None or packet.contract_series_audit is None:
            return []
        row = cls._daily_row(packet)
        low = packet.contract_series_audit.session_low
        high = packet.contract_series_audit.session_high
        if low is None or high is None:
            return []
        touched = bool(low <= packet.entry_threshold <= high)
        if touched:
            distance = 0.0
        else:
            distance = min(abs(packet.entry_threshold - low), abs(packet.entry_threshold - high))
        return [
            {
                "date": packet.session_date,
                "contract": packet.contract,
                "branch": packet.branch,
                "option_type": row["option_type"],
                "entry": packet.entry_threshold,
                "post_order_session_low": low,
                "post_order_session_high": high,
                "entry_minus_low": packet.entry_threshold - low,
                "low_minus_entry": low - packet.entry_threshold,
                "entry_touched": touched,
                "min_distance_abs_points": distance,
                "min_distance_pct_of_entry": distance / packet.entry_threshold
                if packet.entry_threshold else None,
            }
        ]

    @staticmethod
    def _non_trade_reason_code(packet: HsreS23TradeLifecyclePacket, final_order: dict[str, Any]) -> str:
        if packet.status == "ENTRY_NOT_TRIGGERED":
            return "NORMAL_ORDER_READY_BUT_ENTRY_NOT_TRIGGERED"
        if packet.status == "LIFECYCLE_EVIDENCE_INCOMPLETE":
            return "LIFECYCLE_EVIDENCE_INCOMPLETE"
        verdict = str(final_order.get("final_decision_verdict") or "")
        if verdict and verdict != "BASE_DECISION_NOT_READY":
            return verdict
        reason = packet.status_reason.lower()
        if "option lookback" in reason or "prior daily bars" in reason:
            return "INSUFFICIENT_OPTION_HISTORY"
        if "minimum premium" in reason or "no qualifying" in reason:
            return "NO_QUALIFYING_CONTRACT"
        return verdict or packet.status

    def _summary(
        self,
        *,
        sessions: tuple[date, ...],
        packets: tuple[HsreS23TradeLifecyclePacket, ...],
        daily_rows: list[dict[str, Any]],
        trade_rows: list[dict[str, Any]],
        non_trade_rows: list[dict[str, Any]],
        candidate_rows: list[dict[str, Any]],
        entry_distance_rows: list[dict[str, Any]],
        output_path: Path,
        data_root: Path,
        hashes: dict[str, str],
        runtime_seconds: float,
    ) -> dict[str, Any]:
        status_counts = _counts(packet.status for packet in packets)
        branch_counts = _counts(packet.branch or "NONE" for packet in packets)
        verdict_counts = _counts(str(row["final_order_verdict"]) for row in daily_rows)
        exit_counts = _counts(str(row["exit_reason"]) for row in trade_rows)
        non_trade_counts = _counts(str(row["reason_code"]) for row in non_trade_rows)
        orders = [row for row in daily_rows if row["final_entry"] is not None]
        triggered = [row for row in daily_rows if row["entry_triggered"]]
        net_points = [float(row["net_points"]) for row in trade_rows]
        wins = [value for value in net_points if value > 0]
        losses = [value for value in net_points if value < 0]
        breakeven = [value for value in net_points if value == 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        equity_curve: list[float] = []
        running = 0.0
        for value in net_points:
            running += value
            equity_curve.append(running)
        max_drawdown = _max_drawdown(equity_curve)
        option_breakdown: dict[str, dict[str, Any]] = {}
        for option_type in ("CALL", "PUT"):
            side_orders = [row for row in orders if row["option_type"] == option_type]
            side_trades = [row for row in trade_rows if row["option_type"] == option_type]
            side_points = [float(row["net_points"]) for row in side_trades]
            option_breakdown[option_type] = {
                "orders_ready": len(side_orders),
                "entries_triggered": sum(1 for row in side_orders if row["entry_triggered"]),
                "trades": len(side_trades),
                "wins": sum(1 for value in side_points if value > 0),
                "losses": sum(1 for value in side_points if value < 0),
                "net_points": sum(side_points),
            }
        distances = [
            float(row["min_distance_abs_points"])
            for row in entry_distance_rows
            if row["min_distance_abs_points"] is not None
        ]
        return {
            "month": self.period_label,
            "data_root": str(data_root),
            "date_coverage": {
                "start": sessions[0].isoformat() if sessions else None,
                "end": sessions[-1].isoformat() if sessions else None,
                "observed_trading_days": len(sessions),
                "sessions": [session.isoformat() for session in sessions],
            },
            "runtime_seconds": None,
            "status_counts": status_counts,
            "branch_counts": branch_counts,
            "final_order_verdict_counts": verdict_counts,
            "funnel": {
                "observed_trading_days": len(sessions),
                "base_orders_created": sum(1 for row in daily_rows if row["base_entry"] is not None),
                "final_orders_ready": len(orders),
                "normal_orders_ready": verdict_counts.get("NORMAL_ORDER_READY", 0),
                "recalculated_orders_ready": verdict_counts.get("RECALCULATED_ORDER_READY", 0),
                "entry_missed_at_orpt": sum(1 for row in daily_rows if row["entry_missed"]),
                "rc_rejected": verdict_counts.get("RC_REJECTED", 0),
                "no_qualifying_recalculated_contract": verdict_counts.get(
                    "NO_QUALIFYING_RECALCULATED_CONTRACT",
                    0,
                ),
                "entries_triggered": len(triggered),
                "entries_not_triggered": sum(1 for row in orders if not row["entry_triggered"]),
                "closed_trades": len(trade_rows),
                "incomplete_trades": status_counts.get("TRADE_OPEN_NO_EXIT", 0)
                + status_counts.get("LIFECYCLE_EVIDENCE_INCOMPLETE", 0),
            },
            "non_trade_reason_counts": non_trade_counts,
            "trade_metrics": {
                "orders_ready": len(orders),
                "entries_triggered": len(triggered),
                "trigger_rate": len(triggered) / len(orders) if orders else None,
                "trades": len(trade_rows),
                "wins": len(wins),
                "losses": len(losses),
                "breakeven": len(breakeven),
                "win_rate": len(wins) / len(trade_rows) if trade_rows else None,
                "exit_distribution": exit_counts,
                "gross_positive_points": gross_profit,
                "gross_negative_points": -gross_loss,
                "net_total_points": sum(net_points),
                "average_net_points": sum(net_points) / len(net_points) if net_points else 0.0,
                "profit_factor": gross_profit / gross_loss if gross_loss else None,
                "expectancy_points": sum(net_points) / len(trade_rows) if trade_rows else 0.0,
                "max_drawdown_points": max_drawdown,
            },
            "ce_pe_breakdown": option_breakdown,
            "orpt_recalculation": {
                "orders_evaluated": len(orders),
                "entry_missed_at_orpt": sum(1 for row in daily_rows if row["entry_missed"]),
                "recalculation_required": sum(1 for row in daily_rows if row["recalculation_required"]),
                "rc_required": sum(1 for row in daily_rows if row["rc_required"]),
                "recalculated_orders_ready": verdict_counts.get("RECALCULATED_ORDER_READY", 0),
            },
            "entry_distance": {
                "rows": len(entry_distance_rows),
                "entry_touched": sum(1 for row in entry_distance_rows if row["entry_touched"]),
                "not_touched": sum(1 for row in entry_distance_rows if not row["entry_touched"]),
                "min_abs_points": min(distances) if distances else None,
                "max_abs_points": max(distances) if distances else None,
                "average_abs_points": sum(distances) / len(distances) if distances else None,
            },
            "rupee_pnl_status": "NOT_CERTIFIED",
            "rupee_pnl_reason": "Historical Jan-2024 lot size/quantity is not certified in HSRE M5.",
            "candidate_summary_rows": len(candidate_rows),
            "report_files": {
                "daily_decisions": "daily_decisions.csv",
                "trades": "trades.csv",
                "non_trades": "non_trades.csv",
                "rejected_candidates_summary": "rejected_candidates_summary.csv",
                "entry_distance": "entry_distance.csv",
                "summary_json": "summary.json",
                "summary_md": "summary.md",
            },
            "hashes": hashes,
        }

    @staticmethod
    def _write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")

    @staticmethod
    def _write_text(path: Path, text: str) -> None:
        path.write_text(text, encoding="utf-8")

    @staticmethod
    def _hashes(output_path: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        for name in (
            "daily_decisions.csv",
            "trades.csv",
            "non_trades.csv",
            "rejected_candidates_summary.csv",
            "entry_distance.csv",
        ):
            path = output_path / name
            if path.exists():
                result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return result

    def _summary_markdown(self, summary: dict[str, Any]) -> str:
        funnel = summary["funnel"]
        metrics = summary["trade_metrics"]
        lines = [
            f"# HSRE S23 {self.period_label} End-to-End Run",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Observed trading days | {summary['date_coverage']['observed_trading_days']} |",
            f"| Final orders ready | {funnel['final_orders_ready']} |",
            f"| Entries triggered | {metrics['entries_triggered']} |",
            f"| Trigger rate | {_pct(metrics['trigger_rate'])} |",
            f"| Trades | {metrics['trades']} |",
            f"| Wins / Losses / Breakeven | {metrics['wins']} / {metrics['losses']} / {metrics['breakeven']} |",
            f"| Net point P&L | {metrics['net_total_points']} |",
            f"| Profit factor | {_display(metrics['profit_factor'])} |",
            f"| Max drawdown points | {metrics['max_drawdown_points']} |",
            f"| Rupee P&L | {summary['rupee_pnl_status']} |",
            "",
            "## Exit Distribution",
            "",
            json.dumps(summary["trade_metrics"]["exit_distribution"], indent=2, sort_keys=True),
            "",
            "## CE/PE Breakdown",
            "",
            json.dumps(summary["ce_pe_breakdown"], indent=2, sort_keys=True),
            "",
            "## ORPT/Recalculation",
            "",
            json.dumps(summary["orpt_recalculation"], indent=2, sort_keys=True),
            "",
            "## Entry Distance",
            "",
            json.dumps(summary["entry_distance"], indent=2, sort_keys=True),
            "",
            "## Hashes",
            "",
            json.dumps(summary["hashes"], indent=2, sort_keys=True),
            "",
        ]
        return "\n".join(lines)


def run_hsre_s23_january_2024(
    *,
    data_root: str | Path = r"D:\HistoricalData\Nifty",
    output_dir: str | Path = Path("reports") / "hsre" / "S23" / "2024-01",
) -> HsreS23MonthRunResult:
    runner = HsreS23January2024Runner(data_root=data_root)
    return runner.run(output_dir=output_dir)


def run_hsre_s23_date_range(
    *,
    start_date: date,
    end_date: date,
    period_label: str,
    data_root: str | Path = r"D:\HistoricalData\Nifty",
    output_dir: str | Path,
) -> HsreS23MonthRunResult:
    runner = HsreS23January2024Runner(
        data_root=data_root,
        start_date=start_date,
        end_date=end_date,
        period_label=period_label,
    )
    return runner.run(output_dir=output_dir)


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return ""
    if value is None:
        return ""
    return value


def _counts(values: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        key = str(value)
        result[key] = result.get(key, 0) + 1
    return dict(sorted(result.items()))


def _max_drawdown(equity_curve: list[float]) -> float:
    peak = 0.0
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        max_dd = max(max_dd, peak - value)
    return max_dd


def _display(value: Any) -> str:
    return "None" if value is None else str(value)


def _pct(value: float | None) -> str:
    if value is None:
        return "None"
    return f"{value:.2%}"
