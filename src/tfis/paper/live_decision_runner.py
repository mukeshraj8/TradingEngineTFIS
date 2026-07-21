from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tfis.brokers.fyers_token import prepare_fyers_env_from_tfis as _prepare_fyers_env_from_tfis_auth
from tfis.importers import load_strategy_rule

from .fyers_snapshot_collector import (
    PaperFyersSnapshotArtifactSet,
    PaperFyersSnapshotCollector,
    PaperFyersSnapshotCollectorError,
)
from .live_decision import S23PaperLiveDecisionBuilder, S23PaperLiveDecisionError
from .live_ingress import PaperLiveIngressConfig
from .lifecycle_runtime_config import (
    PaperLifecycleRuntimeConfig,
    prepare_paper_broker_runtime_environment,
)
from .runtime_input_derivation import load_paper_decision_reference_packet


@dataclass(frozen=True, slots=True)
class S23LiveDecisionRunResult:
    snapshot_artifacts: PaperFyersSnapshotArtifactSet
    decision_summary_json: Path
    decision_summary_markdown: Path
    decision_explainer_json: Path
    decision_explainer_markdown: Path


PaperLiveDecisionRunResult = S23LiveDecisionRunResult


def prepare_fyers_env_from_tfis(
    *,
    tfis_root: str | Path | None = None,
    skip_refresh: bool = False,
) -> None:
    prepare_fyers_env_from_tfis_auth(tfis_root=tfis_root, skip_refresh=skip_refresh)


def prepare_fyers_env_from_tfis_auth(
    *,
    tfis_root: str | Path | None = None,
    skip_refresh: bool = False,
) -> None:
    _prepare_fyers_env_from_tfis_auth(tfis_root=tfis_root, skip_refresh=skip_refresh)


def prepare_live_decision_runtime_environment(
    *,
    tfis_root: str | Path | None = None,
    config_path: str | Path,
    skip_refresh: bool = False,
) -> None:
    runtime_config = PaperLifecycleRuntimeConfig.from_yaml(config_path)
    prepare_paper_broker_runtime_environment(
        runtime_config,
        tfis_root=tfis_root or Path.cwd(),
        skip_refresh=skip_refresh,
    )


def run_s23_live_decision_check(
    *,
    tfis_root: str | Path | None = None,
    config_path: str | Path,
    strategy_path: str | Path,
    reference_packet_path: str | Path,
    artifact_root: str | Path,
    session_id: str,
    carry_forward_state_dir: str | Path | None = None,
    enable_smoke_override: bool = False,
    skip_refresh: bool = False,
) -> S23LiveDecisionRunResult:
    prepare_live_decision_runtime_environment(
        tfis_root=tfis_root,
        config_path=config_path,
        skip_refresh=skip_refresh,
    )
    _require_exists(Path(reference_packet_path), "TFIS reference packet")

    collector = PaperFyersSnapshotCollector(artifact_root=artifact_root)
    ingress_config = PaperLiveIngressConfig.from_yaml(config_path)
    snapshot_artifacts = collector.collect_from_files(
        config_path=config_path,
        strategy_path=strategy_path,
        carry_forward_state_dir=carry_forward_state_dir,
        session_id=session_id,
        adapter=None,
    )
    if snapshot_artifacts.collected_inputs is None:
        raise RuntimeError("Snapshot collector did not return collected inputs.")

    strategy_rule = load_strategy_rule(strategy_path)
    reference_packet = load_paper_decision_reference_packet(reference_packet_path)
    decision_builder = S23PaperLiveDecisionBuilder()
    decision = decision_builder.build(
        strategy_rule=strategy_rule,
        reference_packet=reference_packet,
        collected_inputs=snapshot_artifacts.collected_inputs,
        smoke_override_enabled=enable_smoke_override,
        smoke_override_selected_contract_symbol=(
            ingress_config.market.selected_contract_symbol if enable_smoke_override else None
        ),
        allow_branch_pinned_unknown_monthly_status=True,
    )
    decision_summary_json, decision_summary_markdown = decision_builder.write_artifacts(
        decision,
        output_dir=snapshot_artifacts.session_directory,
    )
    return S23LiveDecisionRunResult(
        snapshot_artifacts=snapshot_artifacts,
        decision_summary_json=decision_summary_json,
        decision_summary_markdown=decision_summary_markdown,
        decision_explainer_json=snapshot_artifacts.session_directory / "trade_decision_explainer.json",
        decision_explainer_markdown=snapshot_artifacts.session_directory / "trade_decision_explainer.md",
    )


run_paper_live_decision_check = run_s23_live_decision_check


def _require_exists(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"Missing {label}: {path}")


__all__ = [
    "prepare_live_decision_runtime_environment",
    "PaperLiveDecisionRunResult",
    "S23LiveDecisionRunResult",
    "prepare_fyers_env_from_tfis",
    "prepare_fyers_env_from_tfis_auth",
    "run_paper_live_decision_check",
    "run_s23_live_decision_check",
]
