from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.importers import load_strategy_rule
from tfis.paper import (
    S23FyersSnapshotCollector,
    S23FyersSnapshotCollectorError,
    S23PaperLiveDecisionBuilder,
    S23PaperLiveDecisionError,
    load_s23_decision_reference_packet,
)
from tfis.paper.live_ingress import S23LivePaperIngressConfig


DEFAULT_TRADINGENGINE_ROOT = Path(r"D:\TradingEngineProd")
DEFAULT_CONFIG = REPO_ROOT / "config" / "paper.s23.fyers_connect_test.yaml"
DEFAULT_REFERENCE_PACKET = (
    REPO_ROOT / "config" / "reference_packets" / "s23_bear_put_live_decision_reference.json"
)
DEFAULT_STRATEGY = (
    REPO_ROOT
    / "config"
    / "strategies"
    / "options_sell"
    / "nifty"
    / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh FYERS auth via TradingEngine automation, collect normalized TFIS "
            "market inputs, and build a paper-only S23 decision summary."
        )
    )
    parser.add_argument("--tradingengine-root", default=str(DEFAULT_TRADINGENGINE_ROOT))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--strategy-path", default=str(DEFAULT_STRATEGY))
    parser.add_argument("--reference-packet", default=str(DEFAULT_REFERENCE_PACKET))
    parser.add_argument("--artifact-root", default="tmp/s23_fyers_live_decision")
    parser.add_argument("--session-id", default="s23-fyers-live-decision")
    parser.add_argument("--carry-forward-state-dir")
    parser.add_argument("--enable-smoke-override", action="store_true")
    parser.add_argument("--skip-refresh", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    te_root = Path(args.tradingengine_root)
    env_path = te_root / ".env"
    token_path = te_root / "data" / "token_store.json"
    refresh_script = te_root / "scripts" / "fyers_token_refresh.py"
    te_python = te_root / ".venv" / "Scripts" / "python.exe"

    _require_exists(te_root, "TradingEngine root")
    _require_exists(env_path, "TradingEngine .env")
    _require_exists(token_path, "TradingEngine token_store.json")
    _require_exists(refresh_script, "TradingEngine FYERS token refresh script")
    _require_exists(Path(args.reference_packet), "TFIS reference packet")

    if not args.skip_refresh:
        refresh_python = te_python if te_python.exists() else Path(sys.executable)
        result = subprocess.run(
            [str(refresh_python), str(refresh_script)],
            cwd=str(te_root),
            check=False,
            text=True,
        )
        if result.returncode != 0:
            print("ERROR: TradingEngine FYERS token refresh failed.", file=sys.stderr)
            return result.returncode

    env_values = _read_env_file(env_path)
    token_payload = json.loads(token_path.read_text(encoding="utf-8"))
    app_id = str(env_values.get("FYERS_APP_ID") or "").strip()
    access_token = str(token_payload.get("access_token") or "").strip()
    client_id = str(env_values.get("FYERS_CLIENT_ID") or "").strip()
    if not app_id or not access_token:
        print(
            "ERROR: Need FYERS_APP_ID in TradingEngineProd .env and access_token in token_store.json.",
            file=sys.stderr,
        )
        return 1

    os.environ["FYERS_APP_ID"] = app_id
    os.environ["FYERS_ACCESS_TOKEN"] = access_token
    if client_id:
        os.environ["FYERS_CLIENT_ID"] = client_id

    collector = S23FyersSnapshotCollector(artifact_root=args.artifact_root)
    ingress_config = S23LivePaperIngressConfig.from_yaml(args.config)
    try:
        artifacts = collector.collect_from_files(
            config_path=args.config,
            strategy_path=args.strategy_path,
            carry_forward_state_dir=args.carry_forward_state_dir,
            session_id=args.session_id,
            adapter=None,
        )
    except S23FyersSnapshotCollectorError as exc:
        print(f"ERROR [{exc.code}]: {exc}", file=sys.stderr)
        return 1

    if artifacts.collected_inputs is None:
        print("ERROR: Snapshot collector did not return collected inputs.", file=sys.stderr)
        return 1

    strategy_rule = load_strategy_rule(args.strategy_path)
    reference_packet = load_s23_decision_reference_packet(args.reference_packet)
    decision_builder = S23PaperLiveDecisionBuilder()
    try:
        decision = decision_builder.build(
            strategy_rule=strategy_rule,
            reference_packet=reference_packet,
            collected_inputs=artifacts.collected_inputs,
            smoke_override_enabled=args.enable_smoke_override,
            smoke_override_selected_contract_symbol=(
                ingress_config.market.selected_contract_symbol
                if args.enable_smoke_override
                else None
            ),
        )
    except (S23PaperLiveDecisionError, RuntimeError) as exc:
        print(f"ERROR: Unable to build S23 live decision summary: {exc}", file=sys.stderr)
        return 1

    decision_json, decision_md = decision_builder.write_artifacts(
        decision,
        output_dir=artifacts.session_directory,
    )
    print("S23 live decision check succeeded.")
    print(f"Snapshot session directory: {artifacts.session_directory}")
    print(f"Underlying snapshot: {artifacts.normalized_underlying_snapshot_path}")
    print(f"Underlying bars: {artifacts.normalized_underlying_bars_path}")
    print(f"Option-chain snapshot: {artifacts.normalized_option_chain_snapshot_path}")
    print(f"Decision summary (JSON): {decision_json}")
    print(f"Decision summary (Markdown): {decision_md}")
    return 0


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


if __name__ == "__main__":
    raise SystemExit(main())
