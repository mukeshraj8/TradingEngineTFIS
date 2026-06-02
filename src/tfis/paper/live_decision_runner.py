from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from tfis.importers import load_strategy_rule

from .fyers_snapshot_collector import (
    S23FyersSnapshotArtifactSet,
    S23FyersSnapshotCollector,
    S23FyersSnapshotCollectorError,
)
from .live_decision import S23PaperLiveDecisionBuilder, S23PaperLiveDecisionError
from .live_ingress import S23LivePaperIngressConfig
from .runtime_input_derivation import load_s23_decision_reference_packet


@dataclass(frozen=True, slots=True)
class S23LiveDecisionRunResult:
    snapshot_artifacts: S23FyersSnapshotArtifactSet
    decision_summary_json: Path
    decision_summary_markdown: Path
    decision_explainer_json: Path
    decision_explainer_markdown: Path


def prepare_fyers_env_from_tradingengine(
    *,
    tradingengine_root: str | Path,
    skip_refresh: bool = False,
) -> None:
    te_root = Path(tradingengine_root)
    env_path = te_root / ".env"
    token_path = te_root / "data" / "token_store.json"
    refresh_script = te_root / "scripts" / "fyers_token_refresh.py"
    te_python = te_root / ".venv" / "Scripts" / "python.exe"

    _require_exists(te_root, "TradingEngine root")
    _require_exists(env_path, "TradingEngine .env")
    _require_exists(token_path, "TradingEngine token_store.json")
    _require_exists(refresh_script, "TradingEngine FYERS token refresh script")

    _clear_proxy_environment()

    if not skip_refresh:
        refresh_python = te_python if te_python.exists() else Path(sys.executable)
        refresh_env = os.environ.copy()
        for key in _PROXY_ENV_KEYS:
            refresh_env.pop(key, None)
        result = subprocess.run(
            [str(refresh_python), str(refresh_script)],
            cwd=str(te_root),
            check=False,
            text=True,
            env=refresh_env,
        )
        if result.returncode != 0:
            raise RuntimeError("TradingEngine FYERS token refresh failed.")

    env_values = _read_env_file(env_path)
    token_payload = json.loads(token_path.read_text(encoding="utf-8"))
    app_id = str(env_values.get("FYERS_APP_ID") or "").strip()
    access_token = str(token_payload.get("access_token") or "").strip()
    client_id = str(env_values.get("FYERS_CLIENT_ID") or "").strip()
    if not app_id or not access_token:
        raise RuntimeError(
            "Need FYERS_APP_ID in TradingEngineProd .env and access_token in token_store.json."
        )

    os.environ["FYERS_APP_ID"] = app_id
    os.environ["FYERS_ACCESS_TOKEN"] = access_token
    if client_id:
        os.environ["FYERS_CLIENT_ID"] = client_id


_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
)


def _clear_proxy_environment() -> None:
    for key in _PROXY_ENV_KEYS:
        os.environ.pop(key, None)


def run_s23_live_decision_check(
    *,
    tradingengine_root: str | Path,
    config_path: str | Path,
    strategy_path: str | Path,
    reference_packet_path: str | Path,
    artifact_root: str | Path,
    session_id: str,
    carry_forward_state_dir: str | Path | None = None,
    enable_smoke_override: bool = False,
    skip_refresh: bool = False,
) -> S23LiveDecisionRunResult:
    prepare_fyers_env_from_tradingengine(
        tradingengine_root=tradingengine_root,
        skip_refresh=skip_refresh,
    )
    _require_exists(Path(reference_packet_path), "TFIS reference packet")

    collector = S23FyersSnapshotCollector(artifact_root=artifact_root)
    ingress_config = S23LivePaperIngressConfig.from_yaml(config_path)
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
    reference_packet = load_s23_decision_reference_packet(reference_packet_path)
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


def _require_exists(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"Missing {label}: {path}")


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


__all__ = [
    "S23LiveDecisionRunResult",
    "prepare_fyers_env_from_tradingengine",
    "run_s23_live_decision_check",
]
