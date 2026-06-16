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
class DashboardBuildResult:
    output_root: Path
    index_html: Path
    manifest_json: Path
    strategy_pages: dict[str, Path]


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
        )

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
        stage_dirs = self._find_stage_dirs(config=config, day_dir=day_dir)
        session_complete = bool(
            final_session_dir is not None
            and (final_session_dir / "scheduled_run_metadata.json").exists()
        )
        stage_summaries = tuple(
            self._build_stage_summary(
                config=config,
                session_date=session_date,
                day_dir=day_dir,
                stage_dir=stage_dir,
                final_session_dir=final_session_dir,
                prefer_reconstruction=not session_complete,
            )
            for stage_dir in sorted(stage_dirs, key=lambda item: _STAGE_ORDER.get(self._extract_stage_key(item.name), 99))
        )
        final_summary = self._read_json(final_session_dir / "trade_decision_summary.json") if final_session_dir and (final_session_dir / "trade_decision_summary.json").exists() else None
        final_summary_view = final_summary.get("summary", final_summary) if isinstance(final_summary, dict) else None
        final_decision_status = final_summary_view.get("status") if isinstance(final_summary_view, dict) else None
        final_monthly_status = final_summary_view.get("monthly_status") if isinstance(final_summary_view, dict) else None
        final_selected_contract_symbol = final_summary_view.get("selected_contract_symbol") if isinstance(final_summary_view, dict) else None
        latest_stage = stage_summaries[-1] if stage_summaries else None
        if final_monthly_status is None and latest_stage is not None:
            final_monthly_status = latest_stage.monthly_status
        if final_selected_contract_symbol is None and latest_stage is not None:
            final_selected_contract_symbol = latest_stage.selected_contract_symbol
        if final_decision_status:
            session_status = final_decision_status
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
            raw_artifact_links={
                "snapshot_preflight_summary.json": str(stage_dir / "snapshot_preflight_summary.json"),
                "normalized_underlying_bars.json": str(stage_dir / "normalized_underlying_bars.json"),
                "normalized_option_chain_snapshot.json": str(stage_dir / "normalized_option_chain_snapshot.json"),
            },
        )

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
        history_rows = "\n".join(self._render_session_history_row(session, page_path=page_path) for session in sessions) or "<tr><td colspan=\"5\">No sessions found.</td></tr>"
        body = "\n".join(
            [
                '<nav><a href="../../index.html">Back to strategy index</a></nav>',
                "<header class=\"hero\">",
                f"<div class=\"eyebrow\">Strategy {html.escape(config.strategy_code)}</div>",
                f"<h1>{html.escape(config.display_name)}</h1>",
                f"<p>Operator page for {html.escape(config.strategy_code)}. Each stage is rendered from TFIS artifacts and reconstructed stage logic when stage-level explainers are not yet available.</p>",
                "</header>",
                "<section>",
                "<h2>Latest Session</h2>",
                latest_block,
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
                f"<div class=\"artifact-links\">{self._render_links(stage.raw_artifact_links, page_path=page_path)}</div>",
                "</article>",
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
                href = os.path.relpath(path, start=page_path.parent.resolve()).replace("\\", "/")
            parts.append(f'<a href="{html.escape(href)}">{html.escape(label)}</a>')
        return " ".join(parts) if parts else "<span>n/a</span>"

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
                "    .badge-ready, .badge-pass, .badge-bull, .badge-bear, .badge-bull_cf, .badge-bear_cf, .badge-yes { color: var(--good); background: rgba(33,110,57,0.09); }",
                "    .badge-in_progress, .badge-unknown, .badge-no_trigger, .badge-n_a, .badge-none { color: var(--unknown); background: rgba(91,95,151,0.1); }",
                "    .badge-warning, .badge-pending { color: var(--pending); background: rgba(148,98,0,0.1); }",
                "    .badge-no_go, .badge-failed, .badge-no { color: var(--bad); background: rgba(154,52,18,0.1); }",
                "    .focus-panel { margin: 14px 0; padding: 14px 16px; border-radius: 16px; background: linear-gradient(180deg, #fffaf2, #f8f0e4); border: 1px solid #e9dcc7; }",
                "    .focus-panel p { margin: 0 0 10px; } .focus-panel p:last-child { margin-bottom: 0; }",
                "    .artifact-links { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; font-size: 0.9rem; }",
                "    .artifact-links a { padding: 6px 10px; border-radius: 999px; background: #f4ecdf; border: 1px solid #e4d6c1; }",
                "    .top-links { margin-top: 16px; }",
                "    table { width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }",
                "    th, td { text-align: left; padding: 12px; border-bottom: 1px solid var(--border); vertical-align: top; }",
                "    th { background: #f4eadb; }",
                "    @media (max-width: 720px) { .hero, section, nav { padding-left: 18px; padding-right: 18px; } }",
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
