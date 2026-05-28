from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.paper import S23FyersSnapshotCollector, S23FyersSnapshotCollectorError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect one-shot FYERS normalized snapshot inputs for S23 paper preflight."
    )
    parser.add_argument("--config", required=True, help="Paper ingress config YAML path.")
    parser.add_argument(
        "--strategy-path",
        required=True,
        help="Strategy folder or strategy YAML path.",
    )
    parser.add_argument(
        "--runtime-fixture",
        help="Runtime input JSON fixture required for --dry-run-build-prelude.",
    )
    parser.add_argument(
        "--carry-forward-state-dir",
        help="Optional directory containing paper_position_state.json for carry-forward resume prelude builds.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Collect and persist normalized snapshot artifacts only.",
    )
    parser.add_argument(
        "--dry-run-build-prelude",
        action="store_true",
        help="Collect normalized snapshot artifacts and build generated prelude artifacts from runtime fixture inputs.",
    )
    parser.add_argument(
        "--enable-smoke-override",
        action="store_true",
        help="Allow config.market.selected_contract_symbol to act as an explicit smoke override during generated prelude build.",
    )
    parser.add_argument(
        "--artifact-root",
        default="tmp/s23_fyers_snapshot_preflight",
        help="Root directory for persisted snapshot preflight artifacts.",
    )
    parser.add_argument("--session-id", help="Optional stable session id override.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.preflight_only and not args.dry_run_build_prelude:
        args.preflight_only = True
    if args.dry_run_build_prelude and not args.runtime_fixture:
        parser.error("--dry-run-build-prelude requires --runtime-fixture")

    collector = S23FyersSnapshotCollector(artifact_root=args.artifact_root)
    try:
        artifact_set = collector.collect_from_files(
            config_path=args.config,
            strategy_path=args.strategy_path,
            runtime_fixture_path=args.runtime_fixture,
            carry_forward_state_dir=args.carry_forward_state_dir,
            session_id=args.session_id,
            dry_run_build_prelude=args.dry_run_build_prelude,
            enable_smoke_override=args.enable_smoke_override,
        )
    except S23FyersSnapshotCollectorError as exc:
        print(f"ERROR [{exc.code}]: {exc}", file=sys.stderr)
        return 1

    print(f"Snapshot session directory: {artifact_set.session_directory}")
    print(f"Snapshot summary: {artifact_set.summary_path}")
    print(f"Normalized underlying snapshot: {artifact_set.normalized_underlying_snapshot_path}")
    print(f"Normalized option-chain snapshot: {artifact_set.normalized_option_chain_snapshot_path}")
    if artifact_set.generated_prelude_events_path is not None:
        print(f"Generated prelude events: {artifact_set.generated_prelude_events_path}")
    if artifact_set.generated_prelude_provenance_path is not None:
        print(f"Generated prelude provenance: {artifact_set.generated_prelude_provenance_path}")
    if artifact_set.generated_governance_events_path is not None:
        print(f"Generated prelude governance events: {artifact_set.generated_governance_events_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
