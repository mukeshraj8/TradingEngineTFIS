from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.paper import S23SnapshotValidationHarness


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run repeated one-shot FYERS snapshot validation for S23 live-paper readiness."
    )
    parser.add_argument("--config", required=True, help="Paper ingress config YAML path.")
    parser.add_argument("--strategy-path", required=True, help="Strategy folder or strategy YAML path.")
    parser.add_argument("--runtime-fixture", required=True, help="Runtime input JSON fixture for generated prelude builds.")
    parser.add_argument(
        "--carry-forward-state-dir",
        help="Optional directory containing paper_position_state.json for carry-forward resume validation.",
    )
    parser.add_argument("--artifact-root", default="tmp/s23_snapshot_validation_harness", help="Root directory for validation artifacts.")
    parser.add_argument("--session-id", help="Optional stable session id override.")
    parser.add_argument("--samples", type=int, default=3, help="Number of one-shot snapshots to collect.")
    parser.add_argument("--interval-seconds", type=int, default=60, help="Seconds between one-shot snapshot collections.")
    parser.add_argument(
        "--enable-smoke-override",
        action="store_true",
        help="Allow config.market.selected_contract_symbol as an explicit smoke override during prelude build.",
    )
    parser.add_argument("--out-json", help="Optional explicit path for the aggregate JSON report.")
    parser.add_argument("--out-md", help="Optional explicit path for the markdown operational summary.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    harness = S23SnapshotValidationHarness(artifact_root=args.artifact_root)
    artifact_set = harness.run_from_files(
        config_path=args.config,
        strategy_path=args.strategy_path,
        runtime_fixture_path=args.runtime_fixture,
        carry_forward_state_dir=args.carry_forward_state_dir,
        session_id=args.session_id,
        samples=args.samples,
        interval_seconds=args.interval_seconds,
        enable_smoke_override=args.enable_smoke_override,
    )

    if args.out_json:
        Path(args.out_json).write_text(harness.render_json(artifact_set.report), encoding="utf-8")
    if args.out_md:
        Path(args.out_md).write_text(harness.render_markdown(artifact_set.report), encoding="utf-8")

    print(f"Validation session directory: {artifact_set.session_directory}")
    print(f"Aggregate JSON report: {artifact_set.report_json_path}")
    print(f"Operational markdown summary: {artifact_set.report_markdown_path}")
    print(f"Per-sample JSONL: {artifact_set.samples_jsonl_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
