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
        latest_block = self._render_latest_session_block(latest=latest, page_path=page_path) if latest else "<p>No session artifacts found yet.</p>"
        trade_rows = self._collect_trade_ledger_rows(config)
        trades_block = self._render_trade_ledger_section(rows=trade_rows, page_path=page_path)
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
            ]
        )
        return self._render_page(title=config.display_name, body=body)

    def _collect_trade_ledger_rows(
        self,
        config: StrategyDashboardConfig,
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
    ) -> str:
        if not rows:
            return '<div class="empty-panel">No paper trades have been recorded yet.</div>'

        latest_by_trade: dict[str, DashboardTradeLedgerRow] = {}
        for row in reversed(rows):
            latest_by_trade[row.trade_id] = row
        latest_rows = list(latest_by_trade.values())
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
        event_rows = "\n".join(self._render_trade_ledger_row(row, page_path=page_path) for row in rows[:80])
        return "\n".join(
            [
                header,
                '<table class="trade-table">',
                "<thead><tr><th>Time</th><th>Event</th><th>Strategy</th><th>Contract</th><th>Side / Qty</th><th>Entry</th><th>Exit</th><th>Target / SL</th><th>P&L</th><th>Status</th><th>Manage</th></tr></thead>",
                f"<tbody>{event_rows}</tbody>",
                "</table>",
            ]
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
        status_parts = [
            self._badge(row.lifecycle_status),
            self._badge(row.manager_status),
        ]
        if action_text:
            status_parts.append(self._badge(action_text))
        reason = html.escape(row.reason_code)
        if row.message:
            reason = f"{reason}<br><span class=\"muted-text\">{html.escape(row.message)}</span>"
        return "\n".join(
            [
                "<tr>",
                f"<td>{html.escape(event_time)}</td>",
                f"<td>{self._badge(row.event_type)}</td>",
                f"<td>{html.escape(row.strategy_id)}<br><span class=\"muted-text\">{html.escape(row.strategy_branch)}</span></td>",
                f"<td>{html.escape(row.selected_contract_symbol)}<br><span class=\"muted-text\">{html.escape(row.trade_id)}</span></td>",
                f"<td>{html.escape(row.side)}<br>{self._fmt_number(row.lots, integer=True)} lots / {self._fmt_number(row.quantity, integer=True)}</td>",
                f"<td>{self._fmt_number(row.entry_price)}</td>",
                f"<td>{self._fmt_number(row.exit_price)}</td>",
                f"<td>{self._fmt_number(row.target_price)} / {self._fmt_number(row.stoploss_price)}</td>",
                f"<td>{self._fmt_number(row.gross_points)} pts<br>{self._fmt_number(row.gross_pnl)}</td>",
                f"<td>{' '.join(status_parts)}<br>{reason}</td>",
                f"<td><div class=\"artifact-links trade-links\">{self._render_links(row.raw_artifact_links, page_path=page_path)}</div></td>",
                "</tr>",
            ]
        )

    def _render_latest_session_block(self, *, latest: DashboardSessionSummary, page_path: Path) -> str:
        stage_cards = "\n".join(self._render_stage_card(stage, page_path=page_path) for stage in latest.stages)
        artifact_links = self._render_links(latest.raw_artifact_links, page_path=page_path)
        return "\n".join(
            [
                '<div class="session-summary summary-shell">',
                '<div class="summary-grid">',
                self._summary_metric("Session Date", latest.session_date.isoformat()),
                self._summary_metric("Run Status", self._badge(latest.session_status)),
                self._summary_metric("Final Monthly Status", self._badge(latest.final_monthly_status or "n/a")),
                self._summary_metric("Final Contract", latest.final_selected_contract_symbol or "n/a"),
                self._summary_metric("Stage Coverage", " / ".join(stage.stage_time for stage in latest.stages) or "n/a"),
                self._summary_metric("Stage Count", str(len(latest.stages))),
                "</div>",
                f"<div class=\"artifact-links top-links\">{artifact_links}</div>",
                "</div>",
                "<div class=\"stage-grid\">",
                stage_cards or "<p>No stage artifacts found.</p>",
                "</div>",
            ]
        )

    def _render_stage_card(self, stage: DashboardStageSummary, *, page_path: Path) -> str:
        return "\n".join(
            [
                '<article class="stage-card">',
                '<div class="stage-topline">',
                f"<div><div class=\"eyebrow\">{html.escape(stage.stage_time)}</div><h3>{html.escape(stage.stage_name)}</h3></div>",
                f"<div class=\"badge-row\">{self._badge(stage.snapshot_status)} {self._badge(stage.monthly_status or 'n/a')}</div>",
                "</div>",
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
                '<div class="decision-strip">',
                self._summary_metric("Selected Contract", stage.selected_contract_symbol or "n/a"),
                self._summary_metric("Entry", self._fmt_number(stage.planned_entry_price)),
                self._summary_metric("Target", self._fmt_number(stage.target_price)),
                self._summary_metric("Stoploss", self._fmt_number(stage.stoploss_price)),
                "</div>",
                self._render_stage_formula_panel(stage),
                self._render_stage_candidate_panel(stage),
                f"<div class=\"artifact-links\">{self._render_links(stage.raw_artifact_links, page_path=page_path)}</div>",
                "</article>",
            ]
        )

    def _render_stage_formula_panel(self, stage: DashboardStageSummary) -> str:
        def result(name: str) -> str:
            item = stage.formula_values.get(name)
            if not isinstance(item, dict):
                return "n/a"
            return self._fmt_number(item.get("result"))

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
        ledger_path: Path,
        state_directory: Path | None,
    ) -> dict[str, str]:
        links = {"Ledger": str(ledger_path)}
        if state_directory is None:
            return links
        known_artifacts = {
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
    def _float_or_none(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

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
function text(id) { return document.getElementById(id).value.trim(); }
function value(id) {
  const number = Number(document.getElementById(id).value);
  if (!Number.isFinite(number)) throw new Error(`${id} must be numeric`);
  return number;
}
function fmt(number) { return Number.isFinite(number) ? number.toFixed(2).replace(/\.00$/, "") : "n/a"; }
function setMonthlyDefaultDate() { if (!text("monthlyReviewDate")) document.getElementById("monthlyReviewDate").value = new Date().toISOString().slice(0, 10); }
function pctAbove(base, pct) { return base * (1 + pct / 100); }
function pctBelow(base, pct) { return base * (1 - pct / 100); }
function levels() {
  return { PMH: value("PMH"), PML: value("PML"), CMH: value("CMH"), CML: value("CML"), PWH: value("PWH"), PWL: value("PWL"), CWH: value("CWH"), CWL: value("CWL"), currentPrice: value("currentPrice") };
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
document.getElementById("monthlyInstrument").addEventListener("change", applySelectedInstrumentGroup);
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
        <label>Option Side<select id="optionSide"><option value="CE">CE Sell Call</option><option value="PE">PE Sell Put</option></select></label>
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
    PE: { trade: "Sell Put", spotRef: "d2ll", entryRef: "opt2dll", slRef: "opt3dhh", slBuffer: 1.10, direction: "up" }
  },
  bearish: {
    CE: { trade: "Sell Call", spotRef: "d2ll", entryRef: "opt2dll", slRef: "opt3dhh", slBuffer: 1.10, direction: "down" },
    PE: { trade: "Sell Put", spotRef: "d3hh", entryRef: "opt3dhh", slRef: "opt2dhh", slBuffer: 1.07, direction: "up" }
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
      <div class="metric"><span>CE Reason</span><div class="value">${ce.reason}</div></div>
      <div class="metric"><span>Final PE Strike</span><div class="value">${pe.row ? `${fmt(pe.row.strike)} ${pe.contract}` : "No qualified PE"}</div></div>
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
function riskRowHtml(result, activeSide) {
  const selected = result.selected;
  const strike = selected.row ? fmt(selected.row.strike) : "n/a";
  const contract = selected.row ? selected.contract : "n/a";
  const premium = selected.row ? fmt(selected.premium) : "n/a";
  const oi = selected.row ? fmt(selected.oi) : "n/a";
  const active = result.side === activeSide ? " active-risk-row" : "";
  return `<tr class="${active}">
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
  const activeSide = text("optionSide");
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
        ${riskRowHtml(ce, activeSide)}
        ${riskRowHtml(pe, activeSide)}
      </tbody>
    </table>`;
  const steps = [
    `${branchLabel(group, "CE")}: spot ref ${ce.branch.spotRef.toUpperCase()} = ${fmt(ce.plan.ref)}, range ${fmt(ce.plan.start)} -> ${fmt(ce.plan.end)}, final strike ${ce.selected.row ? fmt(ce.selected.row.strike) : "not selected"}; ${ce.selected.reason}`,
    `${branchLabel(group, "PE")}: spot ref ${pe.branch.spotRef.toUpperCase()} = ${fmt(pe.plan.ref)}, range ${fmt(pe.plan.start)} -> ${fmt(pe.plan.end)}, final strike ${pe.selected.row ? fmt(pe.selected.row.strike) : "not selected"}; ${pe.selected.reason}`,
    `Minimum OI = ${fmt(number("minOiLots"))} lots * ${fmt(number("lotSize"))} = ${fmt(minOiContracts)} contracts. Manual OI fields are used on this static review page.`,
    `CE final calculation: entry = ${ce.branch.entryRef.toUpperCase()} ${fmt(ce.entryReference)} * 0.925 = ${fmt(ce.entry)}; target = ${fmt(ce.target)}; SL = min(entry * 1.60 = ${fmt(ce.percentSl)}, ${ce.branch.slRef.toUpperCase()} * ${fmt(ce.branch.slBuffer)} = ${fmt(ce.structureSl)}) = ${fmt(ce.stoploss)}.`,
    `PE final calculation: entry = ${pe.branch.entryRef.toUpperCase()} ${fmt(pe.entryReference)} * 0.925 = ${fmt(pe.entry)}; target = ${fmt(pe.target)}; SL = min(entry * 1.60 = ${fmt(pe.percentSl)}, ${pe.branch.slRef.toUpperCase()} * ${fmt(pe.branch.slBuffer)} = ${fmt(pe.structureSl)}) = ${fmt(pe.stoploss)}.`
  ];
  document.getElementById("calculationSteps").innerHTML = steps.map(stepText => `<li>${stepText}</li>`).join("");
}
document.getElementById("calculateStrikes").addEventListener("click", () => { try { calculateStrikes(); } catch (error) { document.getElementById("strikeSummary").innerHTML = `<div class="error-box">${error.message}</div>`; } });
document.getElementById("fetchS23Data").addEventListener("click", async () => { try { await fetchCapturedS23Data(); } catch (error) { document.getElementById("fetchStatus").innerHTML = `<div class="error-box">${error.message}</div>`; } });
document.getElementById("calculateRisk").addEventListener("click", () => { try { calculate(); } catch (error) { document.getElementById("resultSummary").innerHTML = `<div class="error-box">${error.message}</div>`; } });
document.addEventListener("input", event => { if (event.target.closest(".strike-editor")) updateFinalStrikes(); });
document.getElementById("loadBearPut").addEventListener("click", () => { document.getElementById("monthlyGroup").value = "bearish"; document.getElementById("optionSide").value = "PE"; calculateStrikes(); });
document.getElementById("loadBullCall").addEventListener("click", () => { document.getElementById("monthlyGroup").value = "bullish"; document.getElementById("optionSide").value = "CE"; calculateStrikes(); });
setDefaultDate();
calculateStrikes();
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
                "    :root { --bg: #f5efe3; --card: #fffdf9; --ink: #1a241d; --muted: #617064; --accent: #0f5e59; --accent-2: #ba6b2d; --border: #d8ccb7; --good: #216e39; --bad: #9a3412; --pending: #946200; --unknown: #5b5f97; }",
                "    body { margin: 0; font-family: Georgia, 'Segoe UI', serif; background: radial-gradient(circle at top left, #fff8ee, #f1e7d4 58%, #efe6d9); color: var(--ink); }",
                "    a { color: var(--accent); text-decoration: none; } a:hover { text-decoration: underline; }",
                "    .hero { padding: 34px 40px 22px; border-bottom: 1px solid var(--border); background: linear-gradient(135deg, #fff9ef, #f0e3ca); }",
                "    .hero h1 { margin: 0 0 8px; font-size: 2.25rem; letter-spacing: -0.02em; }",
                "    .eyebrow { color: var(--accent); text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.78rem; font-weight: 700; margin-bottom: 10px; }",
                "    nav { padding: 16px 40px 0; }",
                "    section { padding: 24px 40px; }",
                "    .grid, .stage-grid { display: grid; gap: 18px; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }",
                "    .strategy-card, .stage-card, .session-summary { display: block; background: color-mix(in srgb, var(--card) 92%, white); border: 1px solid var(--border); border-radius: 22px; padding: 20px; box-shadow: 0 16px 32px rgba(47, 39, 22, 0.07); }",
                "    .strategy-card { transition: transform 160ms ease, box-shadow 160ms ease; } .strategy-card:hover { transform: translateY(-2px); box-shadow: 0 20px 38px rgba(47, 39, 22, 0.1); text-decoration: none; }",
                "    .strategy-card h2, .stage-card h3 { margin: 0 0 8px; }",
                "    .summary-shell { padding: 22px; }",
                "    .summary-grid, .stage-metrics, .decision-strip { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }",
                "    .metric { background: #fff8ef; border: 1px solid #eadcc9; border-radius: 16px; padding: 12px 14px; }",
                "    .metric span { display: block; color: var(--muted); font-size: 0.82rem; margin-bottom: 4px; }",
                "    .metric strong, .metric .value { font-size: 1rem; font-weight: 700; }",
                "    .metric-row { display: flex; justify-content: space-between; align-items: center; gap: 14px; padding: 8px 0; border-top: 1px dashed #e5d9c8; }",
                "    .metric-row:first-of-type { border-top: 0; }",
                "    .stage-topline { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }",
                "    .badge-row { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }",
                "    .badge { display: inline-flex; align-items: center; border-radius: 999px; padding: 6px 10px; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.02em; border: 1px solid currentColor; }",
                "    .badge-ready, .badge-pass, .badge-selected, .badge-bull, .badge-bear, .badge-bull_cf, .badge-bear_cf, .badge-yes { color: var(--good); background: rgba(33,110,57,0.09); }",
                "    .badge-in_progress, .badge-unknown, .badge-no_trigger, .badge-n_a, .badge-none { color: var(--unknown); background: rgba(91,95,151,0.1); }",
                "    .badge-warning, .badge-pending { color: var(--pending); background: rgba(148,98,0,0.1); }",
                "    .badge-no_go, .badge-failed, .badge-rejected, .badge-no { color: var(--bad); background: rgba(154,52,18,0.1); }",
                "    .focus-panel { margin: 14px 0; padding: 14px 16px; border-radius: 16px; background: linear-gradient(180deg, #fffaf2, #f8f0e4); border: 1px solid #e9dcc7; }",
                "    .focus-panel p { margin: 0 0 10px; } .focus-panel p:last-child { margin-bottom: 0; }",
                "    .formula-panel, .candidate-panel { margin-top: 14px; padding-top: 12px; border-top: 1px dashed #e1d3bd; }",
                "    .formula-panel h4, .candidate-panel h4 { margin: 0 0 10px; font-size: 1rem; }",
                "    .candidate-table { display: block; overflow-x: auto; font-size: 0.88rem; }",
                "    .candidate-table thead, .candidate-table tbody { display: table; width: 100%; }",
                "    .compact-error { margin-top: 10px; }",
                "    .artifact-links { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; font-size: 0.9rem; }",
                "    .artifact-links a { padding: 6px 10px; border-radius: 999px; background: #f4ecdf; border: 1px solid #e4d6c1; }",
                "    .top-links { margin-top: 16px; }",
                "    .trade-summary { margin-bottom: 14px; }",
                "    .trade-table { display: block; overflow-x: auto; font-size: 0.9rem; }",
                "    .trade-table thead, .trade-table tbody { display: table; width: 100%; }",
                "    .trade-links { margin-top: 0; min-width: 180px; }",
                "    .muted-text { color: var(--muted); font-size: 0.82rem; word-break: break-word; }",
                "    .empty-panel { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 18px; color: var(--muted); }",
                "    .tool-strip { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 18px; }",
                "    .tool-link, button { display: inline-flex; align-items: center; justify-content: center; border: 1px solid var(--accent); background: var(--accent); color: white; border-radius: 10px; padding: 10px 14px; font-weight: 700; cursor: pointer; font: inherit; }",
                "    .tool-link:hover, button:hover { text-decoration: none; filter: brightness(0.95); }",
                "    button[type='button'] { background: #fff8ef; color: var(--accent); }",
                "    .calculator-shell { display: grid; grid-template-columns: 1fr; gap: 20px; padding: 24px 40px; }",
                "    .calc-panel { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 18px; box-shadow: 0 16px 32px rgba(47,39,22,0.07); }",
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
                "    table { width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }",
                "    th, td { text-align: left; padding: 12px; border-bottom: 1px solid var(--border); vertical-align: top; }",
                "    th { background: #f4eadb; }",
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

    @staticmethod
    def _session_manifest_item(session: DashboardSessionSummary) -> dict[str, Any]:
        return {
            "session_date": session.session_date.isoformat(),
            "session_status": session.session_status,
            "final_decision_status": session.final_decision_status,
            "final_monthly_status": session.final_monthly_status,
            "final_selected_contract_symbol": session.final_selected_contract_symbol,
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
