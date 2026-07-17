from __future__ import annotations

import argparse
import http.server
import json
import socketserver
import sys
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.dashboard import StrategyDashboardConfig, TfisOperatorDashboardBuilder
from tfis.dashboard.config_loader import load_dashboard_strategy_configs
from tfis.monthly_status import (
    MonthlyStatusCurrentDataError,
    fetch_current_monthly_status,
    load_monthly_status_instrument_registry,
)
from tfis.paper import prepare_live_decision_runtime_environment


class DashboardRequestHandler(http.server.SimpleHTTPRequestHandler):
    dashboard_root: Path
    repo_root: Path
    runtime_config_path: Path

    def do_GET(self) -> None:
        request = urlsplit(self.path)
        if request.path == "/api/monthly-status/instruments":
            self._send_json(load_monthly_status_instrument_registry().to_json())
            return
        if request.path == "/api/monthly-status/current":
            self._handle_current_monthly_status(parse_qs(request.query))
            return
        super().do_GET()

    def translate_path(self, path: str) -> str:
        request_path = urlsplit(path).path
        if request_path in ("/", "/index.html"):
            request_path = f"/{self.dashboard_root.relative_to(self.repo_root).as_posix()}/index.html"
        elif (
            request_path.startswith("/strategies/")
            or request_path.startswith("/trades/")
            or request_path.startswith("/tools/")
            or request_path.startswith("/data/")
        ):
            request_path = f"/{self.dashboard_root.relative_to(self.repo_root).as_posix()}{request_path}"
        return super().translate_path(request_path)

    def _handle_current_monthly_status(self, query: dict[str, list[str]]) -> None:
        try:
            registry = load_monthly_status_instrument_registry()
            symbol = _query_value(query, "symbol") or registry.default_symbol
            price_source = _query_value(query, "price_source") or registry.default_price_source
            as_of_text = _query_value(query, "as_of") or date.today().isoformat()
            effective_status = _query_value(query, "effective_status") or "UNKNOWN"
            prepare_live_decision_runtime_environment(
                tfis_root=self.repo_root,
                config_path=self.runtime_config_path,
                skip_refresh=True,
            )
            result = fetch_current_monthly_status(
                symbol=symbol,
                price_source=price_source,
                as_of=date.fromisoformat(as_of_text),
                effective_status=effective_status,
            )
            self._send_json(result.to_json())
        except MonthlyStatusCurrentDataError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _send_json(self, payload: dict[str, object], *, status: int = 200) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def _query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    value = str(values[0]).strip()
    return value or None


class ReusableTcpServer(socketserver.TCPServer):
    allow_reuse_address = True

    def handle_error(self, request, client_address) -> None:  # type: ignore[override]
        exc_type, exc, _tb = sys.exc_info()
        if isinstance(exc, (BrokenPipeError, ConnectionAbortedError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and serve the TFIS operator dashboard locally."
    )
    parser.add_argument("--output-root", default="tmp/operator_dashboard")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Serve the existing dashboard files without rebuilding them first.",
    )
    parser.add_argument("--dashboard-config", default="config/operator_dashboard_strategies.yaml")
    parser.add_argument("--runtime-config", default="config/paper.s23.fyers_connect_test.yaml")
    parser.add_argument("--s23-artifact-root", default="data/strategies/S23/fyers_morning_supervised_decision")
    parser.add_argument(
        "--s23-strategy-path",
        default="config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
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
    dashboard_config_path = REPO_ROOT / args.dashboard_config
    if dashboard_config_path.exists():
        strategy_configs = load_dashboard_strategy_configs(
            dashboard_config_path,
            repo_root=REPO_ROOT,
        )
    else:
        strategy_configs = (
            StrategyDashboardConfig(
                strategy_code="S23",
                display_name="S23 Operator Dashboard",
                artifact_root=REPO_ROOT / args.s23_artifact_root,
                strategy_path=REPO_ROOT / args.s23_strategy_path,
                reference_packet_path=REPO_ROOT / args.s23_reference_packet,
                session_id_prefix=args.session_id_prefix,
            ),
        )
    if args.skip_build:
        index_html = output_root / "index.html"
        if not index_html.exists():
            print(
                "ERROR: --skip-build was requested but the dashboard index does not exist yet. "
                "Build it first or start without --skip-build.",
                file=sys.stderr,
            )
            return 1
        result_index_html = index_html
    else:
        builder = TfisOperatorDashboardBuilder(strategy_configs=strategy_configs)
        result = builder.build(output_root=output_root)
        result_index_html = result.index_html
    handler = DashboardRequestHandler
    handler.directory = str(REPO_ROOT)
    handler.dashboard_root = output_root
    handler.repo_root = REPO_ROOT
    handler.runtime_config_path = REPO_ROOT / args.runtime_config
    with ReusableTcpServer(("127.0.0.1", args.port), handler) as httpd:
        print("TFIS operator dashboard ready.")
        print(f"Serving: {result_index_html}")
        relative_index = result_index_html.relative_to(REPO_ROOT).as_posix()
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
