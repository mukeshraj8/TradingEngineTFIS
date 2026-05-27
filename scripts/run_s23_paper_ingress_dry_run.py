from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.paper import (
    S23PaperIngressDryRunError,
    S23PaperIngressDryRunRunner,
    S23PaperSessionArtifactWriter,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an S23 normalized live-paper ingress-only dry run."
    )
    parser.add_argument(
        "--events-jsonl",
        required=True,
        help="Normalized paper ingress JSONL source.",
    )
    parser.add_argument(
        "--artifact-root",
        default="tmp/s23_live_paper_dry_runs",
        help="Root directory for persisted dry-run session artifacts.",
    )
    parser.add_argument(
        "--session-id",
        help="Optional stable session id override.",
    )
    parser.add_argument(
        "--out-json",
        help="Optional explicit path for the dry-run JSON summary.",
    )
    parser.add_argument(
        "--out-md",
        help="Optional explicit path for the dry-run Markdown summary.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    runner = S23PaperIngressDryRunRunner(
        artifact_writer=S23PaperSessionArtifactWriter(args.artifact_root)
    )
    try:
        artifact_set = runner.run_jsonl(
            args.events_jsonl,
            session_id=args.session_id,
        )
    except S23PaperIngressDryRunError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.out_json:
        Path(args.out_json).write_text(
            runner.render_json(artifact_set.summary),
            encoding="utf-8",
        )
    if args.out_md:
        Path(args.out_md).write_text(
            runner.render_markdown(artifact_set.summary),
            encoding="utf-8",
        )

    print(f"Dry-run session directory: {artifact_set.session_directory}")
    print(f"Dry-run JSON summary: {artifact_set.dry_run_summary_json_path}")
    print(f"Dry-run markdown summary: {artifact_set.dry_run_summary_md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
