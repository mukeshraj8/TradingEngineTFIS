from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.paper import (
    PaperGeneratedPreludeDryRunError,
    PaperGeneratedPreludeDryRunRunner,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an S23 generated-live-prelude paper ingress dry run."
    )
    parser.add_argument("--strategy-path", required=True, help="Strategy folder or strategy YAML path.")
    parser.add_argument("--config", required=True, help="Paper ingress config YAML path.")
    parser.add_argument("--runtime-fixture", required=True, help="Generated-prelude runtime input JSON fixture.")
    parser.add_argument("--market-events-jsonl", required=True, help="Normalized market-event JSONL fixture.")
    parser.add_argument(
        "--carry-forward-state-dir",
        help="Optional directory containing paper_position_state.json for carry-forward resume tests.",
    )
    parser.add_argument(
        "--enable-smoke-override",
        action="store_true",
        help="Allow config.market.selected_contract_symbol to act as an explicit smoke override.",
    )
    parser.add_argument(
        "--artifact-root",
        default="tmp/s23_generated_live_prelude_dry_runs",
        help="Root directory for persisted dry-run session artifacts.",
    )
    parser.add_argument("--session-id", help="Optional stable session id override.")
    parser.add_argument("--out-json", help="Optional explicit path for the dry-run JSON summary.")
    parser.add_argument("--out-md", help="Optional explicit path for the dry-run Markdown summary.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    runner = PaperGeneratedPreludeDryRunRunner()
    try:
        artifact_set = runner.run_from_files(
            strategy_path=args.strategy_path,
            ingress_config_path=args.config,
            runtime_fixture_path=args.runtime_fixture,
            market_events_jsonl=args.market_events_jsonl,
            carry_forward_state_dir=args.carry_forward_state_dir,
            session_id=args.session_id,
            enable_smoke_override=args.enable_smoke_override,
        )
    except PaperGeneratedPreludeDryRunError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.out_json:
        Path(args.out_json).write_text(
            runner.render_json(artifact_set),
            encoding="utf-8",
        )
    if args.out_md:
        Path(args.out_md).write_text(
            runner.render_markdown(artifact_set),
            encoding="utf-8",
        )

    print(f"Dry-run session directory: {artifact_set.ingress_artifacts.session_directory}")
    print(f"Generated prelude events: {artifact_set.generated_prelude_events_path}")
    print(f"Combined events: {artifact_set.combined_events_path}")
    print(f"Prelude provenance: {artifact_set.provenance_path}")
    print(f"Dry-run JSON summary: {artifact_set.ingress_artifacts.dry_run_summary_json_path}")
    print(f"Dry-run markdown summary: {artifact_set.ingress_artifacts.dry_run_summary_md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
