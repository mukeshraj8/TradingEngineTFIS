from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.paper.live_ingress import (
    S23BrokerPaperIngressRunner,
    S23LivePaperIngressError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the S23 broker-agnostic live-paper ingress foundation with "
            "Fyers as the first market-data adapter."
        )
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the S23 live-paper broker ingress YAML config.",
    )
    parser.add_argument(
        "--prelude-jsonl",
        required=True,
        help="Normalized non-broker S23 prelude JSONL source.",
    )
    parser.add_argument(
        "--artifact-root",
        default="tmp/s23_fyers_paper_ingress",
        help="Root directory for persisted live-paper ingress artifacts.",
    )
    parser.add_argument(
        "--session-id",
        help="Optional stable session id override.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help=(
            "Validate the S23 FYERS ingress config and prelude without connecting "
            "to FYERS or running the paper engine."
        ),
    )
    parser.add_argument(
        "--out-json",
        help="Optional explicit path for the ingress JSON summary.",
    )
    parser.add_argument(
        "--out-md",
        help="Optional explicit path for the ingress Markdown summary.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    runner = S23BrokerPaperIngressRunner(artifact_root=args.artifact_root)
    try:
        if args.preflight_only:
            preflight_summary = runner.preflight(
                config_path=args.config,
                prelude_jsonl=args.prelude_jsonl,
                session_id=args.session_id,
            )
            if args.out_json:
                Path(args.out_json).write_text(
                    runner.render_preflight_json(preflight_summary),
                    encoding="utf-8",
                )
            if args.out_md:
                Path(args.out_md).write_text(
                    runner.render_preflight_markdown(preflight_summary),
                    encoding="utf-8",
                )
            print(f"Broker ingress preflight status: {preflight_summary.preflight_status}")
            print(
                "Expected session directory: "
                f"{preflight_summary.expected_session_directory}"
            )
            return 0 if preflight_summary.can_run else 1

        artifact_set = runner.run(
            config_path=args.config,
            prelude_jsonl=args.prelude_jsonl,
            session_id=args.session_id,
        )
    except S23LivePaperIngressError as exc:
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

    print(f"Broker ingress session directory: {artifact_set.session_directory}")
    print(f"Broker ingress summary: {artifact_set.ingress_summary_path}")
    print(f"Paper review markdown: {artifact_set.dry_run_artifacts.review_md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
