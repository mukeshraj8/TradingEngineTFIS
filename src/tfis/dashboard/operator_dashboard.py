from __future__ import annotations

import html
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from tfis.domain.enums import ExpiryType, OptionType
from tfis.importers import load_strategy_rule
from tfis.market_data import UnderlyingHistoryBar
from tfis.paper import (
    DeterministicExpiryCalendar,
    EventEnvelope,
    OptionChainContract,
    OptionChainSnapshotEvent,
    PaperEventType,
    S23CollectedSnapshotInputs,
    S23LiveDecisionTimelineBuilder,
    S23PaperExpiryGovernance,
    S23PaperPreludeSessionContext,
    load_s23_decision_reference_packet,
)
from tfis.paper.models import UnderlyingQuoteEvent


_STAGE_SNAPSHOT_RE = re.compile(r"-(\d{4})-(\d{4}-\d{2}-\d{2})$")
_DAY_SESSION_RE = re.compile(r"-(\d{4}-\d{2}-\d{2})$")
_STAGE_LABELS = {
    "0916": "Opening Snapshot",
    "0925": "ORPT Snapshot",
    "0930": "RC Snapshot",
}
_STAGE_TIMES = {
    "0916": time(9, 16),
    "0925": time(9, 25),
    "0930": time(9, 30),
}
_STAGE_ORDER = {"0916": 1, "0925": 2, "0930": 3}


@dataclass(frozen=True, slots=True)
class StrategyDashboardConfig:
    strategy_code: str
    display_name: str
    artifact_root: Path
    strategy_path: Path
    reference_packet_path: Path
    session_id_prefix: str


@dataclass(frozen=True, slots=True)
class DashboardStageSummary:
    stage_key: str
    stage_name: str
    stage_time: str
    snapshot_status: str
    available_checkpoints: tuple[str, ...]
    monthly_status: str | None
    monthly_status_trigger: str | None
    monthly_status_reason: str | None
    monthly_status_price_used: float | None
    current_day_high_so_far: float | None
    current_day_low_so_far: float | None
    underlying_spot_value: float | None
    option_chain_contract_count: int | None
    option_chain_complete_oi: bool | None
    can_finalize_trade_decision: bool | None
    selected_contract_symbol: str | None
    planned_entry_price: float | None
    target_price: float | None
    stoploss_price: float | None
    decision_failure_code: str | None
    decision_failure_message: str | None
    formula_values: dict[str, Any]
    candidate_rows: tuple[dict[str, Any], ...]
    raw_artifact_links: dict[str, str]


@dataclass(frozen=True, slots=True)
class DashboardSessionSummary:
    session_date: date
    strategy_code: str
    display_name: str
    session_status: str
    session_directory: Path | None
    final_decision_status: str | None
    final_monthly_status: str | None
    final_selected_contract_symbol: str | None
    stages: tuple[DashboardStageSummary, ...]
    raw_artifact_links: dict[str, str]


@dataclass(frozen=True, slots=True)
class DashboardTradeLedgerRow:
    event_timestamp: datetime | None
    event_type: str
    trade_id: str
    strategy_id: str
    strategy_code: str
    strategy_branch: str
    selected_contract_symbol: str
    side: str
    lots: int | None
    quantity: int | None
    entry_price: float | None
    current_price: float | None
    current_bid: float | None
    current_ask: float | None
    exit_price: float | None
    target_price: float | None
    stoploss_price: float | None
    gross_points: float | None
    gross_pnl: float | None
    lifecycle_status: str
    manager_status: str
    reason_code: str
    message: str
    fresh_entry_required: bool
    reverse_entry_required: bool
    rollover_required: bool
    state_directory: Path | None
    raw_artifact_links: dict[str, str]


@dataclass(frozen=True, slots=True)
class DashboardBuildResult:
    output_root: Path
    index_html: Path
    manifest_json: Path
    strategy_pages: dict[str, Path]
    tool_pages: dict[str, Path]
    review_data_pages: dict[str, Path]


