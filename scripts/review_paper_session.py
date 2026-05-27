from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.paper import S23PaperReviewError, S23PaperSessionReviewer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Review an S23 paper-session artifact folder or replay bundle."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--session-dir", help="Paper-session artifact directory to review.")
    group.add_argument("--bundle-dir", help="Replay-bundle directory to review.")
    parser.add_argument("--out-json", help="Optional path for JSON review output.")
    parser.add_argument("--out-md", help="Optional path for Markdown review output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    reviewer = S23PaperSessionReviewer()
    try:
        if args.bundle_dir:
            summary = reviewer.review_bundle(args.bundle_dir)
        else:
            summary = reviewer.review_session(args.session_dir)
    except S23PaperReviewError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.out_json or args.out_md:
        reviewer.write_review_outputs(
            summary,
            out_json=args.out_json,
            out_md=args.out_md,
        )
    else:
        print(reviewer.render_review_markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
