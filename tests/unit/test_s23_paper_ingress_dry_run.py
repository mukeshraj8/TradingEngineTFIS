from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from tfis.paper import (
    PaperSessionState,
    S23PaperIngressDryRunRunner,
    S23PaperIngressReadiness,
    S23PaperSessionArtifactWriter,
)


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "paper"
    / "s23_archive_ingress_dry_run.jsonl"
)


def _write_modified_fixture(
    tmp_path: Path,
    *,
    drop_event_type: str | None = None,
    mutate: dict[str, dict[str, object]] | None = None,
) -> Path:
    output_path = tmp_path / "events.jsonl"
    lines: list[str] = []
    for raw_line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines():
        payload = json.loads(raw_line)
        if drop_event_type and payload["event_type"] == drop_event_type:
            continue
        if mutate and payload["event_type"] in mutate:
            updates = mutate[payload["event_type"]]
            for key, value in updates.items():
                if key.startswith("payload."):
                    payload["payload"][key.split(".", 1)[1]] = value
                else:
                    payload[key] = value
        lines.append(json.dumps(payload, sort_keys=True))
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def test_archive_ingress_dry_run_reaches_order_planned_and_writes_intent_shell(
    tmp_path: Path,
) -> None:
    runner = S23PaperIngressDryRunRunner(
        artifact_writer=S23PaperSessionArtifactWriter(tmp_path / "dry_runs")
    )

    artifact_set = runner.run_jsonl(FIXTURE_PATH, session_id="archive-ingress-pass")

    assert artifact_set.summary.terminal_state is PaperSessionState.ORDER_PLANNED
    assert artifact_set.summary.operational_readiness is S23PaperIngressReadiness.PASS
    assert artifact_set.execution_artifacts.paper_order_intent_path is not None
    assert artifact_set.review_json_path.exists()
    assert artifact_set.review_md_path.exists()
    assert artifact_set.ingress_health_metrics_path.exists()
    assert artifact_set.summary.ingress_health_metrics.stale_event_count == 0
    assert artifact_set.summary.selected_contract_audit.present_in_option_chain is True
    assert artifact_set.summary.timing_audit
    markdown = artifact_set.dry_run_summary_md_path.read_text(encoding="utf-8")
    assert "Ingress-only dry run" in markdown
    assert "No broker API was used." in markdown


def test_missing_option_chain_results_in_no_trade(tmp_path: Path) -> None:
    runner = S23PaperIngressDryRunRunner(
        artifact_writer=S23PaperSessionArtifactWriter(tmp_path / "dry_runs")
    )
    events_path = _write_modified_fixture(
        tmp_path,
        drop_event_type="OPTION_CHAIN_SNAPSHOT",
    )

    artifact_set = runner.run_jsonl(events_path, session_id="archive-ingress-no-chain")

    assert artifact_set.summary.terminal_state is PaperSessionState.NO_TRADE
    assert artifact_set.summary.operational_readiness is S23PaperIngressReadiness.FAIL
    assert "missing_option_chain_snapshot" in artifact_set.summary.no_trade_reasons
    assert artifact_set.summary.ingress_health_metrics.missing_option_chain_count == 1
    assert artifact_set.execution_artifacts.paper_order_intent_path is None


def test_missing_selected_contract_results_in_no_trade(tmp_path: Path) -> None:
    runner = S23PaperIngressDryRunRunner(
        artifact_writer=S23PaperSessionArtifactWriter(tmp_path / "dry_runs")
    )
    events_path = _write_modified_fixture(
        tmp_path,
        drop_event_type="SELECTED_CONTRACT_QUOTE",
    )

    artifact_set = runner.run_jsonl(events_path, session_id="archive-ingress-no-selected")

    assert artifact_set.summary.terminal_state is PaperSessionState.NO_TRADE
    assert artifact_set.summary.operational_readiness is S23PaperIngressReadiness.FAIL
    assert "missing_selected_contract_quote" in artifact_set.summary.no_trade_reasons
    assert artifact_set.summary.ingress_health_metrics.missing_selected_contract_count == 1


def test_stale_selected_contract_quote_results_in_no_trade(tmp_path: Path) -> None:
    late_finalize_runner = S23PaperIngressDryRunRunner(
        artifact_writer=S23PaperSessionArtifactWriter(tmp_path / "dry_runs_late")
    )
    artifact_set = late_finalize_runner.run_jsonl(
        FIXTURE_PATH,
        session_id="archive-ingress-stale-selected-late",
        finalize_at=datetime.fromisoformat("2026-05-08T09:31:30+05:30"),
    )

    assert artifact_set.summary.terminal_state in {
        PaperSessionState.NO_TRADE,
        PaperSessionState.ABORTED,
    }
    assert (
        "stale_selected_contract_quote" in artifact_set.summary.no_trade_reasons
        or "stale_selected_contract_quote" in artifact_set.summary.abort_reasons
    )
    assert artifact_set.summary.ingress_health_metrics.stale_event_count >= 1
    assert artifact_set.summary.selected_contract_audit.quote_fresh_at_finalize is False


def test_timezone_mismatch_aborts(tmp_path: Path) -> None:
    runner = S23PaperIngressDryRunRunner(
        artifact_writer=S23PaperSessionArtifactWriter(tmp_path / "dry_runs")
    )
    events_path = _write_modified_fixture(
        tmp_path,
        mutate={"SELECTED_CONTRACT_QUOTE": {"timezone": "UTC"}},
    )

    artifact_set = runner.run_jsonl(events_path, session_id="archive-ingress-timezone-abort")

    assert artifact_set.summary.terminal_state is PaperSessionState.ABORTED
    assert artifact_set.summary.operational_readiness is S23PaperIngressReadiness.FAIL
    assert artifact_set.summary.ingress_health_metrics.timezone_mismatch_count == 1
    assert "unsupported_timezone" in artifact_set.summary.abort_reasons