class TfisOperatorDashboardBuilder:
    def __init__(self, *, strategy_configs: tuple[StrategyDashboardConfig, ...]) -> None:
        self._strategy_configs = strategy_configs
        self._timeline_builder = S23LiveDecisionTimelineBuilder()
        self._repo_root = Path.cwd().resolve()

    def build(self, *, output_root: str | Path) -> DashboardBuildResult:
        target = Path(output_root)
        target.mkdir(parents=True, exist_ok=True)
        summaries = [self._collect_strategy_sessions(config) for config in self._strategy_configs]
        strategy_dir = target / "strategies"
        strategy_dir.mkdir(parents=True, exist_ok=True)
        strategy_pages: dict[str, Path] = {}
        for config, sessions in zip(self._strategy_configs, summaries, strict=False):
            page_dir = strategy_dir / config.strategy_code
            page_dir.mkdir(parents=True, exist_ok=True)
            page_path = page_dir / "index.html"
            page_path.write_text(
                self._render_strategy_page(
                    config=config,
                    sessions=sessions,
                    dashboard_root=target,
                    page_path=page_path,
                ),
                encoding="utf-8",
            )
            strategy_pages[config.strategy_code] = page_path

        review_data_pages = self._write_review_data_pages(target, summaries)
        tool_pages = self._write_tool_pages(target, review_data_pages=review_data_pages)

        index_html = target / "index.html"
        index_html.write_text(
            self._render_index_page(
                strategy_summaries=list(zip(self._strategy_configs, summaries, strict=False)),
                dashboard_root=target,
                index_path=index_html,
            ),
            encoding="utf-8",
        )
        manifest_json = target / "dashboard_manifest.json"
        manifest_json.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now().isoformat(),
                    "strategies": [
                        {
                            "strategy_code": config.strategy_code,
                            "display_name": config.display_name,
                            "artifact_root": str(config.artifact_root),
                            "page": str(Path("strategies") / config.strategy_code / "index.html"),
                            "sessions": [self._session_manifest_item(session) for session in sessions],
                        }
                        for config, sessions in zip(self._strategy_configs, summaries, strict=False)
                    ],
                    "tools": {
                        name: str(path.relative_to(target))
                        for name, path in sorted(tool_pages.items())
                    },
                    "review_data": {
                        name: str(path.relative_to(target))
                        for name, path in sorted(review_data_pages.items())
                    },
                },
                indent=2,
                sort_keys=True,
                default=str,
            ),
            encoding="utf-8",
        )
        return DashboardBuildResult(
            output_root=target,
            index_html=index_html,
            manifest_json=manifest_json,
            strategy_pages=strategy_pages,
            tool_pages=tool_pages,
            review_data_pages=review_data_pages,
        )

    def _write_tool_pages(
        self,
        output_root: Path,
        *,
        review_data_pages: dict[str, Path],
    ) -> dict[str, Path]:
        manual_dir = output_root / "tools" / "s23-manual-calculator"
        manual_dir.mkdir(parents=True, exist_ok=True)
        manual_path = manual_dir / "index.html"
        manual_path.write_text(
            self._render_s23_manual_calculator_page(),
            encoding="utf-8",
        )
        monthly_dir = output_root / "tools" / "monthly-status-calculator"
        monthly_dir.mkdir(parents=True, exist_ok=True)
        monthly_path = monthly_dir / "index.html"
        monthly_path.write_text(
            self._render_monthly_status_calculator_page(
                monthly_index_path=review_data_pages.get("monthly_status_index")
            ),
            encoding="utf-8",
        )
        return {
            "monthly_status_calculator": monthly_path,
            "s23_manual_calculator": manual_path,
        }

    def _write_review_data_pages(
        self,
        output_root: Path,
        summaries_by_strategy: list[list[DashboardSessionSummary]],
    ) -> dict[str, Path]:
        review_root = output_root / "data" / "review"
        monthly_root = review_root / "monthly-status"
        strategy_root = review_root / "strategies"
        monthly_root.mkdir(parents=True, exist_ok=True)
        strategy_root.mkdir(parents=True, exist_ok=True)
        written: dict[str, Path] = {}
        monthly_index: dict[str, str] = {}
        strategy_indexes: dict[str, dict[str, str]] = {}

        for sessions in summaries_by_strategy:
            for session in sessions:
                monthly_payload = self._build_monthly_status_review_payload(session)
                if monthly_payload is not None:
                    monthly_path = monthly_root / f"{session.session_date.isoformat()}.json"
                    monthly_path.write_text(
                        json.dumps(monthly_payload, indent=2, sort_keys=True, default=str),
                        encoding="utf-8",
                    )
                    monthly_index[session.session_date.isoformat()] = str(
                        monthly_path.relative_to(output_root).as_posix()
                    )
                    written[f"monthly_status_{session.session_date.isoformat()}"] = monthly_path

                strategy_payload = self._build_strategy_review_payload(session)
                if strategy_payload is not None:
                    strategy_dir = strategy_root / session.strategy_code
                    strategy_dir.mkdir(parents=True, exist_ok=True)
                    strategy_path = strategy_dir / f"{session.session_date.isoformat()}.json"
                    strategy_path.write_text(
                        json.dumps(strategy_payload, indent=2, sort_keys=True, default=str),
                        encoding="utf-8",
                    )
                    strategy_indexes.setdefault(session.strategy_code, {})[
                        session.session_date.isoformat()
                    ] = str(strategy_path.relative_to(output_root).as_posix())
                    written[
                        f"strategy_{session.strategy_code}_{session.session_date.isoformat()}"
                    ] = strategy_path

        monthly_index_path = monthly_root / "index.json"
        monthly_index_path.write_text(
            json.dumps(
                {
                    "artifact_version": 1,
                    "kind": "monthly_status_review_index",
                    "dates": monthly_index,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        written["monthly_status_index"] = monthly_index_path

        for strategy_code, date_map in strategy_indexes.items():
            index_path = strategy_root / strategy_code / "index.json"
            index_path.write_text(
                json.dumps(
                    {
                        "artifact_version": 1,
                        "kind": "strategy_review_index",
                        "strategy_code": strategy_code,
                        "dates": date_map,
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            written[f"strategy_{strategy_code}_index"] = index_path

        return written

    def _build_monthly_status_review_payload(
        self,
        session: DashboardSessionSummary,
    ) -> dict[str, Any] | None:
        for stage in reversed(session.stages):
            link = stage.raw_artifact_links.get("monthly_status_stage.json")
            if not link:
                continue
            path = Path(link)
            if not path.exists():
                continue
            payload = self._read_json(path)
            monthly = payload.get("monthly_status", {}) if isinstance(payload, dict) else {}
            trace = monthly.get("trace", []) if isinstance(monthly, dict) else []
            trace_item = None
            for item in trace:
                if isinstance(item, dict) and item.get("used_for_resolution"):
                    trace_item = item
                    break
            if trace_item is None and trace:
                trace_item = trace[0] if isinstance(trace[0], dict) else None
            levels = {
                key: trace_item.get(key) if isinstance(trace_item, dict) else None
                for key in ("PMH", "PML", "CMH", "CML", "PWH", "PWL", "CWH", "CWL", "current_price")
            }
            return {
                "artifact_version": 1,
                "kind": "monthly_status_review_data",
                "session_date": session.session_date.isoformat(),
                "symbol": "NIFTY" if session.strategy_code == "S23" else session.strategy_code,
                "instrument_group": "nifty" if session.strategy_code == "S23" else None,
                "price_source": "captured_strategy_snapshot",
                "strategy_code": session.strategy_code,
                "source_artifact": str(path),
                "monthly_status": {
                    "status": monthly.get("status"),
                    "trigger_name": monthly.get("trigger_name"),
                    "price_used": monthly.get("price_used"),
                    "resolution_reason": monthly.get("resolution_reason"),
                    "lookback_used": monthly.get("lookback_used"),
                    "notes": monthly.get("notes"),
                },
                "levels": levels,
                "trace": trace,
            }
        return None

    def _build_strategy_review_payload(
        self,
        session: DashboardSessionSummary,
    ) -> dict[str, Any] | None:
        for stage in reversed(session.stages):
            link = stage.raw_artifact_links.get("normalized_option_chain_snapshot.json")
            if not link:
                continue
            path = Path(link)
            if not path.exists():
                continue
            payload = self._read_json(path)
            body = payload.get("payload", payload) if isinstance(payload, dict) else {}
            contracts = body.get("contracts", []) if isinstance(body, dict) else []
            rows = []
            for item in contracts:
                if not isinstance(item, dict):
                    continue
                option_type = str(item.get("option_type") or "").upper()
                if option_type not in {"CE", "PE", "CALL", "PUT"}:
                    continue
                rows.append(
                    {
                        "symbol": item.get("symbol"),
                        "option_type": "CE" if option_type == "CALL" else "PE" if option_type == "PUT" else option_type,
                        "strike": item.get("strike"),
                        "expiry": item.get("expiry"),
                        "premium": item.get("ltp"),
                        "oi": item.get("oi"),
                        "bid": item.get("bid"),
                        "ask": item.get("ask"),
                        "volume": item.get("volume"),
                    }
                )
            return {
                "artifact_version": 1,
                "kind": "strategy_review_data",
                "strategy_code": session.strategy_code,
                "session_date": session.session_date.isoformat(),
                "source_artifact": str(path),
                "underlying_symbol": body.get("underlying_symbol"),
                "expiry": body.get("expiry"),
                "contracts": rows,
            }
        return None

    def _collect_strategy_sessions(
        self,
        config: StrategyDashboardConfig,
    ) -> list[DashboardSessionSummary]:
        if not config.artifact_root.exists():
            return []
        sessions: list[DashboardSessionSummary] = []
        for day_dir in sorted(
            [path for path in config.artifact_root.iterdir() if path.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.name)],
            reverse=True,
        ):
            sessions.append(self._build_session_summary(config=config, day_dir=day_dir))
        return sessions

    def _build_session_summary(
        self,
        *,
        config: StrategyDashboardConfig,
        day_dir: Path,
    ) -> DashboardSessionSummary:
        session_date = date.fromisoformat(day_dir.name)
        final_session_dir = self._find_final_session_dir(config=config, day_dir=day_dir)
        final_artifact_dir = self._resolve_final_artifact_dir(
            config=config,
            final_session_dir=final_session_dir,
        )
        stage_dirs = self._find_stage_dirs(config=config, day_dir=day_dir)
        session_complete = bool(
            final_session_dir is not None
            and (final_session_dir / "scheduled_run_metadata.json").exists()
        )
        final_summary_exists = bool(
            final_artifact_dir is not None
            and (final_artifact_dir / "trade_decision_summary.json").exists()
        )
        prefer_reconstruction = not session_complete or (
            session_complete and not final_summary_exists
        )
        stage_summaries = tuple(
            self._build_stage_summary(
                config=config,
                session_date=session_date,
                day_dir=day_dir,
                stage_dir=stage_dir,
                final_session_dir=final_artifact_dir,
                prefer_reconstruction=prefer_reconstruction,
            )
            for stage_dir in sorted(stage_dirs, key=lambda item: _STAGE_ORDER.get(self._extract_stage_key(item.name), 99))
        )
        final_summary = self._read_json(final_artifact_dir / "trade_decision_summary.json") if final_artifact_dir and (final_artifact_dir / "trade_decision_summary.json").exists() else None
        final_summary_view = final_summary.get("summary", final_summary) if isinstance(final_summary, dict) else None
        final_decision_status = final_summary_view.get("status") if isinstance(final_summary_view, dict) else None
        final_monthly_status = final_summary_view.get("monthly_status") if isinstance(final_summary_view, dict) else None
        final_selected_contract_symbol = final_summary_view.get("selected_contract_symbol") if isinstance(final_summary_view, dict) else None
        latest_stage = stage_summaries[-1] if stage_summaries else None
        if final_monthly_status is None and latest_stage is not None:
            final_monthly_status = latest_stage.monthly_status
        if final_selected_contract_symbol is None and latest_stage is not None:
            final_selected_contract_symbol = latest_stage.selected_contract_symbol
        latest_failure_code = latest_stage.decision_failure_code if latest_stage is not None else None
        if final_decision_status:
            session_status = final_decision_status
        elif (
            session_complete
            and latest_stage is not None
            and latest_stage.can_finalize_trade_decision
            and latest_stage.selected_contract_symbol
        ):
            session_status = "READY"
            final_decision_status = session_status
        elif session_complete and latest_stage is not None and latest_stage.can_finalize_trade_decision:
            session_status = "NO_GO" if latest_failure_code else "COMPLETE"
            final_decision_status = session_status
        elif stage_summaries:
            session_status = "IN_PROGRESS"
        else:
            session_status = "NO_DATA"
        raw_links: dict[str, str] = {}
        if final_session_dir is not None:
            for filename in ("trade_decision_summary.md", "trade_decision_explainer.md", "scheduled_run_metadata.json"):
                file_path = final_session_dir / filename
                if file_path.exists():
                    raw_links[filename] = str(file_path)
        if final_artifact_dir is not None and final_artifact_dir != final_session_dir:
            for filename in ("trade_decision_summary.md", "trade_decision_explainer.md"):
                file_path = final_artifact_dir / filename
                if file_path.exists():
                    raw_links[f"{final_artifact_dir.name}/{filename}"] = str(file_path)
        return DashboardSessionSummary(
            session_date=session_date,
            strategy_code=config.strategy_code,
            display_name=config.display_name,
            session_status=session_status,
            session_directory=final_session_dir,
            final_decision_status=final_decision_status,
            final_monthly_status=final_monthly_status,
            final_selected_contract_symbol=final_selected_contract_symbol,
            stages=stage_summaries,
            raw_artifact_links=raw_links,
        )

    def _build_stage_summary(
        self,
        *,
        config: StrategyDashboardConfig,
        session_date: date,
        day_dir: Path,
        stage_dir: Path,
        final_session_dir: Path | None,
        prefer_reconstruction: bool,
    ) -> DashboardStageSummary:
        stage_key = self._extract_stage_key(stage_dir.name)
        if stage_key is None:
            raise ValueError(f"Could not determine stage key from {stage_dir.name}")
        monthly_status_stage_json = (
            final_session_dir / f"monthly_status_stage_{stage_key}.json"
            if final_session_dir is not None
            else None
        )
        stage_explainer_json = (
            final_session_dir / f"trade_decision_explainer_stage_{stage_key}.json"
            if final_session_dir is not None
            else None
        )
        snapshot_summary = self._read_json(stage_dir / "snapshot_preflight_summary.json")
        option_chain_contract_count = snapshot_summary.get("option_chain_contract_count")
        option_chain_complete_oi = snapshot_summary.get("option_chain_has_complete_oi")
        strategy_rule = load_strategy_rule(config.strategy_path)

        if (
            not prefer_reconstruction
            and monthly_status_stage_json
            and monthly_status_stage_json.exists()
            and stage_explainer_json
            and stage_explainer_json.exists()
        ):
            monthly_status_payload = self._read_json(monthly_status_stage_json)
            stage_payload = self._read_json(stage_explainer_json)["stage"]
            decision_summary = stage_payload.get("decision_summary") or {}
            formula_values = self._formula_values(stage_payload)
            return DashboardStageSummary(
                stage_key=stage_key,
                stage_name=stage_payload["stage_name"],
                stage_time=stage_payload["stage_time"],
                snapshot_status=snapshot_summary.get("preflight_status", "READY"),
                available_checkpoints=tuple(stage_payload.get("available_checkpoint_labels", ())),
                monthly_status=monthly_status_payload["monthly_status"]["status"],
                monthly_status_trigger=monthly_status_payload["monthly_status"]["trigger_name"],
                monthly_status_reason=monthly_status_payload["monthly_status"]["resolution_reason"],
                monthly_status_price_used=monthly_status_payload["monthly_status"]["price_used"],
                current_day_high_so_far=stage_payload.get("current_day_high_so_far"),
                current_day_low_so_far=stage_payload.get("current_day_low_so_far"),
                underlying_spot_value=stage_payload.get("underlying_spot_value"),
                option_chain_contract_count=option_chain_contract_count,
                option_chain_complete_oi=option_chain_complete_oi,
                can_finalize_trade_decision=stage_payload.get("can_finalize_trade_decision"),
                selected_contract_symbol=decision_summary.get("selected_contract_symbol"),
                planned_entry_price=decision_summary.get("planned_entry_price"),
                target_price=decision_summary.get("target_price"),
                stoploss_price=decision_summary.get("stoploss_price"),
                decision_failure_code=stage_payload.get("decision_failure_code"),
                decision_failure_message=stage_payload.get("decision_failure_message"),
                formula_values=formula_values,
                candidate_rows=self._candidate_rows(
                    strategy_rule=strategy_rule,
                    stage_dir=stage_dir,
                    formula_values=formula_values,
                    selected_contract_symbol=decision_summary.get("selected_contract_symbol"),
                ),
                raw_artifact_links={
                    "snapshot_preflight_summary.json": str(stage_dir / "snapshot_preflight_summary.json"),
                    "normalized_underlying_bars.json": str(stage_dir / "normalized_underlying_bars.json"),
                    "normalized_option_chain_snapshot.json": str(stage_dir / "normalized_option_chain_snapshot.json"),
                    "monthly_status_stage.json": str(monthly_status_stage_json),
                    "trade_decision_explainer_stage.json": str(stage_explainer_json),
                },
            )

        stage = self._reconstruct_stage_from_snapshot_dir(
            config=config,
            session_date=session_date,
            stage_dir=stage_dir,
            stage_key=stage_key,
        )
        decision_summary = stage.decision_summary or {}
        stage_payload = {
            "provisional_formula_evaluation": list(stage.provisional_formula_evaluation),
            "decision_failure_code": stage.decision_failure_code,
            "decision_failure_message": stage.decision_failure_message,
        }
        formula_values = self._formula_values(stage_payload)
        return DashboardStageSummary(
            stage_key=stage_key,
            stage_name=stage.stage_name,
            stage_time=stage.stage_time,
            snapshot_status=snapshot_summary.get("preflight_status", "READY"),
            available_checkpoints=tuple(stage.available_checkpoint_labels),
            monthly_status=stage.monthly_status,
            monthly_status_trigger=stage.monthly_status_trigger,
            monthly_status_reason=stage.monthly_status_resolution_reason,
            monthly_status_price_used=stage.monthly_status_price_used,
            current_day_high_so_far=stage.current_day_high_so_far,
            current_day_low_so_far=stage.current_day_low_so_far,
            underlying_spot_value=stage.underlying_spot_value,
            option_chain_contract_count=option_chain_contract_count,
            option_chain_complete_oi=option_chain_complete_oi,
            can_finalize_trade_decision=stage.can_finalize_trade_decision,
            selected_contract_symbol=decision_summary.get("selected_contract_symbol"),
            planned_entry_price=decision_summary.get("planned_entry_price"),
            target_price=decision_summary.get("target_price"),
            stoploss_price=decision_summary.get("stoploss_price"),
            decision_failure_code=stage.decision_failure_code,
            decision_failure_message=stage.decision_failure_message,
            formula_values=formula_values,
            candidate_rows=self._candidate_rows(
                strategy_rule=strategy_rule,
                stage_dir=stage_dir,
                formula_values=formula_values,
                selected_contract_symbol=decision_summary.get("selected_contract_symbol"),
            ),
            raw_artifact_links={
                "snapshot_preflight_summary.json": str(stage_dir / "snapshot_preflight_summary.json"),
                "normalized_underlying_bars.json": str(stage_dir / "normalized_underlying_bars.json"),
                "normalized_option_chain_snapshot.json": str(stage_dir / "normalized_option_chain_snapshot.json"),
                **(
                    {
                        "monthly_status_stage.json": str(monthly_status_stage_json),
                    }
                    if monthly_status_stage_json is not None
                    and monthly_status_stage_json.exists()
                    else {}
                ),
            },
        )

    @staticmethod
    def _resolve_final_artifact_dir(
        *,
        config: StrategyDashboardConfig,
        final_session_dir: Path | None,
    ) -> Path | None:
        if final_session_dir is None:
            return None
        if (final_session_dir / "trade_decision_summary.json").exists():
            return final_session_dir
        try:
            strategy_rule = load_strategy_rule(config.strategy_path)
        except Exception:
            return final_session_dir
        branch_dir = final_session_dir / strategy_rule.unique_code
        if branch_dir.exists():
            return branch_dir
        return final_session_dir

    @staticmethod
    def _formula_values(stage_payload: dict[str, Any]) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for item in stage_payload.get("provisional_formula_evaluation", ()):
            if isinstance(item, dict) and item.get("name"):
                values[str(item["name"])] = {
                    "result": item.get("result"),
                    "formula": item.get("formula"),
                    "resolved_formula": item.get("resolved_formula"),
                }
        return values

    def _candidate_rows(
        self,
        *,
        strategy_rule: Any,
        stage_dir: Path,
        formula_values: dict[str, Any],
        selected_contract_symbol: str | None,
    ) -> tuple[dict[str, Any], ...]:
        start = self._formula_result(formula_values, "start_strike")
        end = self._formula_result(formula_values, "end_strike")
        minimum_premium = self._formula_result(formula_values, "minimum_premium")
        ideal_premium = self._formula_result(formula_values, "ideal_premium")
        if None in (start, end, minimum_premium):
            return ()
        chain_path = stage_dir / "normalized_option_chain_snapshot.json"
        if not chain_path.exists():
            return ()
        payload = self._read_json(chain_path)
        contracts = payload.get("payload", {}).get("contracts", [])
        lower = min(float(start), float(end))
        upper = max(float(start), float(end))
        option_type = strategy_rule.option_type.value if strategy_rule.option_type else ""
        rows: list[dict[str, Any]] = []
        for contract in contracts:
            if not isinstance(contract, dict):
                continue
            if str(contract.get("option_type")) != option_type:
                continue
            strike = contract.get("strike")
            if strike is None or not (lower <= float(strike) <= upper):
                continue
            premium = contract.get("ltp")
            oi = contract.get("oi")
            reasons: list[str] = []
            if premium is None or float(premium) < float(minimum_premium):
                reasons.append("premium below minimum")
            if oi is None or float(oi) < float(strategy_rule.minimum_oi):
                reasons.append("OI below minimum")
            rows.append(
                {
                    "symbol": contract.get("symbol"),
                    "strike": strike,
                    "option_type": option_type,
                    "premium": premium,
                    "oi": oi,
                    "premium_distance": (
                        abs(float(premium) - float(ideal_premium))
                        if premium is not None and ideal_premium is not None
                        else None
                    ),
                    "status": (
                        "SELECTED"
                        if selected_contract_symbol and contract.get("symbol") == selected_contract_symbol
                        else "PASS"
                        if not reasons
                        else "REJECTED"
                    ),
                    "reason": ", ".join(reasons) if reasons else "qualified",
                }
            )
        rows.sort(
            key=lambda item: (
                0 if item["status"] == "SELECTED" else 1 if item["status"] == "PASS" else 2,
                item["premium_distance"] if item["premium_distance"] is not None else 999999,
                item["strike"] if item["strike"] is not None else 999999,
            )
        )
        return tuple(rows[:12])

    @staticmethod
    def _formula_result(formula_values: dict[str, Any], name: str) -> float | None:
        item = formula_values.get(name)
        if not isinstance(item, dict) or item.get("result") is None:
            return None
        return float(item["result"])

    def _reconstruct_stage_from_snapshot_dir(
        self,
        *,
        config: StrategyDashboardConfig,
        session_date: date,
        stage_dir: Path,
        stage_key: str,
    ) -> Any:
        strategy_rule = load_strategy_rule(config.strategy_path)
        reference_packet = load_s23_decision_reference_packet(config.reference_packet_path)
        collected_inputs = self._load_snapshot_inputs(stage_dir=stage_dir, strategy_rule=strategy_rule)
        stage_build = self._timeline_builder.build_stage(
            stage_name=_STAGE_LABELS[stage_key],
            stage_time=_STAGE_TIMES[stage_key],
            strategy_rule=strategy_rule,
            reference_packet=reference_packet,
            collected_inputs=collected_inputs,
            allow_branch_pinned_unknown_monthly_status=True,
        )
        return stage_build.stage

    def _load_snapshot_inputs(self, *, stage_dir: Path, strategy_rule: Any) -> S23CollectedSnapshotInputs:
        quote_payload = self._read_json(stage_dir / "normalized_underlying_snapshot.json")
        bars_payload = self._read_json(stage_dir / "normalized_underlying_bars.json")
        daily_payload = self._read_json(stage_dir / "normalized_underlying_daily_bars.json")
        chain_payload = self._read_json(stage_dir / "normalized_option_chain_snapshot.json")
        session_date = date.fromisoformat(quote_payload["session_date"])
        timezone = quote_payload["timezone"]
        quote = UnderlyingQuoteEvent(
            envelope=EventEnvelope(
                event_type=PaperEventType.UNDERLYING_QUOTE,
                session_date=session_date,
                effective_timestamp=datetime.fromisoformat(quote_payload["effective_timestamp"]),
                captured_at=datetime.fromisoformat(quote_payload["captured_at"]),
                timezone=timezone,
                source_type=quote_payload["source_type"],
                source_id=quote_payload["source_id"],
                synthetic_fixture=quote_payload["synthetic_fixture"],
                normalized_by=quote_payload["normalized_by"],
                source_sequence=quote_payload.get("source_sequence"),
                data_quality_flags=tuple(quote_payload.get("data_quality_flags", [])),
            ),
            symbol=quote_payload["payload"]["symbol"],
            ltp=float(quote_payload["payload"]["ltp"]),
            bid=quote_payload["payload"].get("bid"),
            ask=quote_payload["payload"].get("ask"),
            volume=quote_payload["payload"].get("volume"),
        )
        intraday_bars = tuple(self._to_underlying_bar(item) for item in bars_payload["bars"])
        daily_bars = tuple(self._to_underlying_bar(item) for item in daily_payload["bars"])
        contracts = tuple(
            OptionChainContract(
                symbol=item["symbol"],
                option_type=OptionType(item["option_type"]),
                strike=float(item["strike"]),
                expiry=date.fromisoformat(item["expiry"]),
                bid=float(item["bid"]) if item["bid"] is not None else None,
                ask=float(item["ask"]) if item["ask"] is not None else None,
                ltp=float(item["ltp"]) if item["ltp"] is not None else None,
                oi=float(item["oi"]) if item["oi"] is not None else None,
                volume=float(item["volume"]) if item["volume"] is not None else None,
            )
            for item in chain_payload["payload"]["contracts"]
        )
        weekly_expiry = date.fromisoformat(chain_payload["payload"]["expiry"])
        option_chain = OptionChainSnapshotEvent(
            envelope=EventEnvelope(
                event_type=PaperEventType.OPTION_CHAIN_SNAPSHOT,
                session_date=session_date,
                effective_timestamp=datetime.fromisoformat(chain_payload["effective_timestamp"]),
                captured_at=datetime.fromisoformat(chain_payload["captured_at"]),
                timezone=chain_payload["timezone"],
                source_type=chain_payload["source_type"],
                source_id=chain_payload["source_id"],
                synthetic_fixture=chain_payload["synthetic_fixture"],
                normalized_by=chain_payload["normalized_by"],
                source_sequence=chain_payload.get("source_sequence"),
                data_quality_flags=tuple(chain_payload.get("data_quality_flags", [])),
            ),
            underlying_symbol=chain_payload["payload"]["underlying_symbol"],
            expiry=weekly_expiry,
            contracts=contracts,
        )
        return S23CollectedSnapshotInputs(
            session_context=S23PaperPreludeSessionContext(
                session_date=session_date,
                timezone=timezone,
                generated_at=datetime.fromisoformat(quote_payload["captured_at"]),
            ),
            strategy_rule=strategy_rule,
            underlying_quote=quote,
            underlying_bars=intraday_bars,
            daily_bars=daily_bars,
            option_chain_snapshot=option_chain,
            expiry_governance=S23PaperExpiryGovernance(
                DeterministicExpiryCalendar(
                    explicit_expiries={(ExpiryType.WEEKLY, session_date): weekly_expiry}
                )
            ),
            weekly_expiry=weekly_expiry,
        )

    @staticmethod
    def _to_underlying_bar(item: dict[str, Any]) -> UnderlyingHistoryBar:
        return UnderlyingHistoryBar(
            symbol=item["symbol"],
            bar_start=datetime.fromisoformat(item["bar_start"]),
            bar_end=datetime.fromisoformat(item["bar_end"]),
            open=float(item["open"]),
            high=float(item["high"]),
            low=float(item["low"]),
            close=float(item["close"]),
            volume=float(item["volume"]) if item.get("volume") is not None else None,
            source_id=item.get("source_id"),
        )

    @staticmethod
    def _find_final_session_dir(*, config: StrategyDashboardConfig, day_dir: Path) -> Path | None:
        for child in day_dir.iterdir():
            if not child.is_dir():
                continue
            if child.name == f"{config.session_id_prefix}-{day_dir.name}":
                return child
        return None

    @staticmethod
    def _find_stage_dirs(*, config: StrategyDashboardConfig, day_dir: Path) -> list[Path]:
        results: list[Path] = []
        for child in day_dir.iterdir():
            if not child.is_dir():
                continue
            if (
                child.name.startswith(config.session_id_prefix)
                and _STAGE_SNAPSHOT_RE.search(child.name)
                and (child / "snapshot_preflight_summary.json").exists()
            ):
                results.append(child)
        return results

    @staticmethod
    def _extract_stage_key(name: str) -> str | None:
        match = _STAGE_SNAPSHOT_RE.search(name)
        if not match:
            return None
        return match.group(1)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _render_index_page(
        self,
        *,
        strategy_summaries: list[tuple[StrategyDashboardConfig, list[DashboardSessionSummary]]],
        dashboard_root: Path,
        index_path: Path,
    ) -> str:
        cards: list[str] = []
        for config, sessions in strategy_summaries:
            latest = sessions[0] if sessions else None
            href = os.path.relpath(
                dashboard_root / "strategies" / config.strategy_code / "index.html",
                start=index_path.parent,
            ).replace("\\", "/")
            cards.append(
                "\n".join(
                    [
                        '<a class="strategy-card" href="{}">'.format(html.escape(href)),
                        f"<div class=\"eyebrow\">Strategy {html.escape(config.strategy_code)}</div>",
                        f"<h2>{html.escape(config.display_name)}</h2>",
                        f"<div class=\"metric-row\"><span>Latest Session</span><strong>{html.escape(latest.session_date.isoformat() if latest else 'none')}</strong></div>",
                        f"<div class=\"metric-row\"><span>Status</span>{self._badge(latest.session_status if latest else 'NO_DATA')}</div>",
                        f"<div class=\"metric-row\"><span>Final Monthly Status</span>{self._badge(latest.final_monthly_status or 'n/a') if latest else self._badge('n/a')}</div>",
                        "</a>",
                    ]
                )
            )
        return self._render_page(
            title="TFIS Operator Dashboard",
            body="\n".join(
                [
                    "<header class=\"hero\">",
                    "<div class=\"eyebrow\">Operator View</div>",
                    "<h1>TFIS Operator Dashboard</h1>",
                    "<p>Read-only, artifact-backed strategy pages for morning decision visibility across strategies and sessions.</p>",
                    '<div class="tool-strip"><a class="tool-link" href="tools/monthly-status-calculator/index.html">Monthly Status Calculator</a><a class="tool-link" href="tools/s23-manual-calculator/index.html">Manual S23 Calculator</a></div>',
                    "</header>",
                    "<section class=\"grid\">",
                    *(cards if cards else ["<p>No strategy data found.</p>"]),
                    "</section>",
                ]
            ),
        )

    def _render_strategy_page(
        self,
        *,
        config: StrategyDashboardConfig,
        sessions: list[DashboardSessionSummary],
        dashboard_root: Path,
        page_path: Path,
    ) -> str:
        latest = sessions[0] if sessions else None
        trade_rows = self._collect_trade_ledger_rows(
            config,
            latest_session_date=latest.session_date if latest else None,
        )
        latest_block = (
            self._render_latest_session_block(
                config=config,
                latest=latest,
                trade_rows=trade_rows,
                page_path=page_path,
            )
            if latest
            else "<p>No session artifacts found yet.</p>"
        )
        trades_block = self._render_trade_ledger_section(
            rows=trade_rows,
            page_path=page_path,
            latest_session_date=latest.session_date if latest else None,
        )
        history_rows = "\n".join(self._render_session_history_row(session, page_path=page_path) for session in sessions) or "<tr><td colspan=\"5\">No sessions found.</td></tr>"
        body = "\n".join(
            [
                '<nav><a href="../../index.html">Back to strategy index</a></nav>',
                "<header class=\"hero\">",
                f"<div class=\"eyebrow\">Strategy {html.escape(config.strategy_code)}</div>",
                f"<h1>{html.escape(config.display_name)}</h1>",
                f"<p>Operator page for {html.escape(config.strategy_code)}. Each stage is rendered from TFIS artifacts and reconstructed stage logic when stage-level explainers are not yet available.</p>",
                '<div class="tool-strip"><a class="tool-link" href="../../tools/monthly-status-calculator/index.html">Monthly Status Calculator</a><a class="tool-link" href="../../tools/s23-manual-calculator/index.html">Manual S23 Calculator</a></div>',
                "</header>",
                "<section>",
                "<h2>Latest Session</h2>",
                latest_block,
                "</section>",
                "<section>",
                "<h2>Trades Taken</h2>",
                trades_block,
                "</section>",
                "<section>",
                "<h2>Session History</h2>",
                "<table><thead><tr><th>Date</th><th>Status</th><th>Monthly Status</th><th>Contract</th><th>Artifacts</th></tr></thead><tbody>",
                history_rows,
                "</tbody></table>",
                "</section>",
                self._dashboard_refresh_script(),
            ]
        )
        return self._render_page(title=config.display_name, body=body)

    @staticmethod
    def _dashboard_refresh_script() -> str:
        return """
<script>
(function(){
  var storageKey = "tfis-dashboard-open-details:" + window.location.pathname;
  function detailsKey(details, index) {
    var summary = details.querySelector("summary");
    var label = summary ? summary.textContent.replace(/\\s+/g, " ").trim() : "";
    return details.className + "|" + label + "|" + index;
  }
  function readState() {
    try {
      return JSON.parse(sessionStorage.getItem(storageKey) || "{}");
    } catch (error) {
      return {};
    }
  }
  function writeState(state) {
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(state));
    } catch (error) {
      // Ignore private-mode or storage quota errors; auto-refresh still works.
    }
  }
  var state = readState();
  document.querySelectorAll("details").forEach(function(details, index) {
    var key = detailsKey(details, index);
    if (Object.prototype.hasOwnProperty.call(state, key)) {
      details.open = !!state[key];
    }
    details.addEventListener("toggle", function() {
      var nextState = readState();
      nextState[key] = details.open;
      writeState(nextState);
    });
  });
  setTimeout(function(){ window.location.reload(); }, 10000);
})();
</script>"""

    def _collect_trade_ledger_rows(
        self,
        config: StrategyDashboardConfig,
        *,
        latest_session_date: date | None = None,
    ) -> list[DashboardTradeLedgerRow]:
        candidate_paths: set[Path] = set()
        if config.artifact_root.exists():
            candidate_paths.update(config.artifact_root.rglob("paper_trade_ledger.jsonl"))
        global_ledger = self._repo_root / "tmp" / "paper_trade_ledger" / f"{config.strategy_code.lower()}_paper_trade_ledger.jsonl"
        if global_ledger.exists():
            candidate_paths.add(global_ledger)

        rows: list[DashboardTradeLedgerRow] = []
        seen: set[tuple[str, str, str, str, str]] = set()
        for ledger_path in sorted(candidate_paths):
            for raw in self._iter_jsonl_dicts(ledger_path):
                strategy_code = str(raw.get("strategy_code") or "")
                if strategy_code and strategy_code.upper() != config.strategy_code.upper():
                    continue
                event_timestamp_raw = str(raw.get("event_timestamp") or "")
                event_type = str(raw.get("event_type") or "n/a")
                trade_id = str(raw.get("trade_id") or raw.get("selected_contract_symbol") or "n/a")
                manager_status = str(raw.get("manager_status") or "n/a")
                reason_code = str(raw.get("reason_code") or "n/a")
                state_directory = self._path_or_none(raw.get("state_directory"))
                if state_directory is not None and not (state_directory / "paper_position_state.json").exists():
                    continue
                if state_directory is not None and not self._is_relative_to(
                    state_directory,
                    config.artifact_root,
                ):
                    continue
                identity = (
                    trade_id,
                    event_timestamp_raw,
                    event_type,
                    manager_status,
                    reason_code,
                )
                if identity in seen:
                    continue
                seen.add(identity)
                rows.append(
                    DashboardTradeLedgerRow(
                        event_timestamp=self._parse_datetime(event_timestamp_raw),
                        event_type=event_type,
                        trade_id=trade_id,
                        strategy_id=str(raw.get("strategy_id") or "n/a"),
                        strategy_code=str(raw.get("strategy_code") or config.strategy_code),
                        strategy_branch=str(raw.get("strategy_branch") or "n/a"),
                        selected_contract_symbol=str(raw.get("selected_contract_symbol") or "n/a"),
                        side=str(raw.get("side") or "n/a"),
                        lots=self._int_or_none(raw.get("lots")),
                        quantity=self._int_or_none(raw.get("quantity")),
                        entry_price=self._float_or_none(raw.get("entry_price")),
                        current_price=self._float_or_none(raw.get("current_price")),
                        current_bid=self._float_or_none(raw.get("current_bid")),
                        current_ask=self._float_or_none(raw.get("current_ask")),
                        exit_price=self._float_or_none(raw.get("exit_price")),
                        target_price=self._float_or_none(raw.get("target_price")),
                        stoploss_price=self._float_or_none(raw.get("stoploss_price")),
                        gross_points=self._float_or_none(raw.get("gross_points")),
                        gross_pnl=self._float_or_none(raw.get("gross_pnl")),
                        lifecycle_status=str(raw.get("lifecycle_status") or "n/a"),
                        manager_status=manager_status,
                        reason_code=reason_code,
                        message=str(raw.get("message") or ""),
                        fresh_entry_required=bool(raw.get("fresh_entry_required")),
                        reverse_entry_required=bool(raw.get("reverse_entry_required")),
                        rollover_required=bool(raw.get("rollover_required")),
                        state_directory=state_directory,
                        raw_artifact_links=self._trade_artifact_links(
                            ledger_path=ledger_path,
                            state_directory=state_directory,
                        ),
                    )
                )
        if config.artifact_root.exists():
            for order_path in sorted(config.artifact_root.rglob("paper_order_state.json")):
                try:
                    raw = self._read_json(order_path)
                except (OSError, json.JSONDecodeError):
                    continue
                status = str(raw.get("status") or "")
                if status != "PAPER_ORDER_WAITING_FOR_TRIGGER":
                    continue
                entry_date = self._parse_date(raw.get("entry_date"))
                if latest_session_date is not None and entry_date != latest_session_date:
                    continue
                state_directory = order_path.parent
                if not self._is_relative_to(state_directory, config.artifact_root):
                    continue
                strategy_code = str(raw.get("strategy_code") or config.strategy_code)
                if strategy_code.upper() != config.strategy_code.upper():
                    continue
                order_timestamp = str(raw.get("last_updated_timestamp") or raw.get("order_timestamp") or "")
                selected_contract = str(raw.get("selected_contract_symbol") or "n/a")
                strategy_branch = str(raw.get("strategy_branch") or "n/a")
                trade_id = (
                    f"{strategy_code}-{strategy_branch}-{selected_contract}-"
                    f"ORDER-{str(raw.get('order_timestamp') or order_timestamp).replace(':', '').replace('-', '')}"
                )
                identity = (
                    trade_id,
                    order_timestamp,
                    "ORDER_WAITING",
                    status,
                    str(raw.get("last_reason_code") or "paper_order_waiting_for_entry_trigger"),
                )
                if identity in seen:
                    continue
                seen.add(identity)
                rows.append(
                    DashboardTradeLedgerRow(
                        event_timestamp=self._parse_datetime(order_timestamp),
                        event_type="ORDER_WAITING",
                        trade_id=trade_id,
                        strategy_id=f"{strategy_code}:{strategy_branch}",
                        strategy_code=strategy_code,
                        strategy_branch=strategy_branch,
                        selected_contract_symbol=selected_contract,
                        side=str(raw.get("order_side") or "SELL"),
                        lots=self._int_or_none(raw.get("lots")),
                        quantity=self._int_or_none(raw.get("quantity")),
                        entry_price=self._float_or_none(raw.get("planned_entry_price")),
                        current_price=self._float_or_none(raw.get("last_market_price")),
                        current_bid=self._float_or_none(raw.get("last_market_bid")),
                        current_ask=self._float_or_none(raw.get("last_market_ask")),
                        exit_price=None,
                        target_price=self._float_or_none(raw.get("target_price")),
                        stoploss_price=self._float_or_none(raw.get("stoploss_price")),
                        gross_points=None,
                        gross_pnl=None,
                        lifecycle_status=(
                            "ORDER_NOT_FILLED"
                            if status == "PAPER_ORDER_NOT_FILLED"
                            else "ORDER_WAITING_FOR_TRIGGER"
                        ),
                        manager_status=status,
                        reason_code=str(raw.get("last_reason_code") or "paper_order_waiting_for_entry_trigger"),
                        message=str(raw.get("last_message") or "Waiting for selected option premium to reach entry."),
                        fresh_entry_required=False,
                        reverse_entry_required=False,
                        rollover_required=False,
                        state_directory=state_directory,
                        raw_artifact_links=self._trade_artifact_links(
                            ledger_path=None,
                            state_directory=state_directory,
                        ),
                    )
                )
        return sorted(
            rows,
            key=lambda item: item.event_timestamp.isoformat() if item.event_timestamp else "",
            reverse=True,
        )

    def _render_trade_ledger_section(
        self,
        *,
        rows: list[DashboardTradeLedgerRow],
        page_path: Path,
        latest_session_date: date | None = None,
    ) -> str:
        if latest_session_date is not None:
            rows = [
                row
                for row in rows
                if row.event_type != "ORDER_WAITING"
                or (
                    row.event_timestamp is not None
                    and row.event_timestamp.date() == latest_session_date
                )
            ]
        if not rows:
            return '<div class="empty-panel">No paper trades have been recorded yet.</div>'

        grouped_rows: dict[str, list[DashboardTradeLedgerRow]] = {}
        for row in rows:
            grouped_rows.setdefault(row.trade_id, []).append(row)
        latest_by_trade = {
            trade_id: self._display_row_for_trade(trade_rows)
            for trade_id, trade_rows in grouped_rows.items()
        }
        latest_rows = sorted(
            (
                row
                for row in latest_by_trade.values()
                if self._trade_visible_for_latest_session(
                    row,
                    latest_session_date=latest_session_date,
                )
            ),
            key=lambda item: item.event_timestamp.isoformat() if item.event_timestamp else "",
            reverse=True,
        )
        if not latest_rows:
            return '<div class="empty-panel">No active paper orders or positions for the latest session.</div>'
        open_count = sum(
            1
            for row in latest_rows
            if "OPEN" in row.lifecycle_status.upper()
            or row.manager_status.upper() in {"PAPER_POSITION_OPENED", "PAPER_POSITION_HELD"}
        )
        action_required_count = sum(1 for row in latest_rows if self._trade_action_required(row))
        closed_count = sum(1 for row in latest_rows if "CLOSED" in row.lifecycle_status.upper() or row.event_type.upper() == "CLOSE")
        header = "\n".join(
            [
                '<div class="session-summary summary-shell trade-summary">',
                '<div class="summary-grid">',
                self._summary_metric("Unique Trades", str(len(latest_rows))),
                self._summary_metric("Open Positions", str(open_count)),
                self._summary_metric("Action Required", str(action_required_count)),
                self._summary_metric("Closed Trades", str(closed_count)),
                "</div>",
                "</div>",
            ]
        )
        event_rows = "\n".join(
            self._render_trade_ledger_row(row, page_path=page_path) for row in latest_rows[:80]
        )
        return "\n".join(
            [
                header,
                '<table class="trade-table">',
                "<thead><tr><th class=\"trade-time\">Time</th><th class=\"trade-event\">Event</th><th class=\"trade-strategy\">Strategy</th><th class=\"trade-contract\">Contract</th><th class=\"trade-side\">Side / Qty</th><th class=\"trade-number\">Entry</th><th class=\"trade-number\">Current</th><th class=\"trade-number\">Exit</th><th class=\"trade-number\">Target / SL</th><th class=\"trade-number\">P&L</th><th class=\"trade-status\">Status</th><th class=\"trade-manage\">Manage</th></tr></thead>",
                f"<tbody>{event_rows}</tbody>",
                "</table>",
            ]
        )

    def _display_row_for_trade(self, rows: list[DashboardTradeLedgerRow]) -> DashboardTradeLedgerRow:
        terminal_rows = [row for row in rows if self._trade_terminal(row)]
        if terminal_rows:
            return max(
                terminal_rows,
                key=lambda item: item.event_timestamp.isoformat() if item.event_timestamp else "",
            )
        return max(
            rows,
            key=lambda item: item.event_timestamp.isoformat() if item.event_timestamp else "",
        )

    @staticmethod
    def _trade_terminal(row: DashboardTradeLedgerRow) -> bool:
        event_type = row.event_type.upper()
        lifecycle_status = row.lifecycle_status.upper()
        manager_status = row.manager_status.upper()
        return (
            event_type == "CLOSE"
            or "CLOSED" in lifecycle_status
            or manager_status
            in {
                "PAPER_POSITION_TARGET_HIT",
                "PAPER_POSITION_STOPLOSS_HIT",
                "PAPER_POSITION_FORCE_CLOSED",
                "PAPER_POSITION_ALREADY_CLOSED",
            }
        )

    def _trade_visible_for_latest_session(
        self,
        row: DashboardTradeLedgerRow,
        *,
        latest_session_date: date | None,
    ) -> bool:
        if latest_session_date is None or row.event_timestamp is None:
            return True
        if row.event_timestamp.date() == latest_session_date:
            return True
        if self._trade_terminal(row):
            return False
        return self._trade_open(row) or self._trade_action_required(row)

    @staticmethod
    def _trade_open(row: DashboardTradeLedgerRow) -> bool:
        return (
            "OPEN" in row.lifecycle_status.upper()
            or row.manager_status.upper() in {"PAPER_POSITION_OPENED", "PAPER_POSITION_HELD"}
        )

    def _render_trade_ledger_row(self, row: DashboardTradeLedgerRow, *, page_path: Path) -> str:
        event_time = row.event_timestamp.isoformat(sep=" ", timespec="seconds") if row.event_timestamp else "n/a"
        action_flags = []
        if row.fresh_entry_required:
            action_flags.append("Fresh Entry")
        if row.reverse_entry_required:
            action_flags.append("Reverse Entry")
        if row.rollover_required:
            action_flags.append("Rollover")
        action_text = ", ".join(action_flags)
        status_labels = []
        for label in (row.lifecycle_status, row.manager_status):
            normalized = self._normalize_trade_status_label(label)
            if normalized and normalized not in status_labels:
                status_labels.append(normalized)
        status_parts = [self._badge(label) for label in status_labels]
        if action_text:
            status_parts.append(self._badge(action_text))
        reason = html.escape(row.reason_code)
        if row.message:
            reason = f"{reason}<br><span class=\"muted-text\">{html.escape(row.message)}</span>"
        return "\n".join(
            [
                "<tr>",
                f"<td class=\"trade-time\">{html.escape(event_time)}</td>",
                f"<td class=\"trade-event\">{self._badge(row.event_type)}</td>",
                f"<td class=\"trade-strategy\"><strong>{html.escape(row.strategy_id)}</strong><br><span class=\"muted-text code-text\">{html.escape(row.strategy_branch)}</span></td>",
                f"<td class=\"trade-contract\"><strong>{html.escape(row.selected_contract_symbol)}</strong><br><span class=\"muted-text code-text\">{html.escape(row.trade_id)}</span></td>",
                f"<td class=\"trade-side\"><strong>{html.escape(row.side)}</strong><br>{self._fmt_number(row.lots, integer=True)} lots / {self._fmt_number(row.quantity, integer=True)}</td>",
                f"<td class=\"trade-number\">{self._fmt_number(row.entry_price)}</td>",
                f"<td class=\"trade-number\">{self._fmt_number(row.current_price)}<br><span class=\"muted-text\">{self._fmt_number(row.current_bid)} / {self._fmt_number(row.current_ask)}</span></td>",
                f"<td class=\"trade-number\">{self._fmt_number(row.exit_price)}</td>",
                f"<td class=\"trade-number\">{self._fmt_number(row.target_price)}<br><span class=\"muted-text\">/ {self._fmt_number(row.stoploss_price)}</span></td>",
                f"<td class=\"trade-number\">{self._fmt_number(row.gross_points)} pts<br><span class=\"muted-text\">{self._fmt_number(row.gross_pnl)}</span></td>",
                f"<td class=\"trade-status\"><div class=\"status-badges\">{' '.join(status_parts)}</div><div class=\"trade-reason\">{reason}</div></td>",
                f"<td class=\"trade-manage\"><div class=\"artifact-links trade-links\">{self._render_links(row.raw_artifact_links, page_path=page_path)}</div></td>",
                "</tr>",
            ]
        )

    def _render_latest_session_block(
        self,
        *,
        config: StrategyDashboardConfig,
        latest: DashboardSessionSummary,
        trade_rows: list[DashboardTradeLedgerRow],
        page_path: Path,
    ) -> str:
        stage_cards = "\n".join(self._render_stage_card(stage, page_path=page_path) for stage in latest.stages)
        artifact_links = self._render_links(latest.raw_artifact_links, page_path=page_path)
        final_contracts = self._final_contract_display(latest=latest, trade_rows=trade_rows)
        return "\n".join(
            [
                '<div class="session-summary summary-shell">',
                '<div class="summary-grid">',
                self._summary_metric("Session Date", latest.session_date.isoformat()),
                self._summary_metric("Run Status", self._badge(latest.session_status)),
                self._summary_metric("Final Monthly Status", self._badge(latest.final_monthly_status or "n/a")),
                self._summary_metric("Final Contract", final_contracts),
                self._summary_metric("Stage Coverage", " / ".join(stage.stage_time for stage in latest.stages) or "n/a"),
                self._summary_metric("Stage Count", str(len(latest.stages))),
                "</div>",
                f"<div class=\"artifact-links top-links\">{artifact_links}</div>",
                "</div>",
                self._render_final_leg_panel(config=config, latest=latest),
                self._render_final_explanation_panel(config=config, latest=latest),
                "<div class=\"stage-grid\">",
                stage_cards or "<p>No stage artifacts found.</p>",
                "</div>",
            ]
        )

    def _render_final_leg_panel(self, *, config: StrategyDashboardConfig, latest: DashboardSessionSummary) -> str:
        legs = self._session_final_leg_rows(config=config, session=latest)
        if not legs:
            return ""
        rows = "\n".join(
            "".join(
                [
                    "<tr>",
                    f"<td class=\"text-cell code-cell\">{html.escape(str(item['branch']))}</td>",
                    f"<td class=\"text-cell contract-cell\"><strong>{html.escape(str(item.get('contract') or 'No contract selected'))}</strong></td>",
                    f"<td class=\"text-cell side-cell\">{html.escape(str(item['side']))}</td>",
                    f"<td class=\"number-cell\">{self._fmt_number(item['strike'])}</td>",
                    f"<td class=\"number-cell\">{self._fmt_number(item['premium'])}</td>",
                    f"<td class=\"number-cell\">{self._fmt_number(item['oi'], integer=True)}</td>",
                    f"<td class=\"number-cell\">{self._fmt_number(item['entry'])}</td>",
                    f"<td class=\"number-cell\">{self._fmt_number(item['target'])}</td>",
                    f"<td class=\"number-cell\">{self._fmt_number(item['stoploss'])}</td>",
                    f"<td class=\"status-cell\">{self._badge(self._normalize_trade_status_label(str(item['order_status'] or 'n/a')) or 'n/a')}</td>",
                    "</tr>",
                ]
            )
            for item in legs
        )
        return "\n".join(
            [
                '<div class="session-summary summary-shell final-leg-panel">',
                '<div class="section-heading"><h3>Final S23 Leg Decisions</h3><span>Final CE/PE decisions from the 09:30 run</span></div>',
                '<table class="candidate-table final-leg-table">',
                "<thead><tr><th class=\"text-cell\">Branch</th><th class=\"text-cell\">Contract</th><th class=\"text-cell\">Side</th><th class=\"number-cell\">Strike</th><th class=\"number-cell\">Premium</th><th class=\"number-cell\">OI</th><th class=\"number-cell\">Entry</th><th class=\"number-cell\">Target</th><th class=\"number-cell\">SL</th><th class=\"status-cell\">Order Status</th></tr></thead>",
                f"<tbody>{rows}</tbody>",
                "</table>",
                "</div>",
            ]
        )

    def _render_final_explanation_panel(self, *, config: StrategyDashboardConfig, latest: DashboardSessionSummary) -> str:
        legs = self._session_final_leg_rows(config=config, session=latest)
        if not legs:
            return ""
        monthly = legs[0].get("monthly") if legs else {}
        monthly_block = ""
        if isinstance(monthly, dict) and monthly:
            status_text = str(monthly.get("status") or "n/a")
            if status_text.upper().startswith("BULL"):
                group_text = "bullish S23 group, so TFIS evaluates Bull Call Sell and Bull Put Sell independently"
            elif status_text.upper().startswith("BEAR"):
                group_text = "bearish S23 group, so TFIS evaluates Bear Call Sell and Bear Put Sell independently"
            else:
                group_text = "no valid S23 trading group because monthly status is not resolved"
            monthly_block = "\n".join(
                [
                    '<div class="focus-panel">',
                    '<ol class="explanation-list">',
                    f"<li><strong>Step 1 - Preparation.</strong> Session date is {html.escape(latest.session_date.isoformat())}; final decision uses the completed 09:30 RC snapshot.</li>",
                    f"<li><strong>Step 2 - Monthly status.</strong> Status is {html.escape(status_text)} via {html.escape(str(monthly.get('trigger_name') or 'n/a'))}. Current price used was {self._fmt_number(monthly.get('current_price'))}. {html.escape(str(monthly.get('resolution_reason') or ''))}</li>",
                    f"<li><strong>Step 3 - Rule group.</strong> {html.escape(status_text)} maps to the {html.escape(group_text)}.</li>",
                    "</ol>",
                    "</div>",
                ]
            )
        else:
            status_text = latest.final_monthly_status or "n/a"
            if str(status_text).upper().startswith("BULL"):
                group_text = "bullish S23 group, so TFIS evaluates Bull Call Sell and Bull Put Sell independently"
            elif str(status_text).upper().startswith("BEAR"):
                group_text = "bearish S23 group, so TFIS evaluates Bear Call Sell and Bear Put Sell independently"
            else:
                group_text = "no valid S23 trading group because monthly status is not resolved"
            monthly_block = "\n".join(
                [
                    '<div class="focus-panel">',
                    '<ol class="explanation-list">',
                    f"<li><strong>Step 1 - Preparation.</strong> Session date is {html.escape(latest.session_date.isoformat())}; final decision uses the completed 09:30 RC snapshot when available.</li>",
                    f"<li><strong>Step 2 - Monthly status.</strong> Status is {html.escape(str(status_text))}. Detailed monthly trace was not present in this summary artifact.</li>",
                    f"<li><strong>Step 3 - Rule group.</strong> {html.escape(str(status_text))} maps to the {html.escape(group_text)}.</li>",
                    "</ol>",
                    "</div>",
                ]
            )
        leg_blocks = "\n".join(self._render_leg_explanation_card(leg) for leg in legs)
        return "\n".join(
            [
                '<details class="session-summary summary-shell explanation-panel">',
                '<summary class="explanation-summary"><span>Calculation Explanation</span><small>Expand dry-run steps</small></summary>',
                monthly_block,
                '<div class="leg-explanation-grid">',
                leg_blocks,
                "</div>",
                "</details>",
            ]
        )

    def _render_leg_explanation_card(self, leg: dict[str, Any]) -> str:
        formula_rows = ""
        formulas = leg.get("formula_evaluation")
        if isinstance(formulas, list):
            formula_rows = "\n".join(
                "".join(
                    [
                        "<tr>",
                        f"<td>{html.escape(str(item.get('name') or 'n/a'))}</td>",
                        f"<td>{html.escape(str(item.get('resolved_formula') or item.get('formula') or 'n/a'))}</td>",
                        f"<td>{self._fmt_number(item.get('result'))}</td>",
                        "</tr>",
                    ]
                )
                for item in formulas
                if isinstance(item, dict)
            )
        formula_table = (
            "\n".join(
                [
                    '<table class="candidate-table explanation-table">',
                    "<thead><tr><th>Calculated Item</th><th>Resolved Formula</th><th>Result</th></tr></thead>",
                    f"<tbody>{formula_rows}</tbody>",
                    "</table>",
                ]
            )
            if formula_rows
            else "<p>No formula trace found.</p>"
        )
        eligible_table = self._render_eligible_strike_comparison_table(leg)
        rejected = leg.get("rejected_counts")
        rejected_text = "n/a"
        if isinstance(rejected, dict) and rejected:
            rejected_text = ", ".join(
                f"{str(key).replace('_', ' ')}: {self._fmt_number(value, integer=True)}"
                for key, value in sorted(rejected.items())
            )
        ranked = leg.get("ranked_candidates")
        ranked_text = "n/a"
        if isinstance(ranked, list) and ranked:
            first = ranked[0]
            if isinstance(first, dict):
                ranked_text = (
                    f"Rank 1: {first.get('symbol', 'n/a')} at strike {self._fmt_number(first.get('strike'))}, "
                    f"premium {self._fmt_number(first.get('premium'))}, OI {self._fmt_number(first.get('oi'), integer=True)}, "
                    f"distance from ideal {self._fmt_number(first.get('premium_distance'))}."
                )
        dry_run_steps = self._s23_leg_dry_run_steps(leg)
        contract_label = str(leg.get("contract") or "No contract selected")
        final_decision_text = leg.get("final_decision_text")
        if not final_decision_text:
            final_decision_text = ranked_text
        return "\n".join(
            [
                '<article class="leg-explanation-card">',
                f"<h3>{html.escape(str(leg['side']))}: {html.escape(contract_label)}</h3>",
                '<ol class="explanation-list">',
                *(f"<li>{step}</li>" for step in dry_run_steps),
                f"<li><strong>Search outcome.</strong> {html.escape(str(leg.get('selection_reason') or 'n/a'))} Rejections checked before selection: {html.escape(rejected_text)}.</li>",
                f"<li><strong>Final decision.</strong> {html.escape(str(final_decision_text))}</li>",
                "</ol>",
                eligible_table,
                formula_table,
                "</article>",
            ]
        )

    def _render_eligible_strike_comparison_table(self, leg: dict[str, Any]) -> str:
        candidates = leg.get("contract_candidates")
        if not isinstance(candidates, list):
            candidates = []
        rows: list[dict[str, Any]] = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "").upper()
            if status not in {"SELECTED", "PASSED", "PASS"}:
                continue
            rows.append(item)
        if not rows:
            ranked = leg.get("ranked_candidates")
            if isinstance(ranked, list):
                rows = [item for item in ranked if isinstance(item, dict)]
        if not rows:
            return ""
        rows = self._sort_s23_candidate_rows_in_search_order(leg, rows)
        search_note = self._s23_candidate_search_note(leg, rows)
        full_scan = self._render_s23_full_strike_scan(leg)
        body = "\n".join(
            "".join(
                [
                    "<tr>",
                    f"<td class=\"number-cell\">{self._fmt_number(item.get('strike'))}</td>",
                    f"<td class=\"text-cell contract-cell\"><strong>{html.escape(str(item.get('symbol') or 'n/a'))}</strong></td>",
                    f"<td class=\"number-cell\">{self._fmt_number(item.get('ltp', item.get('premium')))}</td>",
                    f"<td class=\"number-cell\">{self._fmt_number(item.get('oi'), integer=True)}</td>",
                    f"<td class=\"number-cell\">{self._fmt_number(item.get('premium_distance_to_ideal', item.get('premium_distance')))}</td>",
                    f"<td class=\"status-cell\">{self._badge(str(item.get('status') or ('RANK_' + str(item.get('rank_position') or ''))))}</td>",
                    "</tr>",
                ]
            )
            for item in rows
        )
        return "\n".join(
            [
                '<div class="eligible-strike-panel">',
                "<h4>Eligible Strike OI Comparison</h4>",
                f'<p class="table-help">{html.escape(search_note)}</p>',
                '<table class="candidate-table eligible-strike-table">',
                "<thead><tr><th class=\"number-cell\">Strike</th><th class=\"text-cell\">Contract</th><th class=\"number-cell\">Premium</th><th class=\"number-cell\">OI</th><th class=\"number-cell\">Distance From Ideal</th><th class=\"status-cell\">Status</th></tr></thead>",
                f"<tbody>{body}</tbody>",
                "</table>",
                full_scan,
                "</div>",
            ]
        )

    def _render_s23_full_strike_scan(self, leg: dict[str, Any]) -> str:
        candidates = leg.get("contract_candidates")
        if not isinstance(candidates, list) or not candidates:
            return (
                '<details class="full-scan-panel">'
                '<summary>Full strike scan audit</summary>'
                '<p class="table-help">Full strike scan rows were not persisted for this run.</p>'
                "</details>"
            )
        expected_side = self._s23_expected_option_suffix(leg)
        visible_candidates = [
            item
            for item in candidates
            if isinstance(item, dict)
            and (
                expected_side is None
                or self._s23_candidate_option_suffix(item) in {None, expected_side}
            )
        ]
        rows = self._sort_s23_candidate_rows_in_search_order(leg, visible_candidates)
        if not rows:
            return ""
        formula_text = self._s23_scan_formula_text(leg)
        body = "\n".join(
            "".join(
                [
                    "<tr>",
                    f"<td class=\"number-cell\">{self._fmt_number(item.get('strike'))}</td>",
                    f"<td class=\"text-cell contract-cell\"><strong>{html.escape(str(item.get('symbol') or 'n/a'))}</strong></td>",
                    f"<td class=\"number-cell\">{self._fmt_number(item.get('ltp', item.get('premium')))}</td>",
                    f"<td class=\"number-cell\">{self._fmt_number(item.get('oi'), integer=True)}</td>",
                    f"<td class=\"number-cell\">{self._fmt_number(item.get('premium_distance_to_ideal', item.get('premium_distance')))}</td>",
                    f"<td class=\"status-cell\">{self._badge(str(item.get('status') or 'n/a'))}</td>",
                    f"<td class=\"text-cell reason-cell\">{html.escape(self._s23_candidate_reason(leg, item))}</td>",
                    "</tr>",
                ]
            )
            for item in rows
        )
        return "\n".join(
            [
                '<details class="full-scan-panel">',
                '<summary>Full strike scan audit</summary>',
                f'<p class="table-help">{html.escape(formula_text)} Showing {html.escape(expected_side or "leg-side")} candidates only.</p>',
                '<div class="full-scan-table-wrap">',
                '<table class="candidate-table eligible-strike-table full-scan-table">',
                "<thead><tr><th class=\"number-cell\">Strike</th><th class=\"text-cell\">Contract</th><th class=\"number-cell\">Premium</th><th class=\"number-cell\">OI</th><th class=\"number-cell\">Distance From Ideal</th><th class=\"status-cell\">Status</th><th class=\"text-cell\">Reason</th></tr></thead>",
                f"<tbody>{body}</tbody>",
                "</table>",
                "</div>",
                "</details>",
            ]
        )

    def _s23_scan_formula_text(self, leg: dict[str, Any]) -> str:
        start = self._s23_formula_numeric_result(leg, "start_strike")
        end = self._s23_formula_numeric_result(leg, "end_strike")
        ideal = self._s23_formula_numeric_result(leg, "ideal_premium")
        minimum = self._s23_formula_numeric_result(leg, "minimum_premium")
        parts: list[str] = []
        if start is not None and end is not None:
            direction = "down" if start > end else "up"
            parts.append(f"Strike scan: {self._fmt_number(start)} {direction} to {self._fmt_number(end)}")
        else:
            parts.append("Strike scan: persisted candidate order inferred from available rows")
        if ideal is not None:
            parts.append(f"ideal premium {self._fmt_number(ideal)}")
        if minimum is not None:
            parts.append(f"minimum premium {self._fmt_number(minimum)}")
        return "; ".join(parts) + "."

    def _s23_candidate_reason(self, leg: dict[str, Any], item: dict[str, Any]) -> str:
        for key in (
            "reason",
            "rejection_reason",
            "failure_reason",
            "selection_reason",
            "message",
        ):
            value = item.get(key)
            if value not in (None, ""):
                return str(value)
        status = str(item.get("status") or "").upper()
        if status in {"SELECTED", "PASSED", "PASS"}:
            return self._s23_candidate_qualification_reason(leg, item, status)
        derived_reasons = self._derive_s23_candidate_reasons(leg, item)
        return ", ".join(derived_reasons) if derived_reasons else "not qualified; detailed rejection reason was not persisted"

    def _s23_candidate_qualification_reason(
        self,
        leg: dict[str, Any],
        item: dict[str, Any],
        status: str,
    ) -> str:
        parts: list[str] = []
        expected_side = self._s23_expected_option_suffix(leg)
        actual_side = self._s23_candidate_option_suffix(item)
        if expected_side:
            side_text = f"side {actual_side or 'n/a'} matches {expected_side}"
            parts.append(side_text if actual_side == expected_side else f"side check unavailable for {expected_side}")

        strike = self._float_or_none(item.get("strike"))
        start = self._s23_formula_numeric_result(leg, "start_strike")
        end = self._s23_formula_numeric_result(leg, "end_strike")
        if strike is not None and start is not None and end is not None:
            parts.append(
                f"strike {self._fmt_number(strike)} inside range "
                f"{self._fmt_number(start)} to {self._fmt_number(end)}"
            )

        premium = self._float_or_none(item.get("ltp", item.get("premium")))
        minimum_premium = (
            self._s23_formula_numeric_result(leg, "minimum_premium")
            or self._float_or_none(leg.get("minimum_premium"))
        )
        ideal_premium = (
            self._s23_formula_numeric_result(leg, "ideal_premium")
            or self._float_or_none(leg.get("ideal_premium"))
        )
        if premium is not None:
            if minimum_premium is not None:
                premium_part = (
                    f"premium {self._fmt_number(premium)} >= minimum "
                    f"{self._fmt_number(minimum_premium)}"
                )
            else:
                premium_part = f"premium {self._fmt_number(premium)} present"
            if ideal_premium is not None:
                comparator = ">=" if premium >= ideal_premium else "<"
                premium_part += f" and {comparator} ideal {self._fmt_number(ideal_premium)}"
            parts.append(premium_part)

        oi = self._float_or_none(item.get("oi"))
        minimum_oi = self._float_or_none(leg.get("minimum_oi"))
        if oi is not None:
            if minimum_oi is not None:
                parts.append(
                    f"OI {self._fmt_number(oi, integer=True)} >= minimum "
                    f"{self._fmt_number(minimum_oi, integer=True)}"
                )
            else:
                parts.append(f"OI {self._fmt_number(oi, integer=True)} present")

        if not parts:
            return "passed persisted qualification checks; detailed threshold values were not persisted"
        prefix = "selected because" if status == "SELECTED" else "passed audit because"
        suffix = ""
        if status != "SELECTED" and premium is not None and ideal_premium is not None and premium < ideal_premium:
            suffix = "; not selected because premium is below the ideal premium"
        elif status != "SELECTED":
            suffix = "; not selected because another strike was first in rule-sheet search order"
        return f"{prefix} " + "; ".join(parts) + suffix

    def _derive_s23_candidate_reasons(
        self,
        leg: dict[str, Any],
        item: dict[str, Any],
    ) -> list[str]:
        reasons: list[str] = []
        expected_side = self._s23_expected_option_suffix(leg)
        actual_side = self._s23_candidate_option_suffix(item)
        if expected_side and actual_side and actual_side != expected_side:
            reasons.append(f"option side mismatch; expected {expected_side}, got {actual_side}")

        strike = self._float_or_none(item.get("strike"))
        start = self._s23_formula_numeric_result(leg, "start_strike")
        end = self._s23_formula_numeric_result(leg, "end_strike")
        if strike is not None and start is not None and end is not None:
            lower = min(start, end)
            upper = max(start, end)
            if strike < lower or strike > upper:
                reasons.append(
                    f"strike outside range {self._fmt_number(start)} to {self._fmt_number(end)}"
                )

        premium = self._float_or_none(item.get("ltp", item.get("premium")))
        minimum_premium = (
            self._s23_formula_numeric_result(leg, "minimum_premium")
            or self._float_or_none(leg.get("minimum_premium"))
        )
        ideal_premium = (
            self._s23_formula_numeric_result(leg, "ideal_premium")
            or self._float_or_none(leg.get("ideal_premium"))
        )
        if premium is None:
            reasons.append("premium missing")
        else:
            if minimum_premium is not None and premium < minimum_premium:
                reasons.append(
                    f"premium {self._fmt_number(premium)} below minimum {self._fmt_number(minimum_premium)}"
                )
            elif ideal_premium is not None and premium < ideal_premium:
                reasons.append(
                    f"premium {self._fmt_number(premium)} below ideal {self._fmt_number(ideal_premium)}"
                )

        oi = self._float_or_none(item.get("oi"))
        minimum_oi = self._float_or_none(leg.get("minimum_oi"))
        if oi is None:
            reasons.append("OI missing")
        elif minimum_oi is not None and oi < minimum_oi:
            reasons.append(
                f"OI {self._fmt_number(oi, integer=True)} below minimum {self._fmt_number(minimum_oi, integer=True)}"
            )
        return reasons

    @staticmethod
    def _s23_expected_option_suffix(leg: dict[str, Any]) -> str | None:
        branch = str(leg.get("branch") or "").upper()
        side = str(leg.get("side") or "").upper()
        option_type = str(leg.get("option_type") or leg.get("selected_contract_option_type") or "").upper()
        combined = f"{branch} {side} {option_type}"
        if "PUT" in combined or " PE" in f" {combined} " or combined.endswith("PE"):
            return "PE"
        if "CALL" in combined or " CE" in f" {combined} " or combined.endswith("CE"):
            return "CE"
        return None

    @staticmethod
    def _s23_candidate_option_suffix(item: dict[str, Any]) -> str | None:
        option_type = str(item.get("option_type") or "").upper()
        if option_type in {"CE", "CALL"}:
            return "CE"
        if option_type in {"PE", "PUT"}:
            return "PE"
        symbol = str(item.get("symbol") or "").upper()
        if symbol.endswith("_CE") or symbol.endswith("-CE"):
            return "CE"
        if symbol.endswith("_PE") or symbol.endswith("-PE"):
            return "PE"
        return None

    def _sort_s23_candidate_rows_in_search_order(
        self,
        leg: dict[str, Any],
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        start = self._s23_formula_numeric_result(leg, "start_strike")
        end = self._s23_formula_numeric_result(leg, "end_strike")
        reverse = False
        if start is not None and end is not None:
            reverse = start > end
        else:
            reverse = self._infer_s23_candidate_search_descending(leg, rows)
        return sorted(
            rows,
            key=lambda item: self._float_or_default(item.get("strike"), 0.0),
            reverse=reverse,
        )

    def _s23_candidate_search_note(self, leg: dict[str, Any], rows: list[dict[str, Any]]) -> str:
        start = self._s23_formula_numeric_result(leg, "start_strike")
        end = self._s23_formula_numeric_result(leg, "end_strike")
        selected = next(
            (
                item
                for item in rows
                if str(item.get("status") or "").upper() == "SELECTED"
            ),
            None,
        )
        if start is not None and end is not None:
            direction = "down" if start > end else "up"
            range_text = (
                f"Displayed in rule-sheet search order: "
                f"{self._fmt_number(start)} {direction} to {self._fmt_number(end)}."
            )
        else:
            range_text = "Displayed in inferred rule-sheet search order from the persisted candidates."
        if selected is None:
            return f"{range_text} No final strike was selected from these rows."
        return (
            f"{range_text} Final strike is {self._fmt_number(selected.get('strike'))} "
            f"({selected.get('symbol', 'n/a')}) because it is the first candidate in that search order "
            "that satisfies the final premium/OI/side rules. PASSED rows are audit candidates; "
            "SELECTED is the row used for the order."
        )

    def _s23_formula_numeric_result(self, leg: dict[str, Any], name: str) -> float | None:
        for key in ("formula_evaluation", "provisional_formula_evaluation"):
            formulas = leg.get(key)
            if not isinstance(formulas, list):
                continue
            for item in formulas:
                if isinstance(item, dict) and item.get("name") == name:
                    return self._float_or_none(item.get("result"))
        return None

    def _infer_s23_candidate_search_descending(
        self,
        leg: dict[str, Any],
        rows: list[dict[str, Any]],
    ) -> bool:
        branch = str(leg.get("branch") or "").upper()
        side = str(leg.get("side") or "").upper()
        if "CALL" in branch or " CE" in f" {side} " or side.endswith("CE"):
            return True
        if "PUT" in branch or " PE" in f" {side} " or side.endswith("PE"):
            return False
        strikes = [self._float_or_default(item.get("strike"), 0.0) for item in rows]
        return len(strikes) >= 2 and strikes[0] > strikes[-1]

    def _s23_leg_dry_run_steps(self, leg: dict[str, Any]) -> list[str]:
        formula_by_name: dict[str, dict[str, Any]] = {}
        formulas = leg.get("formula_evaluation")
        if isinstance(formulas, list):
            for item in formulas:
                if isinstance(item, dict) and item.get("name"):
                    formula_by_name[str(item["name"])] = item
        side = str(leg.get("side") or "")
        branch = str(leg.get("branch") or "")
        is_pe = "PE" in side or "PUT" in branch.upper()
        start = formula_by_name.get("start_strike", {})
        end = formula_by_name.get("end_strike", {})
        ideal = formula_by_name.get("ideal_premium", {})
        minimum = formula_by_name.get("minimum_premium", {})
        entry = formula_by_name.get("entry", {})
        target = formula_by_name.get("target", {})
        stoploss = formula_by_name.get("stoploss", {})
        spot_alias = self._spot_reference_alias_for_s23_leg(leg)
        spot_alias_label = self._s23_spot_alias_label(spot_alias)
        spot_ref_value = self._s23_reference_value(leg.get("market_refs"), spot_alias)
        monthly_status = self._s23_leg_monthly_status(leg)
        strike_step = self._s23_strike_step_from_formula(end) or 50.0
        direction_text = (
            "For PE selling, TFIS starts below the spot reference using the 5% buffer, then searches upward toward the reference."
            if is_pe
            else "For CE selling, TFIS starts above the spot reference using the 5% buffer, then searches downward toward the reference."
        )
        search_text = (
            f"from {self._fmt_number(leg.get('start_strike'))} up to {self._fmt_number(leg.get('end_strike'))}"
            if is_pe
            else f"from {self._fmt_number(leg.get('start_strike'))} down to {self._fmt_number(leg.get('end_strike'))}"
        )
        attempted_expiries = self._s23_attempted_expiries_text(leg)
        expiry_search_text = (
            f" It attempted expiry search in this order: {html.escape(attempted_expiries)}."
            if attempted_expiries
            else " Attempted-expiry details were not persisted for this run."
        )
        entry_status = self._normalize_trade_status_label(str(leg.get("order_status") or "n/a")) or "n/a"
        if leg.get("contract"):
            step_8 = (
                f"<strong>Step 8 - Select final strike.</strong> The selected contract is {html.escape(str(leg.get('contract') or 'n/a'))}: "
                f"strike {self._fmt_number(leg.get('strike'))}, premium {self._fmt_number(leg.get('premium'))}, "
                f"OI {self._fmt_number(leg.get('oi'), integer=True)}."
            )
            step_9 = (
                f"<strong>Step 9 - Calculate trade levels.</strong> Entry uses <code>{html.escape(str(entry.get('resolved_formula') or 'n/a'))}</code> = {self._fmt_number(leg.get('entry'))}; "
                f"target uses <code>{html.escape(str(target.get('resolved_formula') or 'n/a'))}</code> = {self._fmt_number(leg.get('target'))}; "
                f"SL uses <code>{html.escape(str(stoploss.get('resolved_formula') or 'n/a'))}</code> = {self._fmt_number(leg.get('stoploss'))}. "
                f"Order status is {html.escape(entry_status)}."
            )
        else:
            failure_code = str(leg.get("order_status") or "NO_ORDER")
            failure_message = str(leg.get("selection_reason") or "No final contract selected.")
            step_8 = (
                f"<strong>Step 8 - Select final strike.</strong> No final {html.escape(side)} contract was selected. "
                f"Reason: {html.escape(failure_code)} - {html.escape(failure_message)}"
            )
            step_9 = (
                f"<strong>Step 9 - Trade levels.</strong> No final trade levels apply because no contract qualified. "
                "For formula audit only, the provisional entry/target/SL values were "
                f"{self._fmt_number(leg.get('provisional_entry'))} / {self._fmt_number(leg.get('provisional_target'))} / "
                f"{self._fmt_number(leg.get('provisional_stoploss'))}; "
                "these are not actionable order levels and no paper order was created."
            )
        return [
            (
                f"<strong>Step 3 - Collect NIFTY spot data.</strong> Monthly status is {html.escape(monthly_status)}, "
                f"so this {html.escape(side)} rule needs <strong>{html.escape(spot_alias_label)}</strong>. "
                f"Captured {html.escape(spot_alias)} = {self._fmt_number(spot_ref_value)}."
            ),
            (
                f"<strong>Step 4 - Check strike factor.</strong> NIFTY option strike factor is {self._fmt_number(strike_step, integer=True)}. "
                f"TFIS rounds the spot reference to this strike grid before calculating start and end strikes."
            ),
            (
                f"<strong>Step 5a - Decide the strike range.</strong> {html.escape(direction_text)} "
                f"The rule produced start strike {self._fmt_number(leg.get('start_strike'))} using "
                f"<code>{html.escape(str(start.get('resolved_formula') or 'n/a'))}</code> and end strike "
                f"{self._fmt_number(leg.get('end_strike'))} using <code>{html.escape(str(end.get('resolved_formula') or 'n/a'))}</code>."
            ),
            (
                f"<strong>Step 6 - Calculate premium and OI filters.</strong> Ideal premium is {html.escape(spot_alias_label)} * 1.20%: "
                f"<code>{html.escape(str(ideal.get('resolved_formula') or 'n/a'))}</code> = {self._fmt_number(leg.get('ideal_premium'))}. "
                f"Minimum acceptable premium is {html.escape(spot_alias_label)} * 0.90%: "
                f"<code>{html.escape(str(minimum.get('resolved_formula') or 'n/a'))}</code> = {self._fmt_number(leg.get('minimum_premium'))}. "
                f"Minimum OI is {self._fmt_number(leg.get('minimum_oi'), integer=True)} contracts."
            ),
            (
                f"<strong>Step 7 - Search eligible strikes.</strong> TFIS scans the option chain "
                f"{search_text}. "
                f"A strike must have enough OI, meet the premium rule, and be the correct option side."
                f"{expiry_search_text}"
            ),
            step_8,
            step_9,
        ]

    def _spot_reference_alias_for_s23_leg(self, leg: dict[str, Any]) -> str:
        aliases = leg.get("required_market_aliases")
        if isinstance(aliases, list) and aliases:
            return str(aliases[0])
        branch = str(leg.get("branch") or "").upper()
        side = str(leg.get("side") or "").upper()
        monthly = self._s23_leg_monthly_status(leg).upper()
        if monthly.startswith("BEAR") and ("CALL" in branch or "CE" in side):
            return "PRV_2DLL"
        if monthly.startswith("BEAR") and ("PUT" in branch or "PE" in side):
            return "PRV_3DHH"
        if monthly.startswith("BULL") and ("CALL" in branch or "CE" in side):
            return "PRV_3DLL"
        if monthly.startswith("BULL") and ("PUT" in branch or "PE" in side):
            return "PRV_2DHH"
        return "spot reference"

    @staticmethod
    def _s23_spot_alias_label(alias: str) -> str:
        cleaned = str(alias or "").replace("PRV_", "")
        mapping = {
            "2DLL": "2DLL of NIFTY spot",
            "2DHH": "2DHH of NIFTY spot",
            "3DLL": "3DLL of NIFTY spot",
            "3DHH": "3DHH of NIFTY spot",
        }
        return mapping.get(cleaned, cleaned or "NIFTY spot reference")

    def _s23_reference_value(self, refs: Any, alias: str) -> float | None:
        if not isinstance(refs, dict):
            return None
        raw = refs.get(alias)
        if isinstance(raw, dict):
            return self._float_or_none(raw.get("value"))
        return self._float_or_none(raw)

    def _s23_leg_monthly_status(self, leg: dict[str, Any]) -> str:
        monthly = leg.get("monthly")
        if isinstance(monthly, dict) and monthly.get("status"):
            return str(monthly["status"])
        return "n/a"

    @staticmethod
    def _s23_attempted_expiries_text(leg: dict[str, Any]) -> str:
        attempted = leg.get("attempted_expiries")
        if isinstance(attempted, tuple | list):
            values = [str(item) for item in attempted if str(item).strip()]
            if values:
                if len(values) == 1:
                    return f"near expiry {values[0]} only"
                return "near expiry " + values[0] + "; fallback expiry " + "; fallback expiry ".join(values[1:])
        return ""

    def _s23_strike_step_from_formula(self, formula: dict[str, Any]) -> float | None:
        text = str(formula.get("resolved_formula") or "")
        match = re.search(r"([+-])\s*(\d+(?:\.\d+)?)\s*$", text)
        if not match:
            return None
        return self._float_or_none(match.group(2))

    def _session_final_leg_rows(
        self,
        *,
        config: StrategyDashboardConfig,
        session: DashboardSessionSummary,
    ) -> tuple[dict[str, Any], ...]:
        session_dir = session.session_directory
        if session_dir is None or not session_dir.exists():
            return ()
        rows: list[dict[str, Any]] = []
        selected_branches: set[str] = set()
        for summary_path in sorted(session_dir.rglob("trade_decision_summary.json")):
            try:
                raw_summary = self._read_json(summary_path)
            except (OSError, json.JSONDecodeError):
                continue
            summary = raw_summary.get("summary", raw_summary) if isinstance(raw_summary, dict) else {}
            if not isinstance(summary, dict):
                continue
            contract = str(summary.get("selected_contract_symbol") or "")
            if not contract or contract == "n/a":
                continue
            explanation = raw_summary.get("explanation", {}) if isinstance(raw_summary, dict) else {}
            if not isinstance(explanation, dict):
                explanation = {}
            request = explanation.get("contract_selection_request", {})
            if not isinstance(request, dict):
                request = {}
            thresholds = explanation.get("contract_selection_thresholds", {})
            if not isinstance(thresholds, dict):
                thresholds = {}
            order_status = None
            order_path = summary_path.parent / "paper_order_state.json"
            if order_path.exists():
                try:
                    raw_order = self._read_json(order_path)
                except (OSError, json.JSONDecodeError):
                    raw_order = {}
                if isinstance(raw_order, dict):
                    order_status = raw_order.get("status")
            option_type = str(summary.get("selected_contract_option_type") or "").upper()
            side = "SELL PE" if option_type in {"PE", "PUT"} else "SELL CE" if option_type in {"CE", "CALL"} else "SELL"
            branch = str(summary.get("strategy_branch") or summary_path.parent.name)
            selected_branches.add(self._normalize_s23_branch_name(branch))
            rows.append(
                {
                    "branch": branch,
                    "contract": contract,
                    "side": side,
                    "strike": self._float_or_none(summary.get("selected_contract_strike")),
                    "premium": self._float_or_none(summary.get("selected_contract_ltp")),
                    "oi": self._float_or_none(summary.get("selected_contract_oi")),
                    "entry": self._float_or_none(summary.get("planned_entry_price")),
                    "target": self._float_or_none(summary.get("target_price")),
                    "stoploss": self._float_or_none(summary.get("stoploss_price")),
                    "order_status": order_status or summary.get("status"),
                    "start_strike": self._float_or_none(request.get("start_strike")),
                    "end_strike": self._float_or_none(request.get("end_strike")),
                    "ideal_premium": self._float_or_none(request.get("ideal_premium")),
                    "minimum_premium": self._float_or_none(request.get("minimum_premium")),
                    "minimum_oi": self._float_or_none(thresholds.get("minimum_oi")),
                    "selection_reason": summary.get("contract_selection_reason"),
                    "attempted_expiries": summary.get("contract_selection_attempted_expiries"),
                    "required_market_aliases": summary.get("required_market_aliases"),
                    "ranked_candidates": summary.get("ranked_candidates"),
                    "rejected_counts": summary.get("rejected_candidate_counts"),
                    "contract_candidates": explanation.get("contract_candidates"),
                    "formula_evaluation": explanation.get("formula_evaluation"),
                    "market_refs": explanation.get("market_reference_values"),
                    "option_refs": explanation.get("option_reference_values"),
                    "monthly": explanation.get("monthly_status"),
                }
            )
        rows.extend(
            self._session_failed_leg_rows(
                config=config,
                session=session,
                selected_branches=selected_branches,
            )
        )
        return tuple(rows)

    def _session_failed_leg_rows(
        self,
        *,
        config: StrategyDashboardConfig,
        session: DashboardSessionSummary,
        selected_branches: set[str],
    ) -> list[dict[str, Any]]:
        session_dir = session.session_directory
        if session_dir is None or not session_dir.exists():
            return []
        stage_dir = self._session_final_stage_dir(config=config, session=session)
        rows: list[dict[str, Any]] = []
        for explainer_path in sorted(session_dir.glob("*/trade_decision_explainer.json")):
            branch = explainer_path.parent.name
            normalized_branch = self._normalize_s23_branch_name(branch)
            if normalized_branch in selected_branches:
                continue
            try:
                payload = self._read_json(explainer_path)
            except (OSError, json.JSONDecodeError):
                continue
            stage = self._finalized_explainer_stage(payload)
            if not stage:
                continue
            effective_monthly_status = str(stage.get("monthly_status") or session.final_monthly_status or "")
            if not self._branch_matches_monthly_status(normalized_branch, effective_monthly_status):
                continue
            failure_code = str(stage.get("decision_failure_code") or "")
            if not failure_code:
                continue
            formula_values = self._formula_values(stage)
            strategy_rule = self._load_s23_branch_rule(config=config, branch=normalized_branch)
            candidates: tuple[dict[str, Any], ...] = ()
            minimum_oi = None
            if strategy_rule is not None:
                minimum_oi = self._float_or_none(getattr(strategy_rule, "minimum_oi", None))
                if stage_dir is not None:
                    candidates = self._candidate_rows(
                        strategy_rule=strategy_rule,
                        stage_dir=stage_dir,
                        formula_values=formula_values,
                        selected_contract_symbol=None,
                    )
            persisted_rejected_counts = stage.get("decision_failure_rejected_counts")
            rejected_counts = (
                persisted_rejected_counts
                if isinstance(persisted_rejected_counts, dict)
                else self._candidate_rejection_counts(candidates)
            )
            side = "SELL PE" if "PUT" in normalized_branch.upper() else "SELL CE" if "CALL" in normalized_branch.upper() else "SELL"
            message = str(stage.get("decision_failure_message") or "No final contract selected.")
            rows.append(
                {
                    "branch": normalized_branch,
                    "contract": None,
                    "side": side,
                    "strike": None,
                    "premium": None,
                    "oi": None,
                    "entry": None,
                    "target": None,
                    "stoploss": None,
                    "provisional_entry": self._formula_result(formula_values, "entry"),
                    "provisional_target": self._formula_result(formula_values, "target"),
                    "provisional_stoploss": self._formula_result(formula_values, "stoploss"),
                    "order_status": failure_code,
                    "start_strike": self._formula_result(formula_values, "start_strike"),
                    "end_strike": self._formula_result(formula_values, "end_strike"),
                    "ideal_premium": self._formula_result(formula_values, "ideal_premium"),
                    "minimum_premium": self._formula_result(formula_values, "minimum_premium"),
                    "minimum_oi": minimum_oi,
                    "selection_reason": message,
                    "attempted_expiries": stage.get("decision_failure_attempted_expiries"),
                    "required_market_aliases": None,
                    "ranked_candidates": [],
                    "rejected_counts": rejected_counts,
                    "contract_candidates": candidates,
                    "formula_evaluation": stage.get("provisional_formula_evaluation"),
                    "market_refs": stage.get("market_reference_values"),
                    "option_refs": stage.get("option_reference_values"),
                    "monthly": {
                        "status": stage.get("monthly_status"),
                        "trigger_name": stage.get("monthly_status_trigger"),
                        "current_price": stage.get("monthly_status_price_used"),
                        "resolution_reason": stage.get("monthly_status_resolution_reason"),
                    },
                    "final_decision_text": f"No {side} order: {failure_code} - {message}",
                }
            )
        return rows

    @staticmethod
    def _normalize_s23_branch_name(branch: str) -> str:
        return re.sub(r"^S23_", "", str(branch or ""))

    @staticmethod
    def _branch_matches_monthly_status(branch: str, monthly_status: str | None) -> bool:
        status = str(monthly_status or "").upper()
        branch_upper = branch.upper()
        if status.startswith("BEAR"):
            return "_BEAR_" in branch_upper or branch_upper.endswith("_BEAR_CALL") or branch_upper.endswith("_BEAR_PUT")
        if status.startswith("BULL"):
            return "_BULL_" in branch_upper or branch_upper.endswith("_BULL_CALL") or branch_upper.endswith("_BULL_PUT")
        return False

    @staticmethod
    def _finalized_explainer_stage(payload: dict[str, Any]) -> dict[str, Any] | None:
        stages = payload.get("stages")
        if not isinstance(stages, list):
            return None
        for stage in reversed(stages):
            if isinstance(stage, dict) and stage.get("can_finalize_trade_decision"):
                return stage
        return None

    def _session_final_stage_dir(
        self,
        *,
        config: StrategyDashboardConfig,
        session: DashboardSessionSummary,
    ) -> Path | None:
        session_dir = session.session_directory
        if session_dir is None:
            return None
        day_dir = session_dir.parent
        for stage_dir in self._find_stage_dirs(config=config, day_dir=day_dir):
            if self._extract_stage_key(stage_dir.name) == "0930":
                return stage_dir
        return None

    def _load_s23_branch_rule(self, *, config: StrategyDashboardConfig, branch: str) -> Any | None:
        config_dir = config.strategy_path.parent
        for name in (branch, f"S23_{branch}"):
            path = config_dir / name
            if path.exists():
                try:
                    return load_strategy_rule(path)
                except Exception:
                    return None
        return None

    @staticmethod
    def _candidate_rejection_counts(candidates: tuple[dict[str, Any], ...]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in candidates:
            status = str(item.get("status") or "").upper()
            if status not in {"REJECTED", "FAIL", "FAILED"}:
                continue
            reason = str(item.get("reason") or "rejected").replace(" ", "_")
            counts[reason] = counts.get(reason, 0) + 1
        return counts

    def _render_stage_card(self, stage: DashboardStageSummary, *, page_path: Path) -> str:
        return "\n".join(
            [
                '<details class="stage-card snapshot-panel">',
                '<summary class="stage-summary">',
                '<div class="stage-topline">',
                f"<div><div class=\"eyebrow\">{html.escape(stage.stage_time)}</div><h3>{html.escape(stage.stage_name)}</h3></div>",
                f"<div class=\"badge-row\">{self._badge(stage.snapshot_status)} {self._badge(stage.monthly_status or 'n/a')}</div>",
                "</div>",
                "</summary>",
                '<div class="stage-detail">',
                '<div class="stage-metrics">',
                self._summary_metric("Checkpoints", ", ".join(stage.available_checkpoints) or "none"),
                self._summary_metric("Price Used", self._fmt_number(stage.monthly_status_price_used)),
                self._summary_metric("CDHH", self._fmt_number(stage.current_day_high_so_far)),
                self._summary_metric("CDLL", self._fmt_number(stage.current_day_low_so_far)),
                self._summary_metric("Option Chain", f"{self._fmt_number(stage.option_chain_contract_count, integer=True)} contracts"),
                self._summary_metric("OI Complete", self._badge("yes" if stage.option_chain_complete_oi else "no")),
                "</div>",
                '<div class="focus-panel">',
                f"<p><strong>Trigger</strong><br>{html.escape(stage.monthly_status_trigger or 'n/a')}</p>",
                f"<p><strong>Resolution Reason</strong><br>{html.escape(stage.monthly_status_reason or 'n/a')}</p>",
                "</div>",
                self._render_s23_rule_step_panel(stage),
                '<div class="decision-strip">',
                self._summary_metric("Selected Contract", stage.selected_contract_symbol or "n/a"),
                self._summary_metric("Entry", self._fmt_number(stage.planned_entry_price)),
                self._summary_metric("Target", self._fmt_number(stage.target_price)),
                self._summary_metric("Stoploss", self._fmt_number(stage.stoploss_price)),
                "</div>",
                self._render_stage_formula_panel(stage),
                self._render_stage_candidate_panel(stage),
                f"<div class=\"artifact-links\">{self._render_links(stage.raw_artifact_links, page_path=page_path)}</div>",
                "</div>",
                "</details>",
            ]
        )

    def _final_contract_display(
        self,
        *,
        latest: DashboardSessionSummary,
        trade_rows: list[DashboardTradeLedgerRow],
    ) -> str:
        contracts: list[str] = []
        for symbol in self._session_final_contract_symbols(latest):
            if symbol not in contracts:
                contracts.append(symbol)
        session_dir = latest.session_directory.resolve() if latest.session_directory is not None else None
        if not contracts and session_dir is not None:
            for row in trade_rows:
                if row.state_directory is None:
                    continue
                try:
                    state_dir = row.state_directory.resolve()
                except OSError:
                    continue
                if not self._is_relative_to(state_dir, session_dir):
                    continue
                symbol = row.selected_contract_symbol
                if symbol and symbol != "n/a" and symbol not in contracts:
                    contracts.append(symbol)
        if not contracts and latest.final_selected_contract_symbol:
            contracts.append(latest.final_selected_contract_symbol)
        if not contracts:
            return "n/a"
        return "<br>".join(html.escape(symbol) for symbol in contracts)

    def _session_final_contract_symbols(self, session: DashboardSessionSummary) -> tuple[str, ...]:
        contracts: list[str] = []
        session_dir = session.session_directory
        if session_dir is not None and session_dir.exists():
            for order_path in sorted(session_dir.rglob("paper_order_state.json")):
                try:
                    raw = self._read_json(order_path)
                except (OSError, json.JSONDecodeError):
                    continue
                symbol = str(raw.get("selected_contract_symbol") or "")
                if symbol and symbol != "n/a" and symbol not in contracts:
                    contracts.append(symbol)
            for summary_path in sorted(session_dir.rglob("trade_decision_summary.json")):
                try:
                    raw = self._read_json(summary_path)
                except (OSError, json.JSONDecodeError):
                    continue
                view = raw.get("summary", raw) if isinstance(raw, dict) else {}
                if not isinstance(view, dict):
                    continue
                symbol = str(view.get("selected_contract_symbol") or "")
                if symbol and symbol != "n/a" and symbol not in contracts:
                    contracts.append(symbol)
        if not contracts and session.final_selected_contract_symbol:
            contracts.append(session.final_selected_contract_symbol)
        return tuple(contracts)

    def _render_s23_rule_step_panel(self, stage: DashboardStageSummary) -> str:
        selected_candidate = next(
            (
                item
                for item in stage.candidate_rows
                if str(item.get("status") or "").upper() == "SELECTED"
            ),
            None,
        )
        selected_side = (
            str(selected_candidate.get("option_type") or "n/a")
            if selected_candidate is not None
            else "n/a"
        )
        selected_strike = (
            self._fmt_number(selected_candidate.get("strike"))
            if selected_candidate is not None
            else "n/a"
        )
        selected_premium = (
            self._fmt_number(selected_candidate.get("premium"))
            if selected_candidate is not None
            else "n/a"
        )
        selected_oi = (
            self._fmt_number(selected_candidate.get("oi"), integer=True)
            if selected_candidate is not None
            else "n/a"
        )
        status_group = self._monthly_status_group(stage.monthly_status)
        final_decision = (
            f"{html.escape(stage.selected_contract_symbol)} at strike {selected_strike}"
            if stage.selected_contract_symbol
            else "No final contract selected"
        )
        if stage.decision_failure_code:
            final_decision = f"No order: {stage.decision_failure_code}"
        step_rows = [
            ("Step 1", "Preparation date/time", f"{html.escape(stage.stage_time)} snapshot"),
            (
                "Step 2",
                "Monthly status",
                f"{self._badge(stage.monthly_status or 'n/a')} {html.escape(stage.monthly_status_trigger or '')}",
            ),
            ("Step 3", "Rule group", html.escape(status_group)),
            (
                "Step 4",
                "Strike range",
                f"{self._stage_formula_result(stage, 'start_strike')} to {self._stage_formula_result(stage, 'end_strike')}",
            ),
            (
                "Step 5",
                "Near/next contract search",
                f"{len(stage.candidate_rows)} candidates reviewed; selected side {html.escape(selected_side)}",
            ),
            (
                "Step 6",
                "Premium and OI",
                f"premium {selected_premium}, OI {selected_oi}",
            ),
            ("Step 7", "Final weekly option", final_decision),
            (
                "Step 8",
                "Entry / Target / SL",
                f"{self._fmt_number(stage.planned_entry_price)} / {self._fmt_number(stage.target_price)} / {self._fmt_number(stage.stoploss_price)}",
            ),
        ]
        rows = "\n".join(
            "<tr>"
            f"<td>{html.escape(step)}</td>"
            f"<td>{html.escape(label)}</td>"
            f"<td>{value}</td>"
            "</tr>"
            for step, label, value in step_rows
        )
        return "\n".join(
            [
                '<div class="rule-step-panel">',
                "<h4>S23 Rule Sheet Steps</h4>",
                '<table class="candidate-table rule-step-table">',
                "<thead><tr><th>Step</th><th>Rule Sheet Item</th><th>Dashboard Value</th></tr></thead>",
                f"<tbody>{rows}</tbody>",
                "</table>",
                "</div>",
            ]
        )

    def _stage_formula_result(self, stage: DashboardStageSummary, name: str) -> str:
        item = stage.formula_values.get(name)
        if not isinstance(item, dict):
            return "n/a"
        return self._fmt_number(item.get("result"))

    @staticmethod
    def _monthly_status_group(status: str | None) -> str:
        normalized = (status or "").strip().upper()
        if normalized in {"BULL", "BULL_CF", "BULLISH", "BULLISH_CONFIRMED"}:
            return "Bullish group: evaluate CE Sell Call and PE Sell Put"
        if normalized in {"BEAR", "BEAR_CF", "BEARISH", "BEARISH_CONFIRMED"}:
            return "Bearish group: evaluate CE Sell Call and PE Sell Put"
        return "Unknown group: no S23 rule group selected"

    def _render_stage_formula_panel(self, stage: DashboardStageSummary) -> str:
        def result(name: str) -> str:
            return self._stage_formula_result(stage, name)

        selected_candidate = next(
            (
                item
                for item in stage.candidate_rows
                if str(item.get("status") or "").upper() == "SELECTED"
            ),
            None,
        )
        final_strike = (
            self._fmt_number(selected_candidate.get("strike"))
            if selected_candidate is not None
            else "n/a"
        )
        final_premium = (
            self._fmt_number(selected_candidate.get("premium"))
            if selected_candidate is not None
            else "n/a"
        )
        final_oi = (
            self._fmt_number(selected_candidate.get("oi"), integer=True)
            if selected_candidate is not None
            else "n/a"
        )
        final_contract = stage.selected_contract_symbol or (
            str(selected_candidate.get("symbol"))
            if selected_candidate is not None and selected_candidate.get("symbol")
            else "n/a"
        )
        failure = ""
        if stage.decision_failure_code:
            failure = (
                "<div class=\"error-box compact-error\">"
                f"{html.escape(stage.decision_failure_code)}: "
                f"{html.escape(stage.decision_failure_message or '')}"
                "</div>"
            )
        return "\n".join(
            [
                '<div class="formula-panel">',
                "<h4>Calculated Strike Inputs</h4>",
                '<div class="summary-grid">',
                self._summary_metric("Start Strike", result("start_strike")),
                self._summary_metric("End Strike", result("end_strike")),
                self._summary_metric("Ideal Premium", result("ideal_premium")),
                self._summary_metric("Minimum Premium", result("minimum_premium")),
                self._summary_metric("Final Strike", final_strike),
                self._summary_metric("Final Contract", html.escape(final_contract)),
                self._summary_metric("Final Premium", final_premium),
                self._summary_metric("Final OI", final_oi),
                "</div>",
                failure,
                "</div>",
            ]
        )

    def _render_stage_candidate_panel(self, stage: DashboardStageSummary) -> str:
        if not stage.candidate_rows:
            return ""
        rows = "\n".join(
            [
                "<tr>"
                f"<td>{html.escape(str(item.get('strike') or 'n/a'))}</td>"
                f"<td>{html.escape(str(item.get('option_type') or 'n/a'))}</td>"
                f"<td>{html.escape(self._fmt_number(item.get('premium')))}</td>"
                f"<td>{html.escape(self._fmt_number(item.get('oi'), integer=True))}</td>"
                f"<td>{self._badge(str(item.get('status') or 'n/a'))}</td>"
                f"<td>{html.escape(str(item.get('reason') or ''))}</td>"
                "</tr>"
                for item in stage.candidate_rows
            ]
        )
        return "\n".join(
            [
                '<div class="candidate-panel">',
                "<h4>Strike Qualification</h4>",
                '<table class="candidate-table">',
                "<thead><tr><th>Strike</th><th>Side</th><th>Premium</th><th>OI</th><th>Status</th><th>Reason</th></tr></thead>",
                f"<tbody>{rows}</tbody>",
                "</table>",
                "</div>",
            ]
        )

    def _render_session_history_row(self, session: DashboardSessionSummary, *, page_path: Path) -> str:
        return "\n".join(
            [
                "<tr>",
                f"<td>{html.escape(session.session_date.isoformat())}</td>",
                f"<td>{self._badge(session.session_status)}</td>",
                f"<td>{self._badge(session.final_monthly_status or 'n/a')}</td>",
                f"<td>{html.escape(session.final_selected_contract_symbol or 'n/a')}</td>",
                f"<td>{self._render_links(session.raw_artifact_links, page_path=page_path)}</td>",
                "</tr>",
            ]
        )

    def _render_links(self, links: dict[str, str], *, page_path: Path) -> str:
        parts: list[str] = []
        for label, raw_path in sorted(links.items()):
            path = Path(raw_path)
            if not path.is_absolute():
                path = (self._repo_root / path).resolve()
            try:
                href = "/" + path.relative_to(self._repo_root).as_posix()
            except ValueError:
                try:
                    href = os.path.relpath(path, start=page_path.parent.resolve()).replace("\\", "/")
                except ValueError:
                    href = path.as_uri()
            parts.append(f'<a href="{html.escape(href)}">{html.escape(label)}</a>')
        return " ".join(parts) if parts else "<span>n/a</span>"

    def _trade_artifact_links(
        self,
        *,
        ledger_path: Path | None,
        state_directory: Path | None,
    ) -> dict[str, str]:
        links = {"Ledger": str(ledger_path)} if ledger_path is not None else {}
        if state_directory is None:
            return links
        known_artifacts = {
            "Order State": "paper_order_state.json",
            "Order Events": "paper_order_events.jsonl",
            "State": "paper_position_state.json",
            "Manager Summary": "paper_position_manager_summary.json",
            "State Events": "paper_position_state_events.jsonl",
            "Manager Events": "paper_position_manager_events.jsonl",
        }
        for label, filename in known_artifacts.items():
            artifact_path = state_directory / filename
            if artifact_path.exists():
                links[label] = str(artifact_path)
        return links

    @staticmethod
    def _iter_jsonl_dicts(path: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return rows
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                loaded = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(loaded, dict):
                rows.append(loaded)
        return rows

    @staticmethod
    def _path_or_none(value: Any) -> Path | None:
        if value is None:
            return None
        text = str(value).strip()
        return Path(text) if text else None

    @staticmethod
    def _is_relative_to(path: Path, parent: Path) -> bool:
        try:
            path.resolve().relative_to(parent.resolve())
        except ValueError:
            return False
        return True

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _float_or_default(value: Any, default: float) -> float:
        parsed = TfisOperatorDashboardBuilder._float_or_none(value)
        return parsed if parsed is not None else default

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _trade_action_required(row: DashboardTradeLedgerRow) -> bool:
        manager_status = row.manager_status.upper()
        return (
            row.fresh_entry_required
            or row.reverse_entry_required
            or row.rollover_required
            or "REQUIRED" in manager_status
        )

    @staticmethod
    def _normalize_trade_status_label(label: str) -> str:
        value = str(label or "").strip()
        if value in {"", "n/a"}:
            return ""
        if value == "PAPER_ORDER_WAITING_FOR_TRIGGER":
            return "ORDER_WAITING_FOR_TRIGGER"
        if value == "PAPER_ORDER_NOT_FILLED":
            return "ORDER_NOT_FILLED"
        return value

    def _render_monthly_status_calculator_page(
        self,
        *,
        monthly_index_path: Path | None,
    ) -> str:
        body = r"""
<nav><a href="../../index.html">Back to dashboard</a></nav>
<header class="hero">
  <div class="eyebrow">Review Mode</div>
  <h1>Monthly Status Calculator</h1>
  <p>Enter or load monthly-status reference levels by date, then calculate the status and explanation without mixing it with strategy option-chain data.</p>
</header>
<main class="calculator-shell">
  <section class="calc-panel">
    <h2>Monthly Status Inputs</h2>
    <div class="form-grid">
      <label>Review Date<input id="monthlyReviewDate" type="date"></label>
      <label>Instrument<select id="monthlyInstrument"></select></label>
      <label>Price Source<select id="monthlyPriceSource"><option value="spot">Spot</option><option value="futures_continuous">Futures Continuous</option></select></label>
      <label>Instrument Group<select id="instrumentGroup"><option value="nifty">NIFTY</option><option value="banknifty">BANKNIFTY</option><option value="stock">Stock</option><option value="currency">Currency</option><option value="gold">Gold</option><option value="silver">Silver</option><option value="crude_oil">Crude Oil</option><option value="natural_gas">Natural Gas</option></select></label>
      <label>Effective Status<select id="effectiveStatus"><option value="UNKNOWN">UNKNOWN</option><option value="BULL">BULL</option><option value="BULL_CF">BULL_CF</option><option value="BEAR">BEAR</option><option value="BEAR_CF">BEAR_CF</option></select></label>
      <label>Current Price<input id="currentPrice" type="number" step="0.05" value="0"></label>
      <label>PMH<input id="PMH" type="number" step="0.05" value="0"></label>
      <label>PML<input id="PML" type="number" step="0.05" value="0"></label>
      <label>CMH<input id="CMH" type="number" step="0.05" value="0"></label>
      <label>CML<input id="CML" type="number" step="0.05" value="0"></label>
      <label>PWH<input id="PWH" type="number" step="0.05" value="0"></label>
      <label>PWL<input id="PWL" type="number" step="0.05" value="0"></label>
      <label>CWH<input id="CWH" type="number" step="0.05" value="0"></label>
      <label>CWL<input id="CWL" type="number" step="0.05" value="0"></label>
    </div>
    <div class="form-actions">
      <button type="button" id="fetchMonthlyData">Fetch Captured Monthly Data</button>
      <button type="button" id="fetchCurrentMonthlyData">Fetch Current Monthly Data</button>
      <button type="button" id="getMonthlyStatus">GetMonthlyStatus</button>
    </div>
    <div id="monthlyFetchStatus" class="result-summary"></div>
  </section>
  <section class="calc-panel market-chart-panel">
    <div class="chart-heading">
      <div>
        <h2>Market Structure Chart</h2>
        <div id="monthlyChartSubtitle" class="chart-subtitle">Fetch current data to load candles.</div>
      </div>
      <div class="chart-tabs" role="tablist" aria-label="Monthly status chart timeframe">
        <button type="button" class="chart-tab active" data-frame="monthly">Monthly</button>
        <button type="button" class="chart-tab" data-frame="weekly">Weekly</button>
        <button type="button" class="chart-tab" data-frame="daily">Daily</button>
      </div>
    </div>
    <div id="monthlyChartMeta" class="chart-meta-grid"></div>
    <div id="monthlyChartInspector" class="chart-inspector"></div>
    <div class="chart-level-controls" aria-label="Chart level visibility">
      <label><input type="checkbox" data-level-group="monthly" checked> Monthly levels</label>
      <label><input type="checkbox" data-level-group="weekly" checked> Weekly levels</label>
      <label><input type="checkbox" data-level-group="current" checked> Current price</label>
      <label><input type="checkbox" data-level-group="labels" checked> Candle H/L labels</label>
    </div>
    <div id="monthlyChartLegend" class="chart-legend"></div>
    <div class="chart-wrap">
      <svg id="monthlyStatusChart" class="ohlc-chart" viewBox="0 0 1200 520" role="img" aria-label="Monthly status candlestick chart"></svg>
      <div id="monthlyChartEmpty" class="chart-empty">No chart data loaded.</div>
      <div id="monthlyChartTooltip" class="chart-tooltip" hidden></div>
    </div>
  </section>
  <section class="calc-panel output-panel">
    <h2>Monthly Status Result</h2>
    <div id="monthlyResultSummary" class="result-summary"></div>
    <ol id="monthlyCalculationSteps" class="trace-list"></ol>
  </section>
</main>
<script>
const THRESHOLDS = {
  nifty: { a: 0.75, b: 0.75, c: 0.15 },
  banknifty: { a: 0.75, b: 0.75, c: 0.15 },
  stock: { a: 2.50, b: 2.00, c: 1.00 },
  currency: { a: 0.15, b: 0.05, c: 0.05 },
  gold: { a: 0.50, b: 0.50, c: 0.12 },
  silver: { a: 0.70, b: 0.70, c: 0.15 },
  crude_oil: { a: 2.00, b: 1.50, c: 0.30 },
  natural_gas: { a: 2.00, b: 2.00, c: 0.50 }
};
const FALLBACK_INSTRUMENTS = [
  { symbol: "NIFTY", label: "NIFTY", instrument_group: "nifty" },
  { symbol: "BANKNIFTY", label: "BANKNIFTY", instrument_group: "banknifty" },
  { symbol: "VOLTAS", label: "VOLTAS", instrument_group: "stock" },
  { symbol: "INFY", label: "INFY", instrument_group: "stock" },
  { symbol: "TATACHEM", label: "TATACHEM", instrument_group: "stock" },
  { symbol: "ESCORTS", label: "ESCORTS", instrument_group: "stock" },
  { symbol: "ADANIENT", label: "ADANIENT", instrument_group: "stock" },
  { symbol: "CANFINHOME", label: "CANFINHOME", instrument_group: "stock" },
  { symbol: "APOLLOTYRE", label: "APOLLOTYRE", instrument_group: "stock" },
  { symbol: "HINDALCO", label: "HINDALCO", instrument_group: "stock" },
  { symbol: "INDIGO", label: "INDIGO", instrument_group: "stock" },
  { symbol: "RAMCOCEM", label: "RAMCOCEM", instrument_group: "stock" },
  { symbol: "TATACOMM", label: "TATACOMM", instrument_group: "stock" },
  { symbol: "ICICIPRULI", label: "ICICIPRULI", instrument_group: "stock" },
  { symbol: "ITC", label: "ITC", instrument_group: "stock" },
  { symbol: "TATACONSUM", label: "TATACONSUM", instrument_group: "stock" },
  { symbol: "BAJAJFINSV", label: "BAJAJFINSV", instrument_group: "stock" },
  { symbol: "TATAMOTORS", label: "TATAMOTORS", instrument_group: "stock" },
  { symbol: "DLF", label: "DLF", instrument_group: "stock" },
  { symbol: "AMBUJACEM", label: "AMBUJACEM", instrument_group: "stock" },
  { symbol: "JINDALSTEL", label: "JINDALSTEL", instrument_group: "stock" },
  { symbol: "BAJFINANCE", label: "BAJFINANCE", instrument_group: "stock" },
  { symbol: "TVSMOTOR", label: "TVSMOTOR", instrument_group: "stock" },
  { symbol: "GLENMARK", label: "GLENMARK", instrument_group: "stock" },
  { symbol: "TORNTPHARM", label: "TORNTPHARM", instrument_group: "stock" },
  { symbol: "M&M", label: "M&M", instrument_group: "stock" },
  { symbol: "SRF", label: "SRF", instrument_group: "stock" },
  { symbol: "CUMMINSIND", label: "CUMMINSIND", instrument_group: "stock" },
  { symbol: "AUROPHARMA", label: "AUROPHARMA", instrument_group: "stock" },
  { symbol: "JSWSTEEL", label: "JSWSTEEL", instrument_group: "stock" },
  { symbol: "TITAN", label: "TITAN", instrument_group: "stock" },
  { symbol: "CHOLAFIN", label: "CHOLAFIN", instrument_group: "stock" }
];
let monthlyInstrumentRegistry = { instruments: FALLBACK_INSTRUMENTS, default_symbol: "NIFTY", default_price_source: "spot" };
let monthlyChartPayload = null;
let monthlyChartFrame = "monthly";
let monthlyChartState = null;
function text(id) { return document.getElementById(id).value.trim(); }
function value(id) {
  const number = Number(document.getElementById(id).value);
  if (!Number.isFinite(number)) throw new Error(`${id} must be numeric`);
  return number;
}
function fmt(number) { return Number.isFinite(number) ? number.toFixed(2).replace(/\.00$/, "") : "n/a"; }
function fmtAxis(number) {
  if (!Number.isFinite(number)) return "n/a";
  return number.toFixed(2);
}
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}
function chartPeriodLabel(item) {
  const label = String(item.label || item.end_date || "");
  if (monthlyChartFrame === "weekly") return label.replace(/^\d{4}-/, "");
  if (monthlyChartFrame === "daily") return String(item.end_date || label).slice(5);
  return label;
}
function chartLevelVisibility() {
  const visibility = { monthly: true, weekly: true, current: true, labels: true };
  document.querySelectorAll("[data-level-group]").forEach(input => {
    visibility[input.dataset.levelGroup] = input.checked;
  });
  return visibility;
}
function candleContainsReviewDate(candle) {
  const reviewDate = text("monthlyReviewDate");
  if (!reviewDate) return false;
  const startDate = String(candle.start_date || candle.end_date || "");
  const endDate = String(candle.end_date || candle.start_date || "");
  return reviewDate >= startDate && reviewDate <= endDate;
}
function setMonthlyDefaultDate() { if (!text("monthlyReviewDate")) document.getElementById("monthlyReviewDate").value = new Date().toISOString().slice(0, 10); }
function pctAbove(base, pct) { return base * (1 + pct / 100); }
function pctBelow(base, pct) { return base * (1 - pct / 100); }
function levels() {
  return { PMH: value("PMH"), PML: value("PML"), CMH: value("CMH"), CML: value("CML"), PWH: value("PWH"), PWL: value("PWL"), CWH: value("CWH"), CWL: value("CWL"), currentPrice: value("currentPrice") };
}
function setMonthlyChartPayload(payload) {
  monthlyChartPayload = payload && payload.chart ? payload : null;
  renderMonthlyStatusChart();
}
function clearMonthlyChart(message) {
  monthlyChartPayload = null;
  monthlyChartState = null;
  document.getElementById("monthlyStatusChart").innerHTML = "";
  document.getElementById("monthlyChartMeta").innerHTML = "";
  document.getElementById("monthlyChartInspector").innerHTML = "";
  document.getElementById("monthlyChartLegend").innerHTML = "";
  document.getElementById("monthlyChartSubtitle").textContent = message || "Fetch current data to load candles.";
  document.getElementById("monthlyChartEmpty").textContent = message || "No chart data loaded.";
  document.getElementById("monthlyChartEmpty").style.display = "grid";
}
function chartLineLegend() {
  return [
    ["Monthly Highs", "PMH/CMH", "Previous and current month high reference levels.", "monthly"],
    ["Monthly Lows", "PML/CML", "Previous and current month low reference levels.", "monthly-low"],
    ["Weekly Highs", "PWH/CWH", "Previous and current week high reference levels.", "weekly"],
    ["Weekly Lows", "PWL/CWL", "Previous and current week low reference levels.", "weekly-low"],
    ["Current Price", "LTP", "Latest close/reference price used in monthly-status review.", "current"],
    ["Review Date", "marker", "The candle/window containing the selected review date.", "review"],
  ];
}
function chartReferenceLevels() {
  try {
    const l = levels();
    return [
      { key: "PMH", value: l.PMH, tone: "monthly-high", group: "monthly" },
      { key: "PML", value: l.PML, tone: "monthly-low", group: "monthly" },
      { key: "CMH", value: l.CMH, tone: "current-month-high", group: "monthly" },
      { key: "CML", value: l.CML, tone: "current-month-low", group: "monthly" },
      { key: "PWH", value: l.PWH, tone: "weekly-high", group: "weekly" },
      { key: "PWL", value: l.PWL, tone: "weekly-low", group: "weekly" },
      { key: "CWH", value: l.CWH, tone: "current-week-high", group: "weekly" },
      { key: "CWL", value: l.CWL, tone: "current-week-low", group: "weekly" },
      { key: "LTP", value: l.currentPrice, tone: "current-price", group: "current" }
    ].filter(item => Number.isFinite(item.value) && item.value > 0);
  } catch (error) {
    return [];
  }
}
function chartInspectorHtml(candle, price, refs) {
  const refMap = Object.fromEntries(refs.map(ref => [ref.key, ref.value]));
  const range = Number(candle.high) - Number(candle.low);
  const rows = [
    ["Window", chartPeriodLabel(candle)],
    ["Dates", `${candle.start_date || ""}${candle.end_date && candle.end_date !== candle.start_date ? ` -> ${candle.end_date}` : ""}`],
    ["Open", candle.open],
    ["High", candle.high],
    ["Low", candle.low],
    ["Close", candle.close],
    ["Range", range],
    ["Cursor", price],
    ["PMH", refMap.PMH],
    ["PML", refMap.PML],
    ["CMH", refMap.CMH],
    ["CML", refMap.CML],
    ["PWH", refMap.PWH],
    ["PWL", refMap.PWL],
    ["CWH", refMap.CWH],
    ["CWL", refMap.CWL],
  ];
  return rows.map(([label, val]) => {
    const rendered = typeof val === "number" || Number.isFinite(Number(val)) ? fmtAxis(Number(val)) : String(val || "n/a");
    return `<div class="inspector-cell"><span>${esc(label)}</span><strong>${esc(rendered)}</strong></div>`;
  }).join("");
}
function chartCompactTooltipHtml(candle) {
  return `<div class="tooltip-title">${esc(chartPeriodLabel(candle))}</div>
    <div class="tooltip-grid compact">
      <span>O</span><strong>${fmtAxis(Number(candle.open))}</strong>
      <span>H</span><strong>${fmtAxis(Number(candle.high))}</strong>
      <span>L</span><strong>${fmtAxis(Number(candle.low))}</strong>
      <span>C</span><strong>${fmtAxis(Number(candle.close))}</strong>
    </div>`;
}
function hideMonthlyChartHover() {
  const tooltip = document.getElementById("monthlyChartTooltip");
  tooltip.hidden = true;
  document.getElementById("chartCrosshairLayer")?.setAttribute("visibility", "hidden");
}
function handleMonthlyChartHover(event) {
  if (!monthlyChartState) return;
  const svg = document.getElementById("monthlyStatusChart");
  const tooltip = document.getElementById("monthlyChartTooltip");
  const point = svg.createSVGPoint();
  point.x = event.clientX;
  point.y = event.clientY;
  const cursor = point.matrixTransform(svg.getScreenCTM().inverse());
  const state = monthlyChartState;
  if (cursor.x < state.margin.left || cursor.x > state.width - state.margin.right || cursor.y < state.margin.top || cursor.y > state.height - state.margin.bottom) {
    hideMonthlyChartHover();
    return;
  }
  const rawIndex = Math.floor((cursor.x - state.margin.left) / state.xStep);
  const index = Math.max(0, Math.min(state.candles.length - 1, rawIndex));
  const candle = state.candles[index];
  const cx = state.x(index);
  const price = state.priceFromY(cursor.y);
  document.getElementById("crosshairV")?.setAttribute("x1", cx);
  document.getElementById("crosshairV")?.setAttribute("x2", cx);
  document.getElementById("crosshairH")?.setAttribute("y1", cursor.y);
  document.getElementById("crosshairH")?.setAttribute("y2", cursor.y);
  const priceLabel = document.getElementById("crosshairPriceLabel");
  if (priceLabel) {
    priceLabel.setAttribute("y", cursor.y + 4);
    priceLabel.textContent = fmtAxis(price);
  }
  const dateLabel = document.getElementById("crosshairDateLabel");
  if (dateLabel) {
    dateLabel.setAttribute("x", cx);
    dateLabel.textContent = chartPeriodLabel(candle);
  }
  document.getElementById("crosshairDateBox")?.setAttribute("x", cx - 36);
  document.getElementById("chartCrosshairLayer")?.setAttribute("visibility", "visible");
  document.getElementById("monthlyChartInspector").innerHTML = chartInspectorHtml(candle, price, state.refs);
  tooltip.innerHTML = chartCompactTooltipHtml(candle);
  tooltip.hidden = false;
  const wrap = svg.parentElement.getBoundingClientRect();
  const xOffset = event.clientX - wrap.left;
  const yOffset = event.clientY - wrap.top;
  tooltip.style.left = `${Math.min(wrap.width - 120, xOffset + 14)}px`;
  tooltip.style.top = `${Math.max(12, Math.min(wrap.height - 120, yOffset - 18))}px`;
}
function renderMonthlyStatusChart() {
  const svg = document.getElementById("monthlyStatusChart");
  const empty = document.getElementById("monthlyChartEmpty");
  const meta = document.getElementById("monthlyChartMeta");
  const subtitle = document.getElementById("monthlyChartSubtitle");
  const chart = monthlyChartPayload && monthlyChartPayload.chart ? monthlyChartPayload.chart : {};
  const candles = (chart[monthlyChartFrame] || []).filter(item =>
    Number.isFinite(Number(item.open)) &&
    Number.isFinite(Number(item.high)) &&
    Number.isFinite(Number(item.low)) &&
    Number.isFinite(Number(item.close))
  );
  document.querySelectorAll(".chart-tab").forEach(tab => {
    tab.classList.toggle("active", tab.dataset.frame === monthlyChartFrame);
  });
  if (!candles.length) {
    svg.innerHTML = "";
    meta.innerHTML = "";
    document.getElementById("monthlyChartInspector").innerHTML = "";
    document.getElementById("monthlyChartLegend").innerHTML = "";
    monthlyChartState = null;
    subtitle.textContent = monthlyChartPayload ? "No candles available for this timeframe." : "Fetch current data to load candles.";
    empty.textContent = monthlyChartPayload ? "No candles available for this timeframe." : "No chart data loaded.";
    empty.style.display = "grid";
    return;
  }

  empty.style.display = "none";
  const bounds = svg.getBoundingClientRect();
  const width = Math.max(1100, Math.round(bounds.width || 1200));
  const height = 520;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  const margin = { top: 28, right: 78, bottom: 56, left: 52 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const visibility = chartLevelVisibility();
  const refs = chartReferenceLevels().filter(item => visibility[item.group]);
  const highs = candles.map(item => Number(item.high)).concat(refs.map(item => item.value));
  const lows = candles.map(item => Number(item.low)).concat(refs.map(item => item.value));
  let maxPrice = Math.max(...highs);
  let minPrice = Math.min(...lows);
  if (maxPrice === minPrice) {
    maxPrice += 1;
    minPrice -= 1;
  }
  const pad = (maxPrice - minPrice) * 0.08;
  maxPrice += pad;
  minPrice -= pad;
  const xStep = plotW / Math.max(candles.length, 1);
  const bodyW = Math.max(4, Math.min(24, xStep * 0.58));
  const y = price => margin.top + ((maxPrice - price) / (maxPrice - minPrice)) * plotH;
  const x = index => margin.left + xStep * index + xStep / 2;
  const grid = [];
  for (let i = 0; i <= 5; i += 1) {
    const gy = margin.top + (plotH / 5) * i;
    const price = maxPrice - ((maxPrice - minPrice) / 5) * i;
    grid.push(`<line class="chart-grid-line" x1="${margin.left}" y1="${gy}" x2="${width - margin.right}" y2="${gy}"></line>`);
    grid.push(`<text class="chart-axis-label" x="${width - margin.right + 10}" y="${gy + 4}">${fmtAxis(price)}</text>`);
  }
  const refPositions = refs
    .map(ref => ({ ...ref, ry: y(ref.value), labelY: y(ref.value) - 6 }))
    .sort((left, right) => left.ry - right.ry);
  let previousLabelY = margin.top + 5;
  for (const ref of refPositions) {
    ref.labelY = Math.max(ref.labelY, previousLabelY + 15);
    previousLabelY = ref.labelY;
  }
  for (let i = refPositions.length - 1; i >= 0; i -= 1) {
    const maxLabelY = height - margin.bottom - 8 - (refPositions.length - 1 - i) * 15;
    refPositions[i].labelY = Math.min(refPositions[i].labelY, maxLabelY);
  }
  const referenceLines = refPositions.map(ref => `<g class="chart-reference chart-reference-${ref.tone}">
      <line x1="${margin.left}" y1="${ref.ry}" x2="${width - margin.right}" y2="${ref.ry}"></line>
      <line class="chart-label-guide" x1="${width - margin.right}" y1="${ref.ry}" x2="${width - margin.right + 10}" y2="${ref.labelY - 4}"></line>
      <text x="${width - margin.right + 12}" y="${ref.labelY}">${esc(ref.key)} ${fmtAxis(ref.value)}</text>
    </g>`).join("");
  const labelEvery = monthlyChartFrame === "monthly" ? 1 : Math.max(1, Math.ceil(candles.length / 10));
  const highLowEvery = monthlyChartFrame === "monthly" ? 1 : Math.max(1, Math.ceil(candles.length / 8));
  const candleNodes = candles.map((item, index) => {
    const open = Number(item.open);
    const high = Number(item.high);
    const low = Number(item.low);
    const close = Number(item.close);
    const cx = x(index);
    const yo = y(open);
    const yc = y(close);
    const yh = y(high);
    const yl = y(low);
    const top = Math.min(yo, yc);
    const bodyH = Math.max(2, Math.abs(yc - yo));
    const up = close >= open;
    const showLabel = index % labelEvery === 0 || index === candles.length - 1;
    const label = showLabel
      ? `<text class="chart-x-label" x="${cx}" y="${height - 18}">${esc(chartPeriodLabel(item))}</text>`
      : "";
    const showHighLow = visibility.labels && (index % highLowEvery === 0 || index === candles.length - 1);
    const highLow = showHighLow
      ? `<text class="chart-hilo chart-high" x="${cx + bodyW / 2 + 5}" y="${yh - 6}">H ${fmtAxis(high)}</text>
         <text class="chart-hilo chart-low" x="${cx + bodyW / 2 + 5}" y="${yl + 14}">L ${fmtAxis(low)}</text>`
      : "";
    return `<g class="chart-candle ${up ? "up" : "down"}">
      <line x1="${cx}" y1="${yh}" x2="${cx}" y2="${yl}"></line>
      <rect x="${cx - bodyW / 2}" y="${top}" width="${bodyW}" height="${bodyH}" rx="1"></rect>
      ${label}
      ${highLow}
    </g>`;
  }).join("");
  const reviewIndex = candles.findIndex(candleContainsReviewDate);
  const reviewMarker = reviewIndex >= 0
    ? `<g class="chart-review-marker">
        <line x1="${x(reviewIndex)}" y1="${margin.top}" x2="${x(reviewIndex)}" y2="${height - margin.bottom}"></line>
        <text x="${x(reviewIndex) + 8}" y="${margin.top + 16}">Review date</text>
      </g>`
    : "";
  const latest = candles[candles.length - 1];
  subtitle.textContent = `${monthlyChartFrame.toUpperCase()} candles for ${monthlyChartPayload.symbol || text("monthlyInstrument")} through ${monthlyChartPayload.last_bar_date || latest.end_date || ""}`;
  meta.innerHTML = [
    ["Instrument", monthlyChartPayload.symbol || text("monthlyInstrument")],
    ["Source", monthlyChartPayload.price_source || text("monthlyPriceSource")],
    ["Candles", candles.length],
    ["Latest Close", fmtAxis(Number(latest.close))]
  ].map(([label, val]) => `<div class="chart-chip"><span>${label}</span><strong>${esc(val)}</strong></div>`).join("");
  document.getElementById("monthlyChartLegend").innerHTML = chartLineLegend().map(([name, code, meaning, tone]) => `
    <div class="legend-item legend-${tone}">
      <i></i><div><strong>${esc(name)} <span>${esc(code)}</span></strong><em>${esc(meaning)}</em></div>
    </div>`).join("");
  document.getElementById("monthlyChartInspector").innerHTML = chartInspectorHtml(latest, Number(latest.close), chartReferenceLevels());
  svg.innerHTML = `
    <rect class="chart-bg" x="0" y="0" width="${width}" height="${height}"></rect>
    <g>${grid.join("")}</g>
    <line class="chart-axis" x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}"></line>
    ${referenceLines}
    ${reviewMarker}
    <g>${candleNodes}</g>
    <g id="chartCrosshairLayer" class="chart-crosshair" visibility="hidden">
      <line id="crosshairV" x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${height - margin.bottom}"></line>
      <line id="crosshairH" x1="${margin.left}" y1="${margin.top}" x2="${width - margin.right}" y2="${margin.top}"></line>
      <rect x="${width - margin.right + 4}" y="${margin.top - 12}" width="72" height="20" rx="4"></rect>
      <text id="crosshairPriceLabel" x="${width - margin.right + 10}" y="${margin.top + 4}"></text>
      <rect id="crosshairDateBox" x="${margin.left - 36}" y="${height - margin.bottom + 12}" width="72" height="22" rx="4"></rect>
      <text id="crosshairDateLabel" x="${margin.left}" y="${height - margin.bottom + 28}"></text>
    </g>
    <rect class="chart-hit-area" x="${margin.left}" y="${margin.top}" width="${plotW}" height="${plotH}"></rect>`;
  monthlyChartState = {
    candles,
    refs: chartReferenceLevels(),
    width,
    height,
    margin,
    xStep,
    x,
    priceFromY: cursorY => maxPrice - ((cursorY - margin.top) / plotH) * (maxPrice - minPrice),
  };
  svg.onmousemove = handleMonthlyChartHover;
  svg.onmouseleave = hideMonthlyChartHover;
}
function classifyMonthlyStructure(group, l) {
  const t = THRESHOLDS[group];
  const bull = pctAbove(l.PMH, t.a);
  const bear = pctBelow(l.PML, t.a);
  const bullCf = pctAbove(bull, t.b);
  const bearCf = pctBelow(bear, t.b);
  if (l.CMH >= bullCf && !(l.CML <= bearCf)) return { status: "BULL_CF", trigger: "BULL_CF_B_THRESHOLD", threshold: bullCf, notes: "CMH breached bullish confirmation threshold." };
  if (l.CML <= bearCf && !(l.CMH >= bullCf)) return { status: "BEAR_CF", trigger: "BEAR_CF_B_THRESHOLD", threshold: bearCf, notes: "CML breached bearish confirmation threshold." };
  if (l.CMH >= bull && !(l.CML <= bear)) return { status: "BULL", trigger: "BULL_A_THRESHOLD", threshold: bull, notes: "CMH breached PMH plus a-percent." };
  if (l.CML <= bear && !(l.CMH >= bull)) return { status: "BEAR", trigger: "BEAR_A_THRESHOLD", threshold: bear, notes: "CML breached PML minus a-percent." };
  return { status: "UNKNOWN", trigger: "NO_MONTHLY_TRIGGER", threshold: NaN, notes: "No direct monthly threshold was decisively breached." };
}
function applyCurrentPriceTransition(group, l, effectiveStatus) {
  const t = THRESHOLDS[group];
  const bull = pctAbove(l.PMH, t.a);
  const bear = pctBelow(l.PML, t.a);
  const bullCf = pctAbove(bull, t.b);
  const bearCf = pctBelow(bear, t.b);
  const reversalBull = pctAbove(Math.max(l.PWH, l.CWH), t.c);
  const reversalBear = pctBelow(Math.min(l.PWL, l.CWL), t.c);
  const p = l.currentPrice;
  if (effectiveStatus === "UNKNOWN") return classifyMonthlyStructure(group, l);
  if (effectiveStatus === "BULL") {
    if (p >= bullCf) return { status: "BULL_CF", trigger: "BULL_CF_B_THRESHOLD", threshold: bullCf, notes: "BULL advanced to BULL_CF by current price." };
    if (p <= reversalBear) return { status: "BEAR", trigger: "REVERSAL_BEAR_C_THRESHOLD", threshold: reversalBear, notes: "BULL reversed to BEAR using MIN(PWL, CWL) minus c-percent." };
    return { status: "BULL", trigger: "BULL_CONTINUES", threshold: bull, notes: "Effective BULL continues." };
  }
  if (effectiveStatus === "BULL_CF") {
    if (p <= bear) return { status: "BEAR", trigger: "BEAR_A_THRESHOLD", threshold: bear, notes: "BULL_CF reversed to BEAR by PML minus a-percent." };
    return { status: "BULL_CF", trigger: "BULL_CF_CONTINUES", threshold: bullCf, notes: "Effective BULL_CF continues." };
  }
  if (effectiveStatus === "BEAR") {
    if (p <= bearCf) return { status: "BEAR_CF", trigger: "BEAR_CF_B_THRESHOLD", threshold: bearCf, notes: "BEAR advanced to BEAR_CF by current price." };
    if (p >= reversalBull) return { status: "BULL", trigger: "REVERSAL_BULL_C_THRESHOLD", threshold: reversalBull, notes: "BEAR reversed to BULL using MAX(PWH, CWH) plus c-percent." };
    return { status: "BEAR", trigger: "BEAR_CONTINUES", threshold: bear, notes: "Effective BEAR continues." };
  }
  if (effectiveStatus === "BEAR_CF") {
    if (p >= bull) return { status: "BULL", trigger: "BULL_A_THRESHOLD", threshold: bull, notes: "BEAR_CF reversed to BULL by PMH plus a-percent." };
    return { status: "BEAR_CF", trigger: "BEAR_CF_CONTINUES", threshold: bearCf, notes: "Effective BEAR_CF continues." };
  }
  return classifyMonthlyStructure(group, l);
}
function calculateMonthlyStatus() {
  const group = text("instrumentGroup");
  const l = levels();
  const result = applyCurrentPriceTransition(group, l, text("effectiveStatus"));
  const t = THRESHOLDS[group];
  const bull = pctAbove(l.PMH, t.a);
  const bear = pctBelow(l.PML, t.a);
  const bullCf = pctAbove(bull, t.b);
  const bearCf = pctBelow(bear, t.b);
  const reversalBull = pctAbove(Math.max(l.PWH, l.CWH), t.c);
  const reversalBear = pctBelow(Math.min(l.PWL, l.CWL), t.c);
  document.getElementById("monthlyResultSummary").innerHTML = `<div class="summary-grid"><div class="metric"><span>Status</span><div class="value">${result.status}</div></div><div class="metric"><span>Trigger</span><div class="value">${result.trigger}</div></div><div class="metric"><span>Threshold</span><div class="value">${fmt(result.threshold)}</div></div><div class="metric"><span>Date</span><div class="value">${text("monthlyReviewDate") || "manual"}</div></div></div>`;
  const steps = [
    `Thresholds for ${group}: a=${t.a}%, b=${t.b}%, c=${t.c}%.`,
    `Bull threshold = PMH ${fmt(l.PMH)} + a% = ${fmt(bull)}; Bull CF = ${fmt(bullCf)}.`,
    `Bear threshold = PML ${fmt(l.PML)} - a% = ${fmt(bear)}; Bear CF = ${fmt(bearCf)}.`,
    `Reversal bull = MAX(PWH ${fmt(l.PWH)}, CWH ${fmt(l.CWH)}) + c% = ${fmt(reversalBull)}.`,
    `Reversal bear = MIN(PWL ${fmt(l.PWL)}, CWL ${fmt(l.CWL)}) - c% = ${fmt(reversalBear)}.`,
    `Current price ${fmt(l.currentPrice)} with effective status ${text("effectiveStatus")} produced ${result.status}: ${result.notes}`
  ];
  document.getElementById("monthlyCalculationSteps").innerHTML = steps.map(step => `<li>${step}</li>`).join("");
  renderMonthlyStatusChart();
}
async function fetchJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`Unable to load ${path}: HTTP ${response.status}`);
  return response.json();
}
function applyInstrumentRegistry(registry) {
  monthlyInstrumentRegistry = registry && Array.isArray(registry.instruments) ? registry : monthlyInstrumentRegistry;
  const select = document.getElementById("monthlyInstrument");
  select.innerHTML = monthlyInstrumentRegistry.instruments.map(item => `<option value="${item.symbol}">${item.label || item.symbol}</option>`).join("");
  const defaultSymbol = monthlyInstrumentRegistry.default_symbol || "NIFTY";
  select.value = defaultSymbol;
  if (select.value !== defaultSymbol) {
    const defaultItem = monthlyInstrumentRegistry.instruments.find(item => item.symbol === defaultSymbol);
    if (defaultItem) {
      select.insertAdjacentHTML("afterbegin", `<option value="${defaultItem.symbol}">${defaultItem.label || defaultItem.symbol}</option>`);
      select.value = defaultSymbol;
    }
  }
  document.getElementById("monthlyPriceSource").value = monthlyInstrumentRegistry.default_price_source || "spot";
  applySelectedInstrumentGroup();
}
async function initInstrumentRegistry() {
  try {
    applyInstrumentRegistry(await fetchJson("/api/monthly-status/instruments"));
  } catch (error) {
    applyInstrumentRegistry(monthlyInstrumentRegistry);
  }
}
function selectedInstrument() {
  const symbol = text("monthlyInstrument");
  return (monthlyInstrumentRegistry.instruments || []).find(item => item.symbol === symbol) || { symbol, instrument_group: text("instrumentGroup") };
}
function applySelectedInstrumentGroup() {
  const instrument = selectedInstrument();
  if (instrument.instrument_group) document.getElementById("instrumentGroup").value = instrument.instrument_group;
}
function assertCapturedPayloadMatchesSelection(payload) {
  const selected = selectedInstrument();
  const payloadSymbol = String(payload.symbol || "").toUpperCase();
  const selectedSymbol = String(selected.symbol || text("monthlyInstrument")).toUpperCase();
  if (payloadSymbol && selectedSymbol && payloadSymbol !== selectedSymbol) {
    throw new Error(`Captured monthly data is for ${payloadSymbol}, but selected instrument is ${selectedSymbol}. No captured monthly data is available for ${selectedSymbol} on this date.`);
  }
  const payloadGroup = String(payload.instrument_group || "").toLowerCase();
  const selectedGroup = String(selected.instrument_group || text("instrumentGroup")).toLowerCase();
  if (payloadGroup && selectedGroup && payloadGroup !== selectedGroup) {
    throw new Error(`Captured monthly data group is ${payloadGroup}, but selected group is ${selectedGroup}.`);
  }
}
function applyMonthlyPayload(payload) {
  const l = payload.levels || {};
  for (const key of ["PMH", "PML", "CMH", "CML", "PWH", "PWL", "CWH", "CWL"]) {
    if (l[key] !== null && l[key] !== undefined) document.getElementById(key).value = l[key];
  }
  if (l.current_price !== null && l.current_price !== undefined) document.getElementById("currentPrice").value = l.current_price;
  if (payload.instrument_group) document.getElementById("instrumentGroup").value = payload.instrument_group;
  if (payload.symbol) document.getElementById("monthlyInstrument").value = payload.symbol;
  if (payload.price_source) document.getElementById("monthlyPriceSource").value = payload.price_source;
}
function renderBackendMonthlyResult(payload) {
  const status = payload.monthly_status || {};
  const threshold = status.threshold === null || status.threshold === undefined ? Number.NaN : Number(status.threshold);
  document.getElementById("monthlyResultSummary").innerHTML = `<div class="summary-grid"><div class="metric"><span>Status</span><div class="value">${status.status || "n/a"}</div></div><div class="metric"><span>Trigger</span><div class="value">${status.trigger || "n/a"}</div></div><div class="metric"><span>Threshold</span><div class="value">${fmt(threshold)}</div></div><div class="metric"><span>Date</span><div class="value">${payload.as_of || text("monthlyReviewDate") || "manual"}</div></div></div>`;
  const steps = payload.steps || [];
  document.getElementById("monthlyCalculationSteps").innerHTML = steps.map(step => `<li>${step}</li>`).join("");
}
async function fetchCurrentMonthlyData() {
  setMonthlyDefaultDate();
  applySelectedInstrumentGroup();
  const params = new URLSearchParams({
    symbol: text("monthlyInstrument"),
    price_source: text("monthlyPriceSource"),
    as_of: text("monthlyReviewDate"),
    effective_status: text("effectiveStatus")
  });
  const response = await fetch(`/api/monthly-status/current?${params.toString()}`, { cache: "no-store" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `Unable to fetch current monthly data: HTTP ${response.status}`);
  applyMonthlyPayload(payload);
  renderBackendMonthlyResult(payload);
  setMonthlyChartPayload(payload);
  document.getElementById("monthlyFetchStatus").innerHTML = `<div class="metric"><span>Current Data</span><div class="value">Loaded ${payload.bar_count || 0} ${payload.price_source || ""} daily candles for ${payload.symbol || ""} through ${payload.last_bar_date || payload.as_of || ""}.</div></div>`;
}
async function fetchCapturedMonthlyData(options = {}) {
  setMonthlyDefaultDate();
  const index = await fetchJson("../../data/review/monthly-status/index.json");
  const dates = index.dates || {};
  let date = text("monthlyReviewDate");
  if (!dates[date]) {
    const availableDates = Object.keys(dates).sort();
    if (!availableDates.length) throw new Error("No captured monthly-status data found yet. Run a snapshot/decision stage first.");
    date = availableDates[availableDates.length - 1];
    document.getElementById("monthlyReviewDate").value = date;
  }
  const dataPath = dates[date];
  const payload = await fetchJson(`../../${dataPath}`);
  assertCapturedPayloadMatchesSelection(payload);
  applyMonthlyPayload(payload);
  if (payload.monthly_status && payload.monthly_status.status) document.getElementById("effectiveStatus").value = payload.monthly_status.status;
  if (payload.chart) setMonthlyChartPayload(payload);
  else clearMonthlyChart("No candle chart was captured for this historical monthly-status artifact.");
  const prefix = options.prefix ? `${options.prefix} ` : "";
  document.getElementById("monthlyFetchStatus").innerHTML = `<div class="metric"><span>Captured Data</span><div class="value">${prefix}Loaded monthly-status data for ${date} from ${payload.source_artifact || "review data"}.</div></div>`;
  calculateMonthlyStatus();
}
document.getElementById("fetchMonthlyData").addEventListener("click", async () => { try { await fetchCapturedMonthlyData(); } catch (error) { document.getElementById("monthlyFetchStatus").innerHTML = `<div class="error-box">${error.message}</div>`; } });
document.getElementById("fetchCurrentMonthlyData").addEventListener("click", async () => {
  try {
    await fetchCurrentMonthlyData();
  } catch (error) {
    try {
      await fetchCapturedMonthlyData({ prefix: `Live FYERS current fetch failed (${error.message});` });
    } catch (fallbackError) {
      document.getElementById("monthlyFetchStatus").innerHTML = `<div class="error-box">Live FYERS current fetch failed: ${error.message}. ${fallbackError.message}</div>`;
    }
  }
});
document.getElementById("getMonthlyStatus").addEventListener("click", () => { try { calculateMonthlyStatus(); } catch (error) { document.getElementById("monthlyResultSummary").innerHTML = `<div class="error-box">${error.message}</div>`; } });
document.querySelectorAll(".chart-tab").forEach(tab => {
  tab.addEventListener("click", () => {
    monthlyChartFrame = tab.dataset.frame || "monthly";
    renderMonthlyStatusChart();
  });
});
document.querySelectorAll("[data-level-group]").forEach(input => {
  input.addEventListener("change", renderMonthlyStatusChart);
});
document.getElementById("monthlyInstrument").addEventListener("change", () => {
  applySelectedInstrumentGroup();
  clearMonthlyChart("Fetch current data to load candles for the selected instrument.");
});
document.getElementById("monthlyPriceSource").addEventListener("change", () => {
  clearMonthlyChart("Fetch current data to load candles for the selected price source.");
});
setMonthlyDefaultDate();
initInstrumentRegistry().then(() => calculateMonthlyStatus()).catch(() => calculateMonthlyStatus());
</script>
"""
        return self._render_page(title="Monthly Status Calculator", body=body)

    def _render_s23_manual_calculator_page(self) -> str:
        body = r"""
<nav><a href="../../index.html">Back to dashboard</a></nav>
<header class="hero">
  <div class="eyebrow">Review Mode</div>
  <h1>S23 Manual Calculator</h1>
  <p>Enter reference levels, calculate eligible strikes, add premium/OI values, and review the final S23 entry, target, stoploss, and strike selection.</p>
</header>
<main class="calculator-shell">
  <section class="calc-panel">
    <h2>Manual Inputs</h2>
    <div id="s23-calculator-form">
      <div class="form-grid">
        <label>Monthly Group<select id="monthlyGroup"><option value="bullish">Bullish / Bullish Confirmed</option><option value="bearish">Bearish / Bearish Confirmed</option></select></label>
        <label>Strike Step<input id="strikeStep" type="number" step="50" value="50"></label>
        <label>NIFTY Lot Size<input id="lotSize" type="number" step="1" value="65"></label>
        <label>Minimum OI Lots<input id="minOiLots" type="number" step="1" value="500"></label>
        <label>Near Contract Label<input id="nearLabel" value="near"></label>
        <label>Next Contract Label<input id="nextLabel" value="next"></label>
        <label>Review Date<input id="reviewDate" type="date"></label>
      </div>

      <h3>Spot References</h3>
      <div class="form-grid">
        <label>PRV 2DHH<input id="d2hh" type="number" step="0.05" value="24108.20"></label>
        <label>PRV 2DLL<input id="d2ll" type="number" step="0.05" value="23888.20"></label>
        <label>PRV 3DHH<input id="d3hh" type="number" step="0.05" value="24108.20"></label>
        <label>PRV 3DLL<input id="d3ll" type="number" step="0.05" value="23817.80"></label>
      </div>

      <div class="form-actions">
        <button type="button" id="calculateStrikes">CalculateStrikes</button>
        <button type="button" id="fetchS23Data">Fetch Captured Premium/OI</button>
      </div>
      <div id="fetchStatus" class="result-summary"></div>
    </div>
  </section>

  <section class="calc-panel output-panel">
    <h2>Eligible Strikes</h2>
    <div id="strikeSummary" class="result-summary"></div>
    <div class="two-column-output">
      <div>
        <h3>Eligible CE Strikes</h3>
        <div id="ceStrikeRows" class="strike-editor"></div>
      </div>
      <div>
        <h3>Eligible PE Strikes</h3>
        <div id="peStrikeRows" class="strike-editor"></div>
      </div>
    </div>
    <div id="finalStrikeSummary" class="result-summary"></div>
  </section>

  <section class="calc-panel output-panel">
    <h2>Rule Sheet Steps</h2>
    <div id="manualRuleSteps" class="result-summary"></div>
  </section>

  <section class="calc-panel output-panel">
      <h3>Option Reference Premiums</h3>
      <div class="form-grid">
        <label>OPT PRV 2DHH<input id="opt2dhh" type="number" step="0.05" value="242"></label>
        <label>OPT PRV 2DLL<input id="opt2dll" type="number" step="0.05" value="210"></label>
        <label>OPT PRV 3DHH<input id="opt3dhh" type="number" step="0.05" value="220"></label>
        <label>OPT PRV 3DLL<input id="opt3dll" type="number" step="0.05" value="230"></label>
      </div>

      <div class="form-actions">
        <button type="button" id="calculateRisk">Calculate</button>
        <button type="button" id="loadBearPut">Load Bear PE Sample</button>
        <button type="button" id="loadBullCall">Load Bull CE Sample</button>
      </div>
    <h2>Calculated Result</h2>
    <div id="resultSummary" class="result-summary"></div>
    <ol id="calculationSteps" class="trace-list"></ol>
  </section>
</main>
<script>
const BRANCHES = {
  bullish: {
    CE: { trade: "Sell Call", spotRef: "d3ll", entryRef: "opt3dll", slRef: "opt2dhh", slBuffer: 1.07, direction: "down" },
    PE: { trade: "Sell Put", spotRef: "d2hh", entryRef: "opt2dll", slRef: "opt3dhh", slBuffer: 1.10, direction: "up" }
  },
  bearish: {
    CE: { trade: "Sell Call", spotRef: "d2ll", entryRef: "opt2dll", slRef: "opt3dhh", slBuffer: 1.10, direction: "down" },
    PE: { trade: "Sell Put", spotRef: "d3hh", entryRef: "opt3dll", slRef: "opt2dhh", slBuffer: 1.07, direction: "up" }
  }
};

function number(id) {
  const value = Number(document.getElementById(id).value);
  if (!Number.isFinite(value)) throw new Error(`${id} must be a number`);
  return value;
}
function text(id) { return document.getElementById(id).value.trim(); }
function setDefaultDate() { if (!text("reviewDate")) document.getElementById("reviewDate").value = new Date().toISOString().slice(0, 10); }
function roundDown(value, step) { return Math.floor(value / step) * step; }
function roundUp(value, step) { return Math.ceil(value / step) * step; }
function fmt(value) { return Number.isFinite(value) ? value.toFixed(2).replace(/\.00$/, "") : "n/a"; }
function branchLabel(group, side) {
  return `${group === "bullish" ? "Bullish / Bullish Confirmed" : "Bearish / Bearish Confirmed"} ${side}`;
}
function refs() {
  return {
    d2hh: number("d2hh"), d2ll: number("d2ll"), d3hh: number("d3hh"), d3ll: number("d3ll"),
    opt2dhh: number("opt2dhh"), opt2dll: number("opt2dll"), opt3dhh: number("opt3dhh"), opt3dll: number("opt3dll")
  };
}
function strikePlan(group, side) {
  const branch = BRANCHES[group][side];
  const step = number("strikeStep");
  const ref = refs()[branch.spotRef];
  const start = branch.direction === "down" ? roundDown(ref * 1.05, step) : roundUp(ref * 0.95, step);
  const end = branch.direction === "down" ? roundDown(ref, step) - step : roundUp(ref, step) + step;
  const low = Math.min(start, end);
  const high = Math.max(start, end);
  const strikes = [];
  if (start > end) {
    for (let strike = start; strike >= end; strike -= step) strikes.push(strike);
  } else {
    for (let strike = start; strike <= end; strike += step) strikes.push(strike);
  }
  return { group, side, branch, ref, start, end, low, high, strikes, idealPremium: ref * 0.012, minimumPremium: ref * 0.009 };
}
function inputValue(selector) {
  const element = document.querySelector(selector);
  if (!element) return Number.NaN;
  return Number(element.value);
}
function renderStrikeRows(targetId, plan) {
  const target = document.getElementById(targetId);
  target.innerHTML = `
    <div class="strike-row strike-row-header">
      <span>Strike</span><span>Near Premium</span><span>Near OI</span><span>Next Premium</span><span>Next OI</span>
    </div>
    ${plan.strikes.map((strike, index) => `
      <div class="strike-row" data-side="${plan.side}" data-strike="${strike}">
        <span class="strike-value">${fmt(strike)}</span>
        <input data-role="near-premium" type="number" step="0.05" value="${index === 0 ? fmt(plan.idealPremium) : ""}">
        <input data-role="near-oi" type="number" step="1" value="">
        <input data-role="next-premium" type="number" step="0.05" value="">
        <input data-role="next-oi" type="number" step="1" value="">
      </div>`).join("")}`;
}
function readStrikeRows(side) {
  return [...document.querySelectorAll(`.strike-row[data-side="${side}"]`)].map(row => ({
    side,
    strike: Number(row.dataset.strike),
    nearPremium: Number(row.querySelector('[data-role="near-premium"]').value),
    nearOi: Number(row.querySelector('[data-role="near-oi"]').value),
    nextPremium: Number(row.querySelector('[data-role="next-premium"]').value),
    nextOi: Number(row.querySelector('[data-role="next-oi"]').value)
  }));
}
function rowQualified(row, contract, plan, minOiContracts) {
  const premium = contract === "near" ? row.nearPremium : row.nextPremium;
  const oi = contract === "near" ? row.nearOi : row.nextOi;
  if (!Number.isFinite(premium) || !Number.isFinite(oi)) return false;
  return oi >= minOiContracts && premium >= plan.minimumPremium;
}
function selectFromRows(rows, plan, minOiContracts) {
  const nearRows = rows.filter(row => rowQualified(row, "near", plan, minOiContracts));
  const nearIdeal = nearRows.find(row => row.nearPremium >= plan.idealPremium);
  if (nearIdeal) return { row: nearIdeal, contract: text("nearLabel") || "near", premium: nearIdeal.nearPremium, oi: nearIdeal.nearOi, reason: "Near contract ideal premium qualified." };
  if (nearRows.length) {
    const row = [...nearRows].reverse()[0];
    return { row, contract: text("nearLabel") || "near", premium: row.nearPremium, oi: row.nearOi, reason: "Near contract minimum premium fallback qualified." };
  }
  const nextRows = rows.filter(row => rowQualified(row, "next", plan, minOiContracts));
  const nextIdeal = nextRows.find(row => row.nextPremium >= plan.idealPremium);
  if (nextIdeal) return { row: nextIdeal, contract: text("nextLabel") || "next", premium: nextIdeal.nextPremium, oi: nextIdeal.nextOi, reason: "Near contract failed; next contract ideal premium qualified." };
  if (nextRows.length) {
    const row = [...nextRows].reverse()[0];
    return { row, contract: text("nextLabel") || "next", premium: row.nextPremium, oi: row.nextOi, reason: "Near contract failed; next contract minimum premium fallback qualified." };
  }
  return { row: null, contract: "", premium: Number.NaN, oi: Number.NaN, reason: "No near or next contract row met minimum OI and minimum premium." };
}
function calculateStrikes() {
  const group = text("monthlyGroup");
  const cePlan = strikePlan(group, "CE");
  const pePlan = strikePlan(group, "PE");
  renderStrikeRows("ceStrikeRows", cePlan);
  renderStrikeRows("peStrikeRows", pePlan);
  document.getElementById("strikeSummary").innerHTML = `
    <div class="summary-grid">
      <div class="metric"><span>CE Range</span><div class="value">${fmt(cePlan.start)} -> ${fmt(cePlan.end)}</div></div>
      <div class="metric"><span>CE Ideal / Min</span><div class="value">${fmt(cePlan.idealPremium)} / ${fmt(cePlan.minimumPremium)}</div></div>
      <div class="metric"><span>PE Range</span><div class="value">${fmt(pePlan.start)} -> ${fmt(pePlan.end)}</div></div>
      <div class="metric"><span>PE Ideal / Min</span><div class="value">${fmt(pePlan.idealPremium)} / ${fmt(pePlan.minimumPremium)}</div></div>
    </div>`;
  updateFinalStrikes();
}
async function fetchJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`Unable to load ${path}: HTTP ${response.status}`);
  return response.json();
}
function applyCapturedS23Data(payload) {
  const expiries = [...new Set((payload.contracts || []).map(row => row.expiry).filter(Boolean))].sort();
  const nearExpiry = expiries[0];
  const nextExpiry = expiries[1];
  let applied = 0;
  for (const side of ["CE", "PE"]) {
    for (const row of document.querySelectorAll(`.strike-row[data-side="${side}"]`)) {
      const strike = Number(row.dataset.strike);
      const near = (payload.contracts || []).find(item => item.option_type === side && Number(item.strike) === strike && item.expiry === nearExpiry);
      const next = (payload.contracts || []).find(item => item.option_type === side && Number(item.strike) === strike && item.expiry === nextExpiry);
      if (near) {
        row.querySelector('[data-role="near-premium"]').value = near.premium ?? "";
        row.querySelector('[data-role="near-oi"]').value = near.oi ?? "";
        applied += 1;
      }
      if (next) {
        row.querySelector('[data-role="next-premium"]').value = next.premium ?? "";
        row.querySelector('[data-role="next-oi"]').value = next.oi ?? "";
        applied += 1;
      }
    }
  }
  updateFinalStrikes();
  return { applied, nearExpiry, nextExpiry };
}
async function fetchCapturedS23Data() {
  setDefaultDate();
  calculateStrikes();
  const date = text("reviewDate");
  const index = await fetchJson("../../data/review/strategies/S23/index.json");
  const dataPath = index.dates && index.dates[date];
  if (!dataPath) throw new Error(`No captured S23 review data found for ${date}. Run a snapshot for that date first.`);
  const payload = await fetchJson(`../../${dataPath}`);
  const result = applyCapturedS23Data(payload);
  document.getElementById("fetchStatus").innerHTML = `<div class="metric"><span>Captured Data</span><div class="value">Loaded ${result.applied} values for ${date}. Near expiry: ${result.nearExpiry || "n/a"}; next expiry: ${result.nextExpiry || "n/a"}.</div></div>`;
}
function updateFinalStrikes() {
  const group = text("monthlyGroup");
  const minOiContracts = number("minOiLots") * number("lotSize");
  const cePlan = strikePlan(group, "CE");
  const pePlan = strikePlan(group, "PE");
  const ce = selectFromRows(readStrikeRows("CE"), cePlan, minOiContracts);
  const pe = selectFromRows(readStrikeRows("PE"), pePlan, minOiContracts);
  document.getElementById("finalStrikeSummary").innerHTML = `
    <div class="summary-grid">
      <div class="metric"><span>Final CE Strike</span><div class="value">${ce.row ? `${fmt(ce.row.strike)} ${ce.contract}` : "No qualified CE"}</div></div>
      <div class="metric"><span>Final CE Premium / OI</span><div class="value">${ce.row ? `${fmt(ce.premium)} / ${fmt(ce.oi)}` : "n/a"}</div></div>
      <div class="metric"><span>CE Reason</span><div class="value">${ce.reason}</div></div>
      <div class="metric"><span>Final PE Strike</span><div class="value">${pe.row ? `${fmt(pe.row.strike)} ${pe.contract}` : "No qualified PE"}</div></div>
      <div class="metric"><span>Final PE Premium / OI</span><div class="value">${pe.row ? `${fmt(pe.premium)} / ${fmt(pe.oi)}` : "n/a"}</div></div>
      <div class="metric"><span>PE Reason</span><div class="value">${pe.reason}</div></div>
    </div>`;
  return { CE: ce, PE: pe };
}
function riskForSide(group, side, selectedBySide) {
  const plan = strikePlan(group, side);
  const branch = plan.branch;
  const refValues = refs();
  const selected = selectedBySide[side];
  const entryReference = refValues[branch.entryRef];
  const entry = entryReference * 0.925;
  const target = entry * 0.40;
  const percentSl = entry * 1.60;
  const structureReference = refValues[branch.slRef];
  const structureSl = structureReference * branch.slBuffer;
  const stoploss = Math.min(percentSl, structureSl);
  return {
    side,
    plan,
    branch,
    selected,
    entryReference,
    entry,
    target,
    percentSl,
    structureReference,
    structureSl,
    stoploss,
    status: selected.row ? "READY" : "NO ORDER"
  };
}
function riskRowHtml(result) {
  const selected = result.selected;
  const strike = selected.row ? fmt(selected.row.strike) : "n/a";
  const contract = selected.row ? selected.contract : "n/a";
  const premium = selected.row ? fmt(selected.premium) : "n/a";
  const oi = selected.row ? fmt(selected.oi) : "n/a";
  return `<tr>
    <td>${result.side}</td>
    <td>${result.branch.trade}</td>
    <td>${result.branch.spotRef.toUpperCase()}</td>
    <td>${fmt(result.plan.start)} -> ${fmt(result.plan.end)}</td>
    <td>${strike}</td>
    <td>${contract}</td>
    <td>${premium}</td>
    <td>${oi}</td>
    <td>${result.branch.entryRef.toUpperCase()} = ${fmt(result.entryReference)}</td>
    <td>${fmt(result.entry)}</td>
    <td>${fmt(result.target)}</td>
    <td>${result.branch.slRef.toUpperCase()} = ${fmt(result.structureReference)}</td>
    <td>${fmt(result.stoploss)}</td>
    <td>${result.status}</td>
  </tr>`;
}
function calculate() {
  const group = text("monthlyGroup");
  const selectedBySide = updateFinalStrikes();
  const ce = riskForSide(group, "CE", selectedBySide);
  const pe = riskForSide(group, "PE", selectedBySide);
  const minOiContracts = number("minOiLots") * number("lotSize");

  const summary = document.getElementById("resultSummary");
  summary.innerHTML = `
    <table class="risk-table">
      <thead>
        <tr>
          <th>Side</th><th>Trade</th><th>Spot Ref</th><th>Strike Range</th><th>Final Strike</th><th>Contract</th><th>Premium</th><th>OI</th><th>Entry Ref</th><th>Entry</th><th>Target</th><th>SL Ref</th><th>Final SL</th><th>Status</th>
        </tr>
      </thead>
      <tbody>
        ${riskRowHtml(ce)}
        ${riskRowHtml(pe)}
      </tbody>
    </table>`;
  renderManualRuleSteps(group, ce, pe, minOiContracts);
  const steps = [
    `${branchLabel(group, "CE")}: spot ref ${ce.branch.spotRef.toUpperCase()} = ${fmt(ce.plan.ref)}, range ${fmt(ce.plan.start)} -> ${fmt(ce.plan.end)}, final strike ${ce.selected.row ? fmt(ce.selected.row.strike) : "not selected"}; ${ce.selected.reason}`,
    `${branchLabel(group, "PE")}: spot ref ${pe.branch.spotRef.toUpperCase()} = ${fmt(pe.plan.ref)}, range ${fmt(pe.plan.start)} -> ${fmt(pe.plan.end)}, final strike ${pe.selected.row ? fmt(pe.selected.row.strike) : "not selected"}; ${pe.selected.reason}`,
    `Minimum OI = ${fmt(number("minOiLots"))} lots * ${fmt(number("lotSize"))} = ${fmt(minOiContracts)} contracts. Manual OI fields are used on this static review page.`,
    `CE final calculation: entry = ${ce.branch.entryRef.toUpperCase()} ${fmt(ce.entryReference)} * 0.925 = ${fmt(ce.entry)}; target = ${fmt(ce.target)}; SL = min(entry * 1.60 = ${fmt(ce.percentSl)}, ${ce.branch.slRef.toUpperCase()} * ${fmt(ce.branch.slBuffer)} = ${fmt(ce.structureSl)}) = ${fmt(ce.stoploss)}.`,
    `PE final calculation: entry = ${pe.branch.entryRef.toUpperCase()} ${fmt(pe.entryReference)} * 0.925 = ${fmt(pe.entry)}; target = ${fmt(pe.target)}; SL = min(entry * 1.60 = ${fmt(pe.percentSl)}, ${pe.branch.slRef.toUpperCase()} * ${fmt(pe.branch.slBuffer)} = ${fmt(pe.structureSl)}) = ${fmt(pe.stoploss)}.`
  ];
  document.getElementById("calculationSteps").innerHTML = steps.map(stepText => `<li>${stepText}</li>`).join("");
}
function renderManualRuleSteps(group, ce, pe, minOiContracts) {
  const groupLabel = group === "bullish" ? "Bullish group: evaluate CE Sell Call and PE Sell Put" : "Bearish group: evaluate CE Sell Call and PE Sell Put";
  const ceFinal = ce.selected.row ? `${fmt(ce.selected.row.strike)} ${ce.selected.contract}` : "No qualified CE";
  const peFinal = pe.selected.row ? `${fmt(pe.selected.row.strike)} ${pe.selected.contract}` : "No qualified PE";
  const rows = [
    ["Step 1", "Preparation date/time", text("reviewDate") || "today"],
    ["Step 2", "Monthly status", text("monthlyGroup") === "bullish" ? "BULLISH / BULLISH_CONFIRMED" : "BEARISH / BEARISH_CONFIRMED"],
    ["Step 3", "Rule group", groupLabel],
    ["Step 4", "Strike range", `CE ${fmt(ce.plan.start)} -> ${fmt(ce.plan.end)}; PE ${fmt(pe.plan.start)} -> ${fmt(pe.plan.end)}`],
    ["Step 5", "Near contract search", `${ce.selected.reason}; ${pe.selected.reason}`],
    ["Step 6", "Minimum OI", `${fmt(number("minOiLots"))} lots * ${fmt(number("lotSize"))} = ${fmt(minOiContracts)} contracts`],
    ["Step 7", "Final weekly options", `CE: ${ceFinal}; PE: ${peFinal}`],
    ["Step 8", "Entry / Target / SL", `CE ${fmt(ce.entry)} / ${fmt(ce.target)} / ${fmt(ce.stoploss)}; PE ${fmt(pe.entry)} / ${fmt(pe.target)} / ${fmt(pe.stoploss)}`],
  ];
  document.getElementById("manualRuleSteps").innerHTML = `
    <table class="candidate-table rule-step-table">
      <thead><tr><th>Step</th><th>Rule Sheet Item</th><th>Manual Review Value</th></tr></thead>
      <tbody>${rows.map(row => `<tr><td>${row[0]}</td><td>${row[1]}</td><td>${row[2]}</td></tr>`).join("")}</tbody>
    </table>`;
}
document.getElementById("calculateStrikes").addEventListener("click", () => { try { calculateStrikes(); } catch (error) { document.getElementById("strikeSummary").innerHTML = `<div class="error-box">${error.message}</div>`; } });
document.getElementById("fetchS23Data").addEventListener("click", async () => { try { await fetchCapturedS23Data(); } catch (error) { document.getElementById("fetchStatus").innerHTML = `<div class="error-box">${error.message}</div>`; } });
document.getElementById("calculateRisk").addEventListener("click", () => { try { calculate(); } catch (error) { document.getElementById("resultSummary").innerHTML = `<div class="error-box">${error.message}</div>`; } });
document.addEventListener("input", event => { if (event.target.closest(".strike-editor")) updateFinalStrikes(); });
document.getElementById("loadBearPut").addEventListener("click", () => { document.getElementById("monthlyGroup").value = "bearish"; calculateStrikes(); calculate(); });
document.getElementById("loadBullCall").addEventListener("click", () => { document.getElementById("monthlyGroup").value = "bullish"; calculateStrikes(); calculate(); });
setDefaultDate();
calculateStrikes();
calculate();
</script>
"""
        return self._render_page(title="S23 Manual Calculator", body=body)

    @staticmethod
    def _render_page(*, title: str, body: str) -> str:
        return "\n".join(
            [
                "<!doctype html>",
                "<html lang=\"en\">",
                "<head>",
                "  <meta charset=\"utf-8\">",
                "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
                f"  <title>{html.escape(title)}</title>",
                "  <style>",
                "    :root { --bg: #f6f2ea; --card: #fffdf9; --ink: #17211b; --muted: #607068; --accent: #0f5e59; --accent-2: #8f5a2a; --border: #d8ccb7; --soft-border: #eadfce; --soft-fill: #fff9f0; --good: #216e39; --bad: #9a3412; --pending: #946200; --unknown: #5b5f97; }",
                "    body { margin: 0; font-family: 'Segoe UI', Arial, sans-serif; background: #f6f2ea; color: var(--ink); font-size: 14px; line-height: 1.45; }",
                "    a { color: var(--accent); text-decoration: none; } a:hover { text-decoration: underline; }",
                "    .hero { padding: 34px 40px 22px; border-bottom: 1px solid var(--border); background: linear-gradient(135deg, #fff9ef, #f0e3ca); }",
                "    .hero h1 { margin: 0 0 8px; font-size: 2.05rem; letter-spacing: 0; }",
                "    .eyebrow { color: var(--accent); text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.78rem; font-weight: 700; margin-bottom: 10px; }",
                "    nav { padding: 16px 40px 0; }",
                "    section { padding: 24px 40px; }",
                "    .grid, .stage-grid { display: grid; gap: 18px; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }",
                "    .strategy-card, .stage-card, .session-summary { display: block; background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; box-shadow: 0 10px 24px rgba(47, 39, 22, 0.06); }",
                "    .strategy-card { transition: transform 160ms ease, box-shadow 160ms ease; } .strategy-card:hover { transform: translateY(-2px); box-shadow: 0 20px 38px rgba(47, 39, 22, 0.1); text-decoration: none; }",
                "    .strategy-card h2, .stage-card h3 { margin: 0 0 8px; font-family: Georgia, 'Times New Roman', serif; }",
                "    .summary-shell { padding: 22px; }",
                "    .summary-shell + .summary-shell { margin-top: 14px; }",
                "    .summary-grid, .stage-metrics, .decision-strip { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }",
                "    .metric { background: var(--soft-fill); border: 1px solid var(--soft-border); border-radius: 8px; padding: 11px 12px; min-width: 0; }",
                "    .metric span { display: block; color: var(--muted); font-size: 0.76rem; line-height: 1.2; margin-bottom: 6px; font-weight: 700; }",
                "    .metric strong, .metric .value { font-size: 0.98rem; line-height: 1.25; font-weight: 750; overflow-wrap: anywhere; }",
                "    .metric-row { display: flex; justify-content: space-between; align-items: center; gap: 14px; padding: 8px 0; border-top: 1px dashed #e5d9c8; }",
                "    .metric-row:first-of-type { border-top: 0; }",
                "    .stage-topline { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }",
                "    .snapshot-panel { padding: 0; overflow: hidden; }",
                "    .stage-summary { display: block; cursor: pointer; list-style: none; padding: 18px 20px; }",
                "    .stage-summary::-webkit-details-marker { display: none; }",
                "    .stage-summary .stage-topline::before { content: '▶'; color: var(--accent); font-size: 0.78rem; margin-top: 4px; transition: transform 160ms ease; }",
                "    .snapshot-panel[open] .stage-summary .stage-topline::before { transform: rotate(90deg); }",
                "    .stage-detail { padding: 0 20px 20px; border-top: 1px solid var(--soft-border); }",
                "    .stage-detail .stage-metrics { margin-top: 16px; }",
                "    .badge-row { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }",
                "    .badge { display: inline-flex; align-items: center; justify-content: center; border-radius: 999px; padding: 4px 9px; font-size: 0.72rem; line-height: 1.15; font-weight: 750; letter-spacing: 0; border: 1px solid currentColor; white-space: nowrap; }",
                "    .badge-ready, .badge-pass, .badge-selected, .badge-bull, .badge-bear, .badge-bull_cf, .badge-bear_cf, .badge-yes { color: var(--good); background: rgba(33,110,57,0.09); }",
                "    .badge-in_progress, .badge-unknown, .badge-no_trigger, .badge-n_a, .badge-none { color: var(--unknown); background: rgba(91,95,151,0.1); }",
                "    .badge-warning, .badge-pending { color: var(--pending); background: rgba(148,98,0,0.1); }",
                "    .badge-no_go, .badge-failed, .badge-rejected, .badge-no { color: var(--bad); background: rgba(154,52,18,0.1); }",
                "    .focus-panel { margin: 14px 0; padding: 14px 16px; border-radius: 8px; background: #fff9f0; border: 1px solid #e9dcc7; }",
                "    .focus-panel p { margin: 0 0 10px; } .focus-panel p:last-child { margin-bottom: 0; }",
                "    .rule-step-panel, .formula-panel, .candidate-panel { margin-top: 14px; padding-top: 12px; border-top: 1px dashed #e1d3bd; }",
                "    .rule-step-panel h4, .formula-panel h4, .candidate-panel h4 { margin: 0 0 10px; font-size: 1rem; }",
                "    .candidate-table { display: block; overflow-x: auto; font-size: 0.86rem; border-radius: 8px; }",
                "    .candidate-table thead, .candidate-table tbody { display: table; width: 100%; }",
                "    .section-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; margin-bottom: 14px; }",
                "    .section-heading h3 { margin: 0; font-family: Georgia, 'Times New Roman', serif; font-size: 1.12rem; }",
                "    .section-heading span { color: var(--muted); font-size: 0.82rem; font-weight: 650; }",
                "    .final-leg-panel { overflow-x: auto; }",
                "    .final-leg-table { display: table; table-layout: fixed; width: 100%; min-width: 1180px; overflow: hidden; font-size: 0.82rem; }",
                "    .final-leg-table thead, .final-leg-table tbody { display: table-row-group; width: auto; }",
                "    .final-leg-table thead { display: table-header-group; }",
                "    .final-leg-table th, .final-leg-table td { padding: 10px 12px; vertical-align: middle; }",
                "    .final-leg-table th:nth-child(1), .final-leg-table td:nth-child(1) { width: 190px; }",
                "    .final-leg-table th:nth-child(2), .final-leg-table td:nth-child(2) { width: 240px; }",
                "    .final-leg-table th:nth-child(3), .final-leg-table td:nth-child(3) { width: 90px; }",
                "    .final-leg-table th:nth-child(4), .final-leg-table td:nth-child(4) { width: 80px; }",
                "    .final-leg-table th:nth-child(5), .final-leg-table td:nth-child(5) { width: 90px; }",
                "    .final-leg-table th:nth-child(6), .final-leg-table td:nth-child(6) { width: 105px; }",
                "    .final-leg-table th:nth-child(7), .final-leg-table td:nth-child(7) { width: 90px; }",
                "    .final-leg-table th:nth-child(8), .final-leg-table td:nth-child(8) { width: 90px; }",
                "    .final-leg-table th:nth-child(9), .final-leg-table td:nth-child(9) { width: 80px; }",
                "    .final-leg-table th:nth-child(10), .final-leg-table td:nth-child(10) { width: 170px; }",
                "    .final-leg-table th { color: #405047; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; font-weight: 800; }",
                "    .final-leg-table tbody tr:nth-child(even) td { background: #fffaf3; }",
                "    .text-cell { text-align: left; }",
                "    .number-cell { text-align: right; font-variant-numeric: tabular-nums; }",
                "    .status-cell { text-align: center; }",
                "    .code-cell { font-family: Consolas, 'Courier New', monospace; font-size: 0.78rem; overflow-wrap: anywhere; }",
                "    .contract-cell strong { display: inline-block; font-family: Consolas, 'Courier New', monospace; font-size: 0.82rem; background: #f6efe4; border: 1px solid #e3d6c2; border-radius: 6px; padding: 3px 6px; white-space: nowrap; }",
                "    .side-cell { font-weight: 800; color: var(--accent); white-space: nowrap; }",
                "    .final-leg-table .code-cell { font-size: 0.76rem; line-height: 1.3; }",
                "    .final-leg-table .contract-cell strong { box-sizing: border-box; max-width: 100%; overflow: hidden; text-overflow: ellipsis; vertical-align: middle; font-size: 0.78rem; padding: 4px 7px; }",
                "    .final-leg-table .side-cell { font-size: 0.78rem; letter-spacing: 0; }",
                "    .final-leg-table .number-cell { white-space: nowrap; }",
                "    .final-leg-table .badge { font-size: 0.66rem; padding: 4px 8px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; }",
                "    .leg-explanation-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 16px; }",
                "    .explanation-panel { cursor: default; }",
                "    .explanation-summary { display: flex; align-items: center; justify-content: space-between; gap: 16px; cursor: pointer; list-style: none; }",
                "    .explanation-summary::-webkit-details-marker { display: none; }",
                "    .explanation-summary::before { content: '▶'; color: var(--accent); font-size: 0.82rem; transition: transform 160ms ease; }",
                "    .explanation-panel[open] .explanation-summary::before { transform: rotate(90deg); }",
                "    .explanation-summary span { font-family: Georgia, 'Times New Roman', serif; font-size: 1.12rem; font-weight: 700; }",
                "    .explanation-summary small { color: var(--muted); font-size: 0.82rem; font-weight: 650; }",
                "    .explanation-panel[open] .focus-panel { margin-top: 16px; }",
                "    .leg-explanation-card { border: 1px solid var(--soft-border); border-radius: 8px; background: #fffaf3; padding: 16px; }",
                "    .leg-explanation-card h3 { margin: 0 0 12px; font-size: 1rem; color: var(--accent); font-family: Georgia, 'Times New Roman', serif; }",
                "    .eligible-strike-panel { margin: 14px 0; }",
                "    .eligible-strike-panel h4 { margin: 0 0 10px; font-size: 0.98rem; color: var(--ink); font-family: 'Segoe UI', Arial, sans-serif; font-weight: 800; }",
                "    .eligible-strike-table { display: table; table-layout: fixed; width: 100%; overflow: hidden; font-size: 0.86rem; }",
                "    .eligible-strike-table thead, .eligible-strike-table tbody { display: table-row-group; width: auto; }",
                "    .eligible-strike-table thead { display: table-header-group; }",
                "    .eligible-strike-table th, .eligible-strike-table td { padding: 11px 14px; vertical-align: middle; }",
                "    .eligible-strike-table th { font-size: 0.74rem; letter-spacing: 0.04em; }",
                "    .eligible-strike-table th.number-cell, .eligible-strike-table td.number-cell { text-align: right; font-variant-numeric: tabular-nums; }",
                "    .eligible-strike-table th.text-cell, .eligible-strike-table td.text-cell { text-align: left; }",
                "    .eligible-strike-table th.status-cell, .eligible-strike-table td.status-cell { text-align: center; }",
                "    .eligible-strike-table th:nth-child(1), .eligible-strike-table td:nth-child(1) { width: 88px; }",
                "    .eligible-strike-table th:nth-child(2), .eligible-strike-table td:nth-child(2) { width: 240px; }",
                "    .eligible-strike-table th:nth-child(3), .eligible-strike-table td:nth-child(3), .eligible-strike-table th:nth-child(4), .eligible-strike-table td:nth-child(4), .eligible-strike-table th:nth-child(5), .eligible-strike-table td:nth-child(5) { width: 112px; }",
                "    .eligible-strike-table th:nth-child(6), .eligible-strike-table td:nth-child(6) { width: 116px; }",
                "    .eligible-strike-table .contract-cell strong { display: inline-block; max-width: 100%; box-sizing: border-box; font-size: 0.78rem; padding: 4px 7px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; vertical-align: middle; }",
                "    .eligible-strike-table .badge { min-width: 78px; }",
                "    .table-help { margin: 0 0 12px; color: var(--ink); font-size: 0.9rem; line-height: 1.45; }",
                "    .full-scan-panel { margin-top: 14px; border: 1px solid var(--soft-border); border-radius: 8px; background: #fffaf3; overflow: hidden; }",
                "    .full-scan-panel summary { cursor: pointer; padding: 11px 14px; color: var(--accent); font-weight: 800; list-style: none; border-bottom: 1px solid transparent; }",
                "    .full-scan-panel summary::-webkit-details-marker { display: none; }",
                "    .full-scan-panel summary::before { content: '▶'; display: inline-block; margin-right: 8px; font-size: 0.78rem; transition: transform 160ms ease; }",
                "    .full-scan-panel[open] summary { border-bottom-color: var(--soft-border); }",
                "    .full-scan-panel[open] summary::before { transform: rotate(90deg); }",
                "    .full-scan-panel .table-help { margin: 12px 14px; }",
                "    .full-scan-table-wrap { overflow-x: auto; padding-bottom: 4px; }",
                "    .full-scan-table { table-layout: fixed; min-width: 930px; border-left: 0; border-right: 0; border-bottom: 0; border-radius: 0; font-size: 0.8rem; }",
                "    .full-scan-table th, .full-scan-table td { padding: 8px 9px; }",
                "    .full-scan-table th { font-size: 0.68rem; }",
                "    .full-scan-table th:nth-child(1), .full-scan-table td:nth-child(1) { width: 68px; }",
                "    .full-scan-table th:nth-child(2), .full-scan-table td:nth-child(2) { width: 205px; }",
                "    .full-scan-table th:nth-child(3), .full-scan-table td:nth-child(3) { width: 82px; }",
                "    .full-scan-table th:nth-child(4), .full-scan-table td:nth-child(4) { width: 94px; }",
                "    .full-scan-table th:nth-child(5), .full-scan-table td:nth-child(5) { width: 104px; }",
                "    .full-scan-table th:nth-child(6), .full-scan-table td:nth-child(6) { width: 104px; }",
                "    .full-scan-table th:nth-child(7), .full-scan-table td:nth-child(7) { width: 230px; }",
                "    .full-scan-table .contract-cell strong { font-size: 0.72rem; padding: 3px 6px; }",
                "    .full-scan-table .badge { min-width: 68px; font-size: 0.64rem; padding: 3px 7px; }",
                "    .full-scan-table .reason-cell { color: var(--muted); font-size: 0.76rem; line-height: 1.25; }",
                "    .explanation-list { margin: 0; padding-left: 20px; display: grid; gap: 8px; }",
                "    .explanation-list li { padding-left: 4px; }",
                "    .explanation-table { margin-top: 14px; }",
                "    .rule-step-table th, .rule-step-table td { padding: 8px 10px; vertical-align: top; text-align: left; }",
                "    .rule-step-table td:first-child { width: 70px; font-weight: 700; color: var(--accent); white-space: nowrap; }",
                "    .rule-step-table td:nth-child(2) { width: 160px; font-weight: 700; }",
                "    .compact-error { margin-top: 10px; }",
                "    .artifact-links { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; font-size: 0.9rem; }",
                "    .artifact-links a { padding: 6px 10px; border-radius: 999px; background: #f4ecdf; border: 1px solid #e4d6c1; font-size: 0.82rem; }",
                "    .top-links { margin-top: 16px; }",
                "    .trade-summary { margin-bottom: 14px; }",
                "    .trade-table { display: table; table-layout: fixed; font-family: 'Segoe UI', Arial, sans-serif; font-size: 0.84rem; line-height: 1.28; }",
                "    .trade-table th, .trade-table td { padding: 10px 12px; }",
                "    .trade-table th { color: #3f493f; font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.04em; }",
                "    .trade-table .badge { padding: 4px 8px; font-size: 0.68rem; line-height: 1; white-space: nowrap; }",
                "    .trade-time { width: 105px; white-space: normal; }",
                "    .trade-event { width: 64px; text-align: center; }",
                "    .trade-strategy { width: 205px; }",
                "    .trade-contract { width: 285px; }",
                "    .trade-side { width: 82px; }",
                "    .trade-number { width: 78px; text-align: right; font-variant-numeric: tabular-nums; }",
                "    .trade-status { width: 260px; }",
                "    .trade-manage { width: 230px; }",
                "    .trade-links { margin-top: 0; min-width: 0; gap: 6px; }",
                "    .trade-links a { padding: 5px 9px; }",
                "    .status-badges { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 6px; }",
                "    .trade-reason { color: var(--ink); font-size: 0.78rem; }",
                "    .code-text { font-family: Consolas, 'Courier New', monospace; overflow-wrap: anywhere; }",
                "    .muted-text { color: var(--muted); font-size: 0.82rem; word-break: break-word; }",
                "    .empty-panel { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 18px; color: var(--muted); }",
                "    .tool-strip { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 18px; }",
                "    .tool-link, button { display: inline-flex; align-items: center; justify-content: center; border: 1px solid var(--accent); background: var(--accent); color: white; border-radius: 10px; padding: 10px 14px; font-weight: 700; cursor: pointer; font: inherit; }",
                "    .tool-link:hover, button:hover { text-decoration: none; filter: brightness(0.95); }",
                "    button[type='button'] { background: #fff8ef; color: var(--accent); }",
                "    .calculator-shell { display: grid; grid-template-columns: 1fr; gap: 20px; padding: 24px 40px; }",
                "    .calc-panel { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 18px; box-shadow: 0 16px 32px rgba(47,39,22,0.07); }",
                "    .market-chart-panel { padding: 0; overflow: hidden; }",
                "    .chart-heading { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 18px; border-bottom: 1px solid var(--soft-border); }",
                "    .chart-heading h2 { margin: 0 0 4px; font-size: 1.15rem; }",
                "    .chart-subtitle { color: var(--muted); font-size: 0.86rem; font-weight: 650; }",
                "    .chart-tabs { display: inline-flex; gap: 6px; padding: 4px; border: 1px solid var(--soft-border); border-radius: 10px; background: #f7efe2; }",
                "    .chart-tab { border: 0; border-radius: 7px; padding: 7px 11px; background: transparent; color: var(--muted); font-size: 0.82rem; }",
                "    .chart-tab.active { background: var(--accent); color: #fff; }",
                "    .chart-meta-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(135px, 1fr)); gap: 10px; padding: 14px 18px 0; }",
                "    .chart-chip { border: 1px solid #273447; background: #121a27; color: #d6dee9; border-radius: 8px; padding: 8px 10px; min-width: 0; }",
                "    .chart-chip span { display: block; color: #8ea0b6; font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; }",
                "    .chart-chip strong { display: block; margin-top: 3px; color: #f5f7fb; font-size: 0.94rem; overflow-wrap: anywhere; }",
                "    .chart-inspector { display: grid; grid-template-columns: repeat(auto-fit, minmax(92px, 1fr)); gap: 8px; padding: 10px 18px 0; }",
                "    .inspector-cell { border: 1px solid #d9cdbb; background: #fff8ee; border-radius: 8px; padding: 7px 9px; min-width: 0; }",
                "    .inspector-cell span { display: block; color: var(--muted); font-size: 0.68rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.04em; }",
                "    .inspector-cell strong { display: block; margin-top: 2px; color: var(--ink); font-size: 0.88rem; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }",
                "    .chart-level-controls { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; padding: 12px 18px 0; color: var(--muted); font-size: 0.82rem; font-weight: 750; }",
                "    .chart-level-controls label { display: inline-flex; grid-auto-flow: column; align-items: center; gap: 6px; width: auto; color: inherit; font-size: inherit; }",
                "    .chart-level-controls input { width: auto; accent-color: var(--accent); }",
                "    .chart-legend { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 8px; padding: 10px 18px 0; }",
                "    .legend-item { display: grid; grid-template-columns: 28px 1fr; gap: 8px; align-items: start; border: 1px solid var(--soft-border); background: #fffaf3; border-radius: 8px; padding: 8px 10px; }",
                "    .legend-item i { display: block; height: 0; margin-top: 10px; border-top: 3px dashed currentColor; }",
                "    .legend-item strong { display: block; font-size: 0.8rem; color: var(--ink); }",
                "    .legend-item strong span { color: var(--muted); font-weight: 750; }",
                "    .legend-item em { display: block; color: var(--muted); font-size: 0.74rem; font-style: normal; line-height: 1.25; }",
                "    .legend-monthly { color: #f59e0b; } .legend-monthly-low { color: #38bdf8; } .legend-weekly { color: #a78bfa; } .legend-weekly-low { color: #34d399; } .legend-current { color: #f43f5e; } .legend-current i { border-top-style: solid; } .legend-review { color: #475569; }",
                "    .chart-wrap { position: relative; margin: 14px 18px 18px; min-height: 360px; border: 1px solid #263348; border-radius: 10px; background: #0d1320; overflow: hidden; }",
                "    .ohlc-chart { display: block; width: 100%; height: min(58vh, 560px); min-height: 360px; font-family: 'Segoe UI', Arial, sans-serif; }",
                "    .chart-bg { fill: #0d1320; }",
                "    .chart-grid-line { stroke: #253149; stroke-width: 1; }",
                "    .chart-axis { stroke: #526174; stroke-width: 1; }",
                "    .chart-axis-label, .chart-x-label { fill: #9aa9bb; font-size: 13px; font-variant-numeric: tabular-nums; }",
                "    .chart-x-label { text-anchor: middle; font-size: 11px; }",
                "    .chart-candle line { stroke-width: 1.4; }",
                "    .chart-candle.up line, .chart-candle.up rect { stroke: #00b386; fill: #00a077; }",
                "    .chart-candle.down line, .chart-candle.down rect { stroke: #ff5b64; fill: #e94d5a; }",
                "    .chart-hilo { fill: #dbe5f0; font-size: 11px; font-weight: 650; paint-order: stroke; stroke: #0d1320; stroke-width: 3px; stroke-linejoin: round; }",
                "    .chart-high { fill: #f7c948; }",
                "    .chart-low { fill: #7dd3fc; }",
                "    .chart-reference line { stroke-width: 1.5; stroke-dasharray: 7 5; }",
                "    .chart-reference text { font-size: 12px; font-weight: 750; paint-order: stroke; stroke: #0d1320; stroke-width: 3px; stroke-linejoin: round; }",
                "    .chart-reference-monthly-high line, .chart-reference-monthly-high text, .chart-reference-current-month-high line, .chart-reference-current-month-high text { stroke: #f59e0b; fill: #f59e0b; }",
                "    .chart-reference-monthly-low line, .chart-reference-monthly-low text, .chart-reference-current-month-low line, .chart-reference-current-month-low text { stroke: #38bdf8; fill: #38bdf8; }",
                "    .chart-reference-weekly-high line, .chart-reference-weekly-high text, .chart-reference-current-week-high line, .chart-reference-current-week-high text { stroke: #a78bfa; fill: #a78bfa; }",
                "    .chart-reference-weekly-low line, .chart-reference-weekly-low text, .chart-reference-current-week-low line, .chart-reference-current-week-low text { stroke: #34d399; fill: #34d399; }",
                "    .chart-reference-current-price line { stroke-width: 2; stroke-dasharray: 0; }",
                "    .chart-reference-current-price line, .chart-reference-current-price text { stroke: #f43f5e; fill: #f43f5e; }",
                "    .chart-review-marker line { stroke: #f8fafc; stroke-width: 1.2; stroke-dasharray: 3 6; opacity: 0.72; }",
                "    .chart-review-marker text { fill: #f8fafc; font-size: 12px; font-weight: 800; paint-order: stroke; stroke: #0d1320; stroke-width: 3px; }",
                "    .chart-hit-area { fill: transparent; pointer-events: all; cursor: crosshair; }",
                "    .chart-crosshair line { stroke: #b8c7da; stroke-width: 1; stroke-dasharray: 4 4; opacity: 0.86; pointer-events: none; }",
                "    .chart-crosshair rect { fill: #111827; stroke: #3d4d63; stroke-width: 1; opacity: 0.96; pointer-events: none; }",
                "    .chart-crosshair text { fill: #f8fafc; font-size: 12px; font-weight: 750; text-anchor: middle; font-variant-numeric: tabular-nums; pointer-events: none; }",
                "    #crosshairPriceLabel { text-anchor: start; }",
                "    .chart-tooltip { position: absolute; z-index: 3; width: 104px; max-width: calc(100% - 24px); padding: 8px 9px; border: 1px solid #40506a; border-radius: 8px; background: rgba(15, 23, 42, 0.92); color: #e5edf7; box-shadow: 0 10px 22px rgba(0,0,0,0.26); pointer-events: none; }",
                "    .tooltip-title { font-weight: 850; color: #fff; margin-bottom: 2px; }",
                "    .tooltip-subtitle { color: #9fb0c5; font-size: 0.76rem; margin-bottom: 9px; }",
                "    .tooltip-grid { display: grid; grid-template-columns: 1fr auto; gap: 4px 14px; font-size: 0.78rem; }",
                "    .tooltip-grid.compact { gap: 3px 8px; }",
                "    .tooltip-grid span { color: #9fb0c5; }",
                "    .tooltip-grid strong { color: #f8fafc; font-variant-numeric: tabular-nums; }",
                "    .chart-empty { position: absolute; inset: 0; display: grid; place-items: center; color: #aeb9c8; font-weight: 700; background: rgba(13,19,32,0.82); }",
                "    .form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 14px; }",
                "    label { display: grid; gap: 6px; color: var(--muted); font-weight: 700; font-size: 0.88rem; }",
                "    input, select, textarea { width: 100%; box-sizing: border-box; border: 1px solid var(--border); border-radius: 10px; padding: 9px 10px; background: #fffaf2; color: var(--ink); font: inherit; }",
                "    textarea { min-height: 150px; resize: vertical; font-family: Consolas, 'Courier New', monospace; font-size: 0.88rem; }",
                "    .form-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }",
                "    .two-column-output { display: grid; grid-template-columns: repeat(2, minmax(320px, 1fr)); gap: 18px; margin: 12px 0 18px; }",
                "    .strike-editor { display: grid; gap: 6px; }",
                "    .strike-row { display: grid; grid-template-columns: 92px repeat(4, minmax(92px, 1fr)); gap: 8px; align-items: center; padding: 8px; border: 1px solid #eadcc9; border-radius: 10px; background: #fff8ef; }",
                "    .strike-row-header { background: #f4eadb; color: var(--muted); font-size: 0.78rem; font-weight: 700; }",
                "    .strike-row input { padding: 7px 8px; border-radius: 8px; }",
                "    .strike-value { font-weight: 700; }",
                "    .result-summary { margin-bottom: 16px; }",
                "    .trace-list { display: grid; gap: 8px; padding-left: 22px; }",
                "    .trace-list li { padding: 8px 10px; background: #fff8ef; border: 1px solid #eadcc9; border-radius: 10px; }",
                "    .error-box { padding: 12px; border: 1px solid var(--bad); color: var(--bad); background: rgba(154,52,18,0.08); border-radius: 10px; }",
                "    table { width: 100%; border-collapse: separate; border-spacing: 0; background: var(--card); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }",
                "    th, td { text-align: left; padding: 11px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }",
                "    th { background: #f2e8d8; color: #405047; font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.04em; font-weight: 800; }",
                "    tbody tr:last-child td { border-bottom: 0; }",
                "    .risk-table { display: block; overflow-x: auto; white-space: nowrap; }",
                "    .risk-table tbody, .risk-table thead { display: table; width: 100%; }",
                "    .active-risk-row td { background: rgba(15,94,89,0.08); }",
                "    @media (max-width: 980px) { .two-column-output { grid-template-columns: 1fr; } }",
                "    @media (max-width: 720px) { .strike-row { grid-template-columns: 1fr 1fr; } .strike-row-header { display: none; } }",
                "    @media (max-width: 720px) { .hero, section, nav, .calculator-shell { padding-left: 18px; padding-right: 18px; } }",
                "  </style>",
                "</head>",
                "<body>",
                body,
                "</body>",
                "</html>",
            ]
        )

    def _session_manifest_item(self, session: DashboardSessionSummary) -> dict[str, Any]:
        final_contracts = list(self._session_final_contract_symbols(session))
        return {
            "session_date": session.session_date.isoformat(),
            "session_status": session.session_status,
            "final_decision_status": session.final_decision_status,
            "final_monthly_status": session.final_monthly_status,
            "final_selected_contract_symbol": session.final_selected_contract_symbol,
            "final_selected_contract_symbols": final_contracts,
            "session_directory": str(session.session_directory) if session.session_directory is not None else None,
            "stage_count": len(session.stages),
        }

    @staticmethod
    def _badge(value: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_") or "n_a"
        safe = html.escape(str(value))
        return f'<span class="badge badge-{normalized}">{safe}</span>'

    @staticmethod
    def _summary_metric(label: str, value: str) -> str:
        return f'<div class="metric"><span>{html.escape(label)}</span><div class="value">{value}</div></div>'

    @staticmethod
    def _fmt_number(value: Any, *, integer: bool = False) -> str:
        if value is None:
            return "n/a"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        if integer:
            return f"{int(number)}"
        if number.is_integer():
            return f"{int(number)}"
        return f"{number:.2f}"
