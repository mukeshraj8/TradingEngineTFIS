from __future__ import annotations

import argparse
import http.server
import socketserver
import sys
from pathlib import Path
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.dashboard import StrategyDashboardConfig, TfisOperatorDashboardBuilder


class DashboardRequestHandler(http.server.SimpleHTTPRequestHandler):
    dashboard_root: Path
    repo_root: Path

    def translate_path(self, path: str) -> str:
        request_path = urlsplit(path).path
        if request_path in ("/", "/index.html"):
            request_path = f"/{self.dashboard_root.relative_to(self.repo_root).as_posix()}/index.html"
        elif request_path.startswith("/strategies/"):
            request_path = f"/{self.dashboard_root.relative_to(self.repo_root).as_posix()}{request_path}"
        return super().translate_path(request_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and serve the TFIS operator dashboard locally."
    )
    parser.add_argument("--output-root", default="tmp/operator_dashboard")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--s23-artifact-root", default="tmp/s23_fyers_morning_supervised_decision")
    parser.add_argument(
        "--s23-strategy-path",
        default="config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
    )
    parser.add_argument(
        "--s23-reference-packet",
        default="config/reference_packets/s23_bear_put_live_decision_reference.json",
    )
    parser.add_argument("--session-id-prefix", default="s23-fyers-morning-supervised-decision")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_root = REPO_ROOT / args.output_root
    builder = TfisOperatorDashboardBuilder(
        strategy_configs=(
            StrategyDashboardConfig(
                strategy_code="S23",
                display_name="S23 Operator Dashboard",
                artifact_root=REPO_ROOT / args.s23_artifact_root,
                strategy_path=REPO_ROOT / args.s23_strategy_path,
                reference_packet_path=REPO_ROOT / args.s23_reference_packet,
                session_id_prefix=args.session_id_prefix,
            ),
        )
    )
    result = builder.build(output_root=output_root)
    handler = DashboardRequestHandler
    handler.directory = str(REPO_ROOT)
    handler.dashboard_root = output_root
    handler.repo_root = REPO_ROOT
    with socketserver.TCPServer(("127.0.0.1", args.port), handler) as httpd:
        print("TFIS operator dashboard ready.")
        print(f"Serving: {result.index_html}")
        relative_index = result.index_html.relative_to(REPO_ROOT).as_posix()
        print(f"URL: http://127.0.0.1:{args.port}/{relative_index}")
        print(f"Shortcut: http://127.0.0.1:{args.port}/index.html")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping TFIS operator dashboard server.")
            httpd.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
